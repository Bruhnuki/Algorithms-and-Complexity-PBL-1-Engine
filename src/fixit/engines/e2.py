"""E2 for the game: the process score and the learning gain, the latter run by the real `pbl_engine` (normalized gain, bootstrap interval,
saturating process accumulator).

`process_score` is the game's own linear score and stays what players and the Grade use (so balance does not move). The engine's saturating
accumulator runs next to it on the same behaviour log (`saturating`), and the instructor sees both.
"""
from __future__ import annotations

import time

from . import real

# The engine's categories for the game's good behaviours: equal weights, and each event closes a fraction `eta` of the remaining distance to the full mark.
CATEGORIES = {k: {"weight": 0.2, "eta": 0.3} for k in ("standup_held", "blocker_cleared", "coach", "dod_honest", "review_before_push")}
STAGE_OF = {"standup_held": "STANDUP", "blocker_cleared": "BUILD", "coach": "BUILD", "dod_honest": "BUILD", "review_before_push": "REVIEW"}


def process_score(log: list[str], weights: dict) -> int:
    cap = weights["max_per_behaviour"]
    total = 0
    for key in ("standup_held", "blocker_cleared", "coach", "dod_honest", "dod_skipped", "dod_dishonest", "review_before_push"):
        total += weights[key] * min(log.count(key), cap)
    return max(0, min(100, total))


def saturating(log: list[str]) -> dict:
    """The engine's ProcessAccumulator over a run's behaviour log: the score after each good behaviour (never negative, never above 100)."""
    t0 = time.perf_counter()
    acc, curve = real.lg.ProcessAccumulator(CATEGORIES), []
    for i, key in enumerate(k for k in log if k in CATEGORIES):
        acc.record(f"e{i}", STAGE_OF[key], key, 1.0)
        curve.append(round(acc.score(), 3))
    real.record("E2", "process_accumulator", t0, events=len(curve), score=round(acc.score(), 3), source="game")
    return {"score": round(acc.score(), 3), "curve": curve, "by_stage": {k: round(v, 3) for k, v in acc.stage_points.items()}}


def learning_gain(pre: list[float], post: list[float], seed: int = 0, n_boot: int = 1000) -> dict:
    """Mean normalized gain with a 95% bootstrap interval, from the engine. pre/post are per-student scores in [0,1]."""
    students = [{"pre": a, "post": b} for a, b in zip(pre, post)]
    if not students:
        return {"mean": 0.0, "low": 0.0, "high": 0.0, "n": 0}
    t0 = time.perf_counter()
    r = real.lg.cohort_summary(students, 1.0, B=n_boot, seed=seed)
    real.record("E2", "cohort_summary", t0, students=len(students), bootstrap=n_boot, source="game")
    ci = r["ci95"] or [0.0, 0.0]
    return {"mean": r["mean_individual_gain"] or 0.0, "low": ci[0], "high": ci[1], "n": len(students), "class_gain": r["class_gain"], "warnings": r["warnings"]}
