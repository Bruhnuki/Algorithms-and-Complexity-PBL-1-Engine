"""An AI-written project ("pack"): story, three Sprints of themed puzzles, quiz questions and hidden-problem tickets.

A pack is written piece by piece (each piece checked by the same validators as everything else), saved whole and never edited afterwards,
so a run that froze its id always replays the same Sprints. `merge_guide` turns a pack into the full guide a run plays.
"""
from __future__ import annotations

import threading

from . import validate
from .client import AiError

TICKETS_PER_SPRINT = 5
MIN_TICKETS = 4      # a Sprint with fewer than this is not a Sprint: the pack is dropped and tried again later
HARD_TICKETS = 3
ATTEMPTS = 3


def merge_guide(base: dict, pack: dict) -> dict:
    """The authored guide with this project's story, Sprints, hidden problems and quiz wordings put in. Retro choices, the summary text and the
    tutorial stay authored. A quiz the pack did not rewrite keeps its authored wording."""
    swaps = {b["for_beat"]: b for b in pack["beats"]}
    return {**base, "project_n": pack["n"], "pack_id": pack["id"],
            "premise": {"title": pack["title"], "lines": pack["premise"]},
            "sprints": {k: {"theme": sp["theme"], "goal": sp["goal"], "tickets": sp["tickets"], "backlog_more": [], "goal_ship_min": sp.get("goal_ship_min", 2),
                            "help_calls": 1, "ai_tickets": 0} for k, sp in pack["sprints"].items()},
            "hard_pool": pack["hard_pool"],
            "beats": [swaps.get(b["id"], b) for b in base["beats"]]}


class _Interrupted(Exception):
    pass


class PackBuilder:
    def __init__(self, gen, library, content):
        self.gen, self.lib, self.content = gen, library, content

    def target(self) -> int:
        quizzes = sum(1 for b in self.content.guide["beats"] if b["kind"] == "quiz" and b.get("teach"))
        return 1 + 3 * TICKETS_PER_SPRINT + HARD_TICKETS + quizzes

    def build(self, n: int, seed: int, progress=lambda made, target, stage: None, save: bool = True, stop=lambda: False) -> tuple[dict | None, str]:
        """-> (pack, "ok") or (None, reason). Never raises; stops at once when the AI server is not available."""
        target, made = self.target(), 0
        _progress = progress

        def progress(made, target, stage):   # every step is also a chance to give way to a player who is waiting
            _progress(made, target, stage)
            if stop():
                raise _Interrupted()
        try:
            outline = None
            for a in range(ATTEMPTS + 1):
                outline, why = self.gen.outline(n, seed * 31 + a)
                if outline or why.startswith("ai_"):
                    break
            if not outline:
                return None, why
            made += 1
            progress(made, target, "story")
            product, tickets, sprints, seen = outline["title"], [], {}, []
            for k, sp in enumerate(outline["sprints"], 1):
                level, ids = min(3, n + (1 if k == 3 else 0)), []
                for slot in range(TICKETS_PER_SPRINT):
                    got = None
                    for a in range(ATTEMPTS):
                        got, why = self.gen.ticket(sp["theme"], level, product, seed * 1000 + k * 100 + slot * 10 + a, seen)
                        if got or why.startswith("ai_"):
                            break
                    if why.startswith("ai_") and not got:
                        return None, why
                    if got:
                        t = got[0]
                        tickets.append(t)
                        ids.append(t["id"])
                        seen.append(f"{t['title']} {t['doc']}")
                        made += 1
                        progress(made, target, f"sprint {k}")
                if len(ids) < MIN_TICKETS:
                    return None, "too_few_tickets"
                sprints[str(k)] = {"theme": sp["theme"], "goal": sp["goal"], "tickets": ids, "goal_ship_min": 2}
            hard = []
            for slot in range(HARD_TICKETS):
                theme = outline["sprints"][(slot + 1) % 3]["theme"]
                for a in range(ATTEMPTS):
                    got, why = self.gen.ticket(theme, 3, product, seed * 1000 + 900 + slot * 10 + a, seen)
                    if got or why.startswith("ai_"):
                        break
                if why.startswith("ai_") and not got:
                    return None, why
                if got:
                    tickets.append(got[0])
                    hard.append(got[0]["id"])
                    seen.append(f"{got[0]['title']} {got[0]['doc']}")
                    made += 1
                    progress(made, target, "hidden problems")
            if not hard:
                return None, "no_hidden_problems"
            beats = []
            for b in [b for b in self.content.guide["beats"] if b["kind"] == "quiz" and b.get("teach")]:
                for a in range(2):
                    item, why = self.gen.quiz(b, product, seed * 1000 + 950 + a + len(beats) * 3)
                    if item or why.startswith("ai_"):
                        break
                if why.startswith("ai_") and not item:
                    return None, why
                if item:
                    beats.append(item)
                made += 1                                   # a question that failed twice keeps its authored wording; the step still counts
                progress(made, target, "questions")
        except _Interrupted:
            return None, "interrupted"
        except AiError as e:                                # the generator turns these into reasons; this is only a safety net
            return None, f"ai_{e.code}"
        pack = {"id": validate.short_id("proj_gen", str(n), product, outline["premise"][0]), "n": n, "title": product, "premise": outline["premise"],
                "sprints": sprints, "beats": beats, "hard_pool": hard, "generated": True, "level": n}
        if save:
            self.lib.add_pack(pack, tickets)
            self.lib.merge_into(self.content)
        return pack, "ok"


class ProjectJobs:
    """Builds a player's next projects in the background while they play, one at a time (the GPU is shared). In memory only: a pack is on disk once
    finished. When nobody is waiting it also keeps a few spare projects per level in the library, so a player whose own project is late still gets one."""

    def __init__(self, builder: PackBuilder, spare: int = 2, idle_s: float = 20.0):
        import queue
        self.builder, self.q, self.state, self.spare, self.idle_s = builder, queue.Queue(), {}, spare, idle_s
        self.excluded: dict[int, set[str]] = {}
        self._lock = threading.Lock()
        threading.Thread(target=self._work, daemon=True, name="ai-projects").start()

    def reset(self, user_id: int, seed: int) -> None:
        """Developer reset: forget this player's projects and write new ones now. The projects that exist already are hidden from them until their new ones are
        ready, so the writing (and its progress bar) can be watched from the start."""
        with self._lock:
            self.excluded[user_id] = {g["pack_id"] for g in self.builder.content.packs.values()}
            for n in (2, 3):
                self.state.pop((user_id, n), None)
        self.enqueue(user_id, seed)

    def enqueue(self, user_id: int, seed: int, levels=(2, 3)) -> None:
        with self._lock:
            for n in levels:
                cur = self.state.get((user_id, n))
                if cur is None or cur["status"] == "failed":
                    self.state[(user_id, n)] = {"status": "building", "made": 0, "target": self.builder.target(), "stage": "queued", "pack": None, "reason": None}
                    self.q.put((user_id, n, seed))

    def _build(self, n: int, seed: int, progress, stop=lambda: False) -> tuple[dict | None, str]:
        pack, why = None, "error"
        for a in range(2):                                  # a second try with another seed when the first draft fell short
            try:
                pack, why = self.builder.build(n, seed * 7 + n * 13 + a, progress, stop=stop)
            except Exception as e:   # noqa: BLE001  (a bug here must never take the worker down)
                pack, why = None, f"error:{type(e).__name__}"
            if pack or why.startswith("ai_") or why == "interrupted":
                break
        return pack, why

    def _work(self) -> None:
        import queue
        import random
        import time
        pause = 0.0
        while True:
            try:
                user_id, n, seed = self.q.get(timeout=self.idle_s)
            except queue.Empty:
                have = {k: 0 for k in (2, 3)}
                for g in self.builder.content.packs.values():
                    have[g["project_n"]] = have.get(g["project_n"], 0) + 1
                need = [k for k in (2, 3) if have[k] < self.spare]
                if need and self.spare and time.time() >= pause:
                    pack, why = self._build(min(need, key=lambda k: have[k]), random.randrange(2 ** 20), lambda *a: None, stop=lambda: not self.q.empty())   # a waiting player goes first
                    pause = time.time() + (0 if pack or why == "interrupted" else 300)   # AI down or the draft failed: wait before trying again
                continue
            st = self.state[(user_id, n)]

            def progress(made, target, stage, st=st):
                st.update(made=made, target=target, stage=stage)
            pack, why = self._build(n, seed, progress)
            with self._lock:
                st.update(status="ready" if pack else "failed", pack=pack["id"] if pack else None, reason=None if pack else why)

    def status(self, user_id: int, n: int) -> dict | None:
        return self.state.get((user_id, n))
