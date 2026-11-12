"""Make one validated item (or say why not) and keep the library topped up in the background."""
from __future__ import annotations

import json
import random
import threading
import time
from collections import Counter

from ..rules.content import Content
from . import prompts, prompts_template, templated, validate
from .client import AiClient, AiError
from .library import Library

SCHEMAS = {"scenario": validate.SCENARIO_SCHEMA, "challenge": validate.CHALLENGE_SCHEMA}


class Generator:
    def __init__(self, client: AiClient, content: Content, library: Library, *, judge: bool = True, temperature: float = 0.8, model: str | None = None, max_level: int = 3, priority: str = "background"):
        self.client, self.content, self.lib, self.judge, self.temperature, self.model, self.max_level, self.priority = client, content, library, judge, temperature, model, max_level, priority
        self.stats = {"attempts": 0, "accepted": 0, "json_invalid": 0, "errors": 0, "rejected": Counter(), "latency_ms": [], "tokens_per_s": [], "completion_tokens": []}
        self._lock = threading.Lock()

    def _ask(self, messages, schema, seed, max_tokens, temperature) -> tuple[object | None, dict]:
        out = self.client.generate(messages, schema, priority=self.priority, max_tokens=max_tokens, temperature=temperature, seed=seed, model=self.model)
        u = out.get("usage", {})
        with self._lock:
            self.stats["latency_ms"].append(u.get("total_ms") or 0)
            self.stats["tokens_per_s"].append(u.get("tokens_per_s") or 0)
            self.stats["completion_tokens"].append(u.get("completion_tokens") or 0)
        try:
            return json.loads(out["content"]), u
        except (ValueError, KeyError):
            with self._lock:
                self.stats["json_invalid"] += 1
            return None, u

    def make(self, kind: str, seed: int | None = None, save: bool = True, level: int | None = None, beat: dict | None = None, product: str | None = None) -> tuple[dict | None, str]:
        """-> (item or None, reason). Never raises."""
        seed = int(time.time() * 1000) % 2**31 if seed is None else seed
        rnd = random.Random(seed)
        texts = self.lib.texts()[kind] + ([self._beat_text(b) for b in self.content.guide.get("beats", []) if b["kind"] == "quiz"] if kind == "quiz"
                                          else [self._authored_text(h) for h in self.content.help.values() if h["type"] == kind and not h.get("generated")])
        with self._lock:
            self.stats["attempts"] += 1
        raw = None
        try:
            if kind == "scenario":
                spec = prompts.scenario_spec(self.content, rnd, level or self.max_level, level or 1)
                raw, _ = self._ask(prompts.scenario_messages(self.content, spec), validate.SCENARIO_SCHEMA, seed, 520, self.temperature)
                item, why = validate.validate_scenario(raw, spec, self.content, texts) if raw is not None else (None, "json_invalid")
                if item and self.judge:
                    verdict, _ = self._ask(prompts.judge_messages(item, spec), validate.JUDGE_SCHEMA, seed, 30, 0.0)
                    if not validate.judge_agrees(item, verdict):
                        item, why = None, "judge_disagrees"
                pair = (item, None)
            elif kind == "quiz":
                quizzes = [b for b in self.content.guide.get("beats", []) if b["kind"] == "quiz" and b.get("teach")]
                beat = beat or rnd.choice([b for b in quizzes if (b["sprint"] == level if level else True)] or quizzes)
                spec = {**prompts.quiz_spec(self.content, rnd, beat), **({"product": product} if product else {})}
                raw, _ = self._ask(prompts.quiz_messages(self.content, spec), validate.QUIZ_SCHEMA, seed, 560, self.temperature)
                item, why = validate.validate_quiz(raw, spec, self.content, texts) if raw is not None else (None, "json_invalid")
                if item and self.judge:
                    verdict, _ = self._ask(prompts.judge_quiz_messages(item, spec), validate.JUDGE_SCHEMA, seed, 30, 0.0)
                    if not validate.judge_agrees_quiz(item, verdict):
                        item, why = None, "judge_disagrees"
                pair = (item, None)
            else:
                spec = prompts.challenge_spec(self.content, rnd, level or self.max_level, level or 1)
                raw, _ = self._ask(prompts.challenge_messages(self.content, spec), validate.CHALLENGE_SCHEMA, seed, 700, 0.5)
                got, why = validate.validate_challenge(raw, spec, self.content, texts) if raw is not None else (None, "json_invalid")
                pair = (got[1], got[0]) if got else (None, None)
                item = pair[0]
        except AiError as e:
            with self._lock:
                self.stats["errors"] += 1
            return None, f"ai_{e.code}"
        if item is None:
            with self._lock:
                self.stats["rejected"][why] += 1
            self.lib.audit(kind, why, raw if isinstance(raw, dict) else None)
            return None, why
        if save:
            if kind == "quiz":
                self.lib.add_beat(item)
            else:
                self.lib.add(item, pair[1])
            self.lib.merge_into(self.content)
        with self._lock:
            self.stats["accepted"] += 1
        return item, "ok"

    # ---- pieces of an AI-written project (see pack.py); they are not saved one by one, the project is saved whole
    def outline(self, n: int, seed: int) -> tuple[dict | None, str]:
        spec = prompts.outline_spec(n, random.Random(seed))
        titles = [p["premise"]["title"] for p in self.content.packs.values()] + [self.content.guide["premise"]["title"]]
        return self._piece("outline", lambda: self._ask(prompts.outline_messages(self.content, spec), validate.OUTLINE_SCHEMA, seed, 450, 0.9),
                           lambda raw: validate.validate_outline(raw, spec, titles))

    def ticket(self, theme: str, level: int, product: str, seed: int, avoid: list[str] | None = None) -> tuple[tuple[dict, dict] | None, str]:
        """-> ((ticket, help_request), reason) for a puzzle themed to a Sprint of a project."""
        rnd = random.Random(seed)
        spec = {"theme": theme, "product": product, "level": level, "shape": rnd.choice(templated.SHAPES[min(3, max(2, level))])}
        return self._piece("challenge", lambda: self._ask(prompts_template.template_messages(self.content, spec), templated.TEMPLATE_SCHEMA, seed, 260, 0.8),
                           lambda raw: templated.validate_templated(raw, spec, self.content, list(avoid or [])))

    def quiz(self, beat: dict, product: str, seed: int) -> tuple[dict | None, str]:
        item, why = self.make("quiz", seed=seed, save=False, beat=beat, product=product)
        return item, why

    def _piece(self, kind, ask, check):
        with self._lock:
            self.stats["attempts"] += 1
        raw = None
        try:
            raw, _ = ask()
            got, why = check(raw) if raw is not None else (None, "json_invalid")
        except AiError as e:
            with self._lock:
                self.stats["errors"] += 1
            return None, f"ai_{e.code}"
        with self._lock:
            if got:
                self.stats["accepted"] += 1
            else:
                self.stats["rejected"][why] += 1
        if not got:
            self.lib.audit(kind, why, raw if isinstance(raw, dict) else None)
        return got, why

    @staticmethod
    def _beat_text(b: dict) -> str:
        return " ".join([b.get("scene", ""), b.get("question", ""), *(c["text"] for c in b.get("choices", []))])

    @staticmethod
    def _authored_text(h: dict) -> str:
        return " ".join([h["title"], *(h.get("prompts") or {}).values(), *(a["text"] for a in h.get("answers", []))])

    def run_forever(self, stop: threading.Event, targets: dict[str, int] | None = None, pause_s: float = 2.0) -> None:
        """One request at a time, lowest priority, backing off while the server is down or busy. The game never waits on this."""
        targets = targets or {"scenario": 30, "challenge": 15, "quiz": 36}
        delay = pause_s
        while not stop.is_set():
            have = {**self.lib.count(), "quiz": len(self.lib.beat_items())}
            need = [k for k in targets if have[k] < targets[k]]
            if not need:
                stop.wait(60)
                continue
            _, why = self.make(min(need, key=lambda k: have[k] / targets[k]))
            delay = min(delay * 2, 300) if why.startswith("ai_") else pause_s
            stop.wait(delay)
