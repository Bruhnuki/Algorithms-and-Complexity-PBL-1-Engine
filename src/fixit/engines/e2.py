"""E2 stand-in: process score and learning gain with bootstrap interval (deterministic by seed)."""
from __future__ import annotations

import random
import statistics


def process_score(log: list[str], weights: dict) -> int:
    cap = weights["max_per_behaviour"]
    total = 0
    for key in ("standup_held", "blocker_cleared", "coach", "dod_honest", "dod_skipped", "dod_dishonest", "review_before_push"):
        total += weights[key] * min(log.count(key), cap)
    return max(0, min(100, total))


def learning_gain(pre: list[float], post: list[float], seed: int = 0, n_boot: int = 1000) -> dict:
    """Mean paired gain with a 95% bootstrap interval. pre/post are per-student scores in [0,1]."""
    gains = [b - a for a, b in zip(pre, post)]
    if not gains:
        return {"mean": 0.0, "low": 0.0, "high": 0.0, "n": 0}
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(gains, k=len(gains))) for _ in range(n_boot))
    return {"mean": statistics.fmean(gains), "low": means[int(0.025 * n_boot)], "high": means[int(0.975 * n_boot) - 1], "n": len(gains)}
