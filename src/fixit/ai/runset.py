"""A fresh set of AI-written problems for each run, written while the player is still in Sprint 1.

The set is made in the background, saved to the library like any other item, and handed to the run as a server-only `ai_set` command
(stored in the run's log, so a replay deals the same Sprints). It only affects Sprints dealt after it arrives, so nothing the player
is looking at ever changes. If the AI is slow or down the run simply keeps what it already has.
"""
from __future__ import annotations

import queue
import threading

from .generator import Generator

# What a run gets: (kind, level). Sprint 2 draws from level <= 2 and Sprint 3 from level <= 3 (see reducer._g_deal_sprint / _g_pick_help).
PLAN = [("challenge", 2), ("challenge", 2), ("challenge", 3), ("scenario", 2), ("challenge", 3), ("scenario", 3), ("challenge", 2), ("challenge", 3),
        ("quiz", 2), ("quiz", 3), ("quiz", 2), ("quiz", 3), ("quiz", 2), ("quiz", 3)]   # quiz: a new wording of a Sprint 2 or 3 Scrum question
ATTEMPTS = 3   # tries per slot; the validators drop about a third of what the model writes


class RunSets:
    def __init__(self, gen: Generator, plan=PLAN):
        self.gen, self.plan = gen, plan
        self.state: dict[int, dict] = {}
        self.q: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        threading.Thread(target=self._work, daemon=True, name="ai-runsets").start()

    def enqueue(self, run_id: int, seed: int) -> None:
        with self._lock:
            self.state[run_id] = {"status": "building", "made": 0, "target": len(self.plan), "pending": [], "ids": []}
        self.q.put((run_id, seed))

    def _work(self) -> None:
        while True:
            run_id, seed = self.q.get()
            st = self.state[run_id]
            for slot, (kind, level) in enumerate(self.plan):
                got = None
                for attempt in range(ATTEMPTS):
                    item, why = self.gen.make(kind, seed=seed * 1000 + slot * 10 + attempt, level=level)
                    if item:
                        got = item
                        break
                    if why.startswith("ai_"):   # the AI is down or busy: stop, the run keeps what it has
                        break
                if got is None:
                    if why.startswith("ai_"):
                        break
                    continue
                ids = [got["id"]] + ([got["ticket"]] if got.get("ticket") else [])   # a quiz question is just its own id
                with self._lock:
                    st["made"] += 1
                    st["pending"] += ids
                    st["ids"] += ids
            st["status"] = "ready" if st["made"] else "unavailable"

    def take_pending(self, run_id: int) -> list[str]:
        with self._lock:
            st = self.state.get(run_id)
            if not st or not st["pending"]:
                return []
            ids, st["pending"] = st["pending"], []
            return ids

    def put_back(self, run_id: int, ids: list[str]) -> None:
        with self._lock:
            if run_id in self.state:
                self.state[run_id]["pending"] = ids + self.state[run_id]["pending"]

    def status(self, run_id: int) -> dict | None:
        st = self.state.get(run_id)
        return {"status": st["status"], "made": st["made"], "target": st["target"]} if st else None
