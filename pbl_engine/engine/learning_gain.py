"""Engine 2: normalized learning gain + saturating process-point accumulator.

- normalized_gain: Hake gain for improvement, Marx-Cummings change for losses.
- bootstrap_ci: seeded percentile bootstrap for the mean gain, O(L*N).
- ProcessAccumulator: per-category saturating recurrence  A <- A + eta*q*(1 - A),
  O(1) per event, with per-stage point buckets (no tree needed).
"""
import math
import random

from .context_chaining import STAGES


def normalized_gain(pre, post, max_score):
    """g = (post-pre)/(M-pre) if post >= pre; c = (post-pre)/pre if post < pre.

    Returns None only for the ceiling case pre == post == M (no information).
    The result always lies in [-1, 1].
    """
    if not (max_score > 0 and math.isfinite(max_score)):
        raise ValueError("max_score must be positive and finite")
    if not (0 <= pre <= max_score and 0 <= post <= max_score):
        raise ValueError("scores must lie in [0, max_score]")
    if pre == max_score and post == max_score:
        return None
    if post >= pre:
        return (post - pre) / (max_score - pre)   # pre < M here, denominator > 0
    return (post - pre) / pre                     # post < pre implies pre > 0


def bootstrap_ci(values, B=1000, alpha=0.05, seed=0):
    if not values:
        return None
    if B < 1:
        raise ValueError("B must be >= 1")
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(rng.choice(values) for _ in range(n)) / n for _ in range(B))
    lo = means[int((alpha / 2) * B)]
    hi = means[min(B - 1, int((1 - alpha / 2) * B))]
    return (lo, hi)


def cohort_summary(students, max_score, B=1000, seed=0):
    gains, skipped = [], 0
    for s in students:
        g = normalized_gain(s["pre"], s["post"], max_score)
        if g is None:
            skipped += 1
        else:
            gains.append(g)
    n = len(students)
    class_gain = None
    if n:
        mean_pre = min(max(sum(s["pre"] for s in students) / n, 0.0), max_score)
        mean_post = min(max(sum(s["post"] for s in students) / n, 0.0), max_score)
        class_gain = normalized_gain(mean_pre, mean_post, max_score)
    ci = bootstrap_ci(gains, B, 0.05, seed)
    warnings = []
    if n == 0:
        warnings.append("empty_cohort")
    elif len(gains) < 5:
        warnings.append("small_sample_ci_unreliable")
    if skipped:
        warnings.append("undefined_gain_excluded")
    return {
        "n_students": n,
        "n_undefined": skipped,
        "mean_individual_gain": sum(gains) / len(gains) if gains else None,
        "class_gain": class_gain,
        "ci95": list(ci) if ci else None,
        "effect_detected": (ci[0] > 0) if ci else None,
        "warnings": warnings,
    }


class ProcessAccumulator:
    """Saturating accumulator per behavior category, with per-stage point buckets.

    categories: {name: {"weight": w >= 0 (sum to 1), "eta": e in (0, 1]}}
    Event (id, stage, category, quality q in [0, 1]) updates  A_c <- A_c + eta_c*q*(1-A_c).
    Process score = 100 * sum_c w_c * A_c  (in [0, 100]); the points an event adds are
    credited to the stage where it occurred, so  sum(stage buckets) == process score.
    Duplicate event ids are ignored (idempotent).
    """

    def __init__(self, categories):
        if not isinstance(categories, dict) or not categories:
            raise ValueError("categories must be a non-empty object")
        total = 0.0
        for name, cfg in categories.items():
            w, e = cfg["weight"], cfg["eta"]
            if isinstance(w, bool) or isinstance(e, bool) or not all(
                    isinstance(x, (int, float)) and math.isfinite(x) for x in (w, e)):
                raise ValueError(f"category {name!r}: weight and eta must be finite numbers")
            if w < 0 or not (0 < e <= 1):
                raise ValueError(f"category {name!r}: need weight >= 0 and 0 < eta <= 1")
            total += w
        if abs(total - 1.0) > 1e-9:
            raise ValueError("category weights must sum to 1")
        self.cfg = categories
        self.A = {c: 0.0 for c in categories}
        self.stage_points = {s: 0.0 for s in STAGES}
        self.seen = set()
        self.duplicates = 0
        self.applied = 0

    def record(self, event_id, stage, category, quality):
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("event id must be a non-empty string")
        if stage not in STAGES:
            raise ValueError(f"unknown stage: {stage!r}")
        if category not in self.cfg:
            raise ValueError(f"unknown category: {category!r}")
        if (isinstance(quality, bool) or not isinstance(quality, (int, float))
                or not math.isfinite(quality) or not 0 <= quality <= 1):
            raise ValueError("quality must be a finite number in [0, 1]")
        if event_id in self.seen:
            self.duplicates += 1
            return 0.0
        self.seen.add(event_id)
        a = self.A[category]
        delta = self.cfg[category]["eta"] * quality * (1.0 - a)
        self.A[category] = a + delta
        pts = 100.0 * self.cfg[category]["weight"] * delta
        self.stage_points[stage] += pts
        self.applied += 1
        return pts

    def score(self):
        return 100.0 * sum(self.cfg[c]["weight"] * a for c, a in self.A.items())


def process_summary(categories, events):
    acc = ProcessAccumulator(categories)
    for e in events:
        acc.record(e["id"], e["stage"], e["category"], e["quality"])
    return {
        "process_score": round(acc.score(), 6),
        "by_category": {c: round(a, 6) for c, a in acc.A.items()},
        "by_stage": {s: round(p, 6) for s, p in acc.stage_points.items()},
        "events_applied": acc.applied,
        "duplicates_ignored": acc.duplicates,
    }
