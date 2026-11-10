"""Dialogue gateway: the only place a game event becomes a prompt and a model reply becomes a validated line.

Rules (spec 6.5): structured input only (never student text), E1-selected memory, JSON output
{text, tone} <= 40 words, validation (schema, length, no spoiler, no other teammate's secret),
one retry then an authored fallback, 2 s queue wait, 10 s run limit, 20 calls/min/student quota.
The model never changes game state: this module has no access to the run state beyond read-only facts.
"""
from __future__ import annotations

import json
import random
import re
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field

import httpx

from ..engines import e1
from ..rules.content import Content

EVENT_TYPES = ("ping_clue", "ping_noise", "ping_trap", "help_call", "standup_question", "status_demand")
# Reactions to what the player does (a Daily Scrum answer, a push, an offload...). Each teammate has authored lines for the ones they handle,
# with {item} {trust} {rating} {sprint} {goal} {done} {total} {n_hidden} {next} filled in, and colder lines when trust is below 60.
REACTION_TYPES = ("react_standup_honest", "react_standup_vague", "react_standup_lie", "react_offload_ok", "react_offload_fail", "react_coached",
                  "react_push", "react_review", "react_review_hidden", "sprint_open")
EVENT_DESC = {
    "react_standup_honest": "The player just gave an HONEST Daily Scrum answer. Respond to it.",
    "react_standup_vague": "The player just gave a VAGUE Daily Scrum answer. You can tell they're dodging.",
    "react_standup_lie": "The player just gave an UNTRUE Daily Scrum answer. You suspect it.",
    "react_offload_ok": "The player gave you an item and you finished it.",
    "react_offload_fail": "The player gave you an item and you could not finish it. It went back to them.",
    "react_coached": "The player just coached you through a problem.",
    "react_push": "The player just sent an item to users.",
    "react_review": "The Sprint Review just happened. Comment on the rating and how many items were done.",
    "react_review_hidden": "The Sprint Review just happened and earlier vague or untrue answers turned into harder items for the next Sprint.",
    "sprint_open": "A new Sprint is starting. Open it by stating the Sprint Goal.",
}
TONES = ("calm", "pushy", "panicked")
LOW_TRUST = 60
_TONE_FOR = {"ping_trap": "pushy", "status_demand": "pushy", "help_call": "panicked", "react_standup_vague": "pushy", "react_standup_lie": "pushy",
             "react_offload_fail": "panicked", "react_review_hidden": "pushy"}


class _Facts(dict):
    def __missing__(self, key):
        return "it"
MAX_WORDS = 40
SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}, "tone": {"enum": list(TONES)}},
          "required": ["text", "tone"], "additionalProperties": False}
DOD_TEXT = "Definition of Done: tests pass, matches the doc, no security concern."


@dataclass
class Request:
    event_type: str
    teammate_id: str
    facts: dict = field(default_factory=dict)       # game data only, never student-typed text
    memory: list = field(default_factory=list)       # E1 segments: {id, text, seq, pinned?, stages?}
    stage: str = "BUILD"
    seed: int = 0
    n: int = 0                                       # per-run line counter (for seeded fallback choice)
    user_key: str = "anon"
    forbidden: list = field(default_factory=list)    # correct-patch texts that must not appear


@dataclass
class Line:
    text: str
    tone: str
    source: str                                      # "llm" | "fallback"
    latency_ms: int
    model: str | None = None
    prompt_tokens: int | None = None
    reason: str | None = None


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s.lower())


def _leaks(secret: str, text: str) -> bool:
    """True if the line contains the secret or most of its distinctive words."""
    if _norm(secret) in _norm(text):
        return True
    words = {w for w in re.findall(r"[a-z]+", secret.lower()) if len(w) >= 5}
    got = words & set(re.findall(r"[a-z]+", text.lower()))
    return len(got) >= min(2, len(words))


class ModelError(Exception):
    pass


class HttpModelClient:
    """OpenAI-compatible chat endpoint (llama.cpp llama-server), localhost only."""

    def __init__(self, base_url: str, model: str, transport: httpx.BaseTransport | None = None):
        self.model = model
        self.http = httpx.Client(base_url=base_url, transport=transport, timeout=None)

    def complete(self, messages: list[dict]) -> dict:
        try:
            r = self.http.post("/v1/chat/completions", json={
                "model": self.model, "messages": messages, "temperature": 0.8, "max_tokens": 120,
                "response_format": {"type": "json_schema", "json_schema": {"name": "line", "schema": SCHEMA, "strict": True}}})
            r.raise_for_status()
            body = r.json()
            content = body["choices"][0]["message"]["content"]
            return {"raw": content, "model": body.get("model", self.model),
                    "prompt_tokens": (body.get("usage") or {}).get("prompt_tokens")}
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise ModelError(str(e)) from e


class Gateway:
    def __init__(self, content: Content, client=None, *, slots: int = 4, quota_per_min: int = 20,
                 queue_wait: float = 2.0, run_timeout: float = 10.0, clock=time.monotonic):
        self.content, self.client = content, client
        self.slots = threading.BoundedSemaphore(slots)
        self.quota, self.queue_wait, self.run_timeout, self.clock = quota_per_min, queue_wait, run_timeout, clock
        self._calls: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()
        self._waiting = 0
        self.last_latency_ms: int | None = None
        self.pool = ThreadPoolExecutor(max_workers=max(slots, 1) * 2, thread_name_prefix="model")

    # ------------------------------------------------------------ public
    def status(self) -> dict:
        return {"queue_depth": self._waiting, "last_latency_ms": self.last_latency_ms,
                "model": getattr(self.client, "model", None), "enabled": self.client is not None}

    def generate(self, req: Request) -> Line:
        t0 = self.clock()
        ms = lambda: int((self.clock() - t0) * 1000)  # noqa: E731
        if self.client is None:
            return self._fallback(req, ms(), "no_model")
        if not self._quota_ok(req.user_key):
            return self._fallback(req, ms(), "quota")
        with self._lock:
            self._waiting += 1
        got = self.slots.acquire(timeout=self.queue_wait)
        with self._lock:
            self._waiting -= 1
        if not got:
            return self._fallback(req, ms(), "queue_timeout")
        try:
            for attempt in range(2):
                try:
                    out = self.pool.submit(self.client.complete, self.build_messages(req)).result(timeout=self.run_timeout)
                except FutureTimeout:
                    return self._fallback(req, ms(), "timeout")
                except Exception:  # model down, refused, HTTP error
                    return self._fallback(req, ms(), "model_error")
                bad = self.validate(out.get("raw"), req)
                if bad is None:
                    data = json.loads(out["raw"])
                    lat = ms()
                    self.last_latency_ms = lat
                    return Line(data["text"].strip(), data["tone"], "llm", lat, out.get("model"), out.get("prompt_tokens"))
            return self._fallback(req, ms(), f"invalid:{bad}")
        finally:
            self.slots.release()

    # ------------------------------------------------------------ pieces
    def _quota_ok(self, key: str) -> bool:
        now = self.clock()
        with self._lock:
            q = self._calls[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.quota:
                return False
            q.append(now)
            return True

    def persona(self, tid: str) -> dict:
        return self.content.teammates[tid]

    def build_messages(self, req: Request) -> list[dict]:
        p = self.persona(req.teammate_id)
        others = [t["secret"] for k, t in self.content.teammates.items() if k != req.teammate_id]
        system = (f"You are {p['name']}, {p['role']} at a failing company. Voice: {p['voice']} "
                  f"Example line: \"{p['example_line']}\" Reply as JSON only: {{\"text\": string, \"tone\": \"calm\"|\"pushy\"|\"panicked\"}}. "
                  f"At most {MAX_WORDS} words. Stay in character. Never state the correct code fix. "
                  f"Never mention or hint at these secrets: {'; '.join(others)}.")
        segs = e1.select_segments([{"id": "persona", "text": system, "seq": 0, "pinned": True},
                                   {"id": "dod", "text": DOD_TEXT, "seq": 0, "pinned": True}] + req.memory, req.stage)
        memory = "\n".join(s["text"] for s in segs if not s.get("pinned"))
        desc = EVENT_DESC.get(req.event_type)
        mood = ("Your trust in the player is in facts.trust (a percent). Below 60 sound cold, short or annoyed; 80 or more, sound warm. "
                "Use the specific facts (item names, numbers) in what you say. " if desc else "")
        user = (f"Event: {req.event_type}\n" + (f"Situation: {desc}\n" if desc else "") + (mood if mood else "")
                + f"Facts: {json.dumps(req.facts, sort_keys=True)}\nRemembered:\n{memory or '(nothing)'}")
        return [{"role": "system", "content": system + "\n" + DOD_TEXT}, {"role": "user", "content": user}]

    def validate(self, raw, req: Request) -> str | None:
        """Return None if the line is acceptable, else a short reason."""
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return "json"
        if not isinstance(data, dict) or set(data) != {"text", "tone"} or data["tone"] not in TONES or not isinstance(data["text"], str):
            return "schema"
        text = data["text"]
        if not text.strip() or len(text.split()) > MAX_WORDS:
            return "length"
        n = _norm(text)
        if any(_norm(f) and _norm(f) in n for f in req.forbidden):
            return "spoiler"
        for k, t in self.content.teammates.items():
            if k != req.teammate_id and _leaks(t["secret"], text):
                return "secret"
        return None

    def _fallback(self, req: Request, latency: int, reason: str) -> Line:
        p = self.persona(req.teammate_id)
        low = req.facts.get("trust", 100) < LOW_TRUST
        pool = None
        if req.event_type in REACTION_TYPES:
            pool = (p.get("reactions_low", {}).get(req.event_type) if low else None) or p.get("reactions", {}).get(req.event_type)
        pool = pool or p["fallback_lines"][req.event_type]
        rnd = random.Random(f"{req.seed}:fallback:{req.teammate_id}:{req.event_type}:{req.n}")
        tone = _TONE_FOR.get(req.event_type, "calm")
        if low and req.event_type in REACTION_TYPES:
            tone = "panicked" if req.teammate_id == "dev2" else "pushy"   # cold when trust is low
        text = rnd.choice(pool)
        try:
            text = text.format_map(_Facts(req.facts))
        except (ValueError, IndexError):
            pass
        return Line(text, tone, "fallback", latency, reason=reason)
