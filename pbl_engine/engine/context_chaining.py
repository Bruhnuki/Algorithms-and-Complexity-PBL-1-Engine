"""Engine 1: Context window chaining with a stage state machine.

Problem: choose which past transcript segments to put in an agent's context window so
total relevance is maximised without exceeding a token budget B (a 0/1 knapsack).
The state machine restricts which segments are eligible at each sprint stage.

Selection policy (mode="auto"):
  * exact dynamic programme, O(m*R) time, when the estimated number of DP cells is
    at most MAX_EXACT_CELLS (about 0.15 s in pure Python);
  * density greedy with best singleton otherwise, O(m log m), with a verifiable
    additive optimality-gap bound in the certificate.
"""
import math
from dataclasses import dataclass

STAGES = ("PLANNING", "STANDUP", "BUILD", "REVIEW")

# Legal stage transitions (BUILD <-> STANDUP loops across a two-day run).
TRANSITIONS = {
    "PLANNING": {"STANDUP"},
    "STANDUP": {"BUILD"},
    "BUILD": {"STANDUP", "REVIEW"},
    "REVIEW": set(),
}

# Segments from which stages may enter the context at each stage.
ELIGIBLE = {
    "PLANNING": {"PLANNING"},
    "STANDUP": {"PLANNING", "STANDUP", "BUILD"},
    "BUILD": {"PLANNING", "STANDUP", "BUILD"},
    "REVIEW": {"PLANNING", "STANDUP", "BUILD", "REVIEW"},
}

MAX_EXACT_CELLS = 2_000_000


class InfeasibleError(ValueError):
    """Pinned segments alone exceed the token budget."""


class IllegalTransitionError(ValueError):
    """Requested stage change is not an edge of the state machine."""


@dataclass(frozen=True)
class Segment:
    id: str
    tokens: int
    relevance: float
    stage: str
    pinned: bool = False  # e.g. Definition of Done: always included


def advance(current: str, target: str) -> str:
    """State machine step. Raises ValueError on an illegal transition."""
    if current not in TRANSITIONS or target not in STAGES:
        raise ValueError(f"unknown stage: {current!r} -> {target!r}")
    if target not in TRANSITIONS[current]:
        raise IllegalTransitionError(f"illegal transition {current} -> {target}")
    return target


def _validate(segments, budget, stage):
    if stage not in STAGES:
        raise ValueError(f"unknown stage: {stage!r}")
    if isinstance(budget, bool) or not isinstance(budget, int) or budget < 0:
        raise ValueError("token_budget must be a non-negative integer")
    seen = set()
    for s in segments:
        if s.id in seen:
            raise ValueError(f"duplicate segment id: {s.id!r}")
        seen.add(s.id)
        if s.stage not in STAGES:
            raise ValueError(f"segment {s.id}: unknown stage {s.stage!r}")
        if isinstance(s.tokens, bool) or not isinstance(s.tokens, int) or s.tokens <= 0:
            raise ValueError(f"segment {s.id}: tokens must be a positive integer")
        if not math.isfinite(s.relevance) or s.relevance < 0:
            raise ValueError(f"segment {s.id}: relevance must be finite and >= 0")


def _plan(segments, budget, current_stage):
    """Validate, set aside pinned segments, and return (pinned, R, candidates)."""
    _validate(segments, budget, current_stage)
    pinned = [s for s in segments if s.pinned]
    pinned_tokens = sum(s.tokens for s in pinned)
    if pinned_tokens > budget:
        raise InfeasibleError("pinned segments alone exceed the token budget")
    R = budget - pinned_tokens
    cands = [s for s in segments
             if not s.pinned and s.stage in ELIGIBLE[current_stage] and s.tokens <= R]
    return pinned, R, cands


def _assemble(segments, pinned, chosen, cands, extra):
    ids = {s.id for s in pinned} | {s.id for s in chosen}
    ordered = [s for s in segments if s.id in ids]  # chronological order
    res = {
        "selected_segment_ids": [s.id for s in ordered],
        "total_relevance": round(sum(s.relevance for s in ordered), 6),
        "tokens_used": sum(s.tokens for s in ordered),
        "candidates": len(cands),
    }
    res.update(extra)
    return res


def estimate_cells(segments, budget, current_stage):
    """Number of DP cells the exact mode would evaluate: sum(R - c_i + 1)."""
    _, R, cands = _plan(segments, budget, current_stage)
    return sum(R - s.tokens + 1 for s in cands)


def select_segments(segments, budget, current_stage):
    """Exact mode: max-relevance eligible subset that fits in `budget` tokens (DP)."""
    pinned, R, cands = _plan(segments, budget, current_stage)

    # DP over capacity; keep[i][b] records whether item i was taken at capacity b.
    dp = [0.0] * (R + 1)
    keep = []
    cells = 0
    for s in cands:
        cells += R - s.tokens + 1
        row = bytearray(R + 1)
        for b in range(R, s.tokens - 1, -1):
            val = dp[b - s.tokens] + s.relevance
            if val > dp[b]:
                dp[b] = val
                row[b] = 1
        keep.append(row)

    chosen, b = [], R
    for i in range(len(cands) - 1, -1, -1):
        if keep[i][b]:
            chosen.append(cands[i])
            b -= cands[i].tokens
    return _assemble(segments, pinned, chosen, cands, {"dp_cells": cells, "mode": "exact"})


def select_segments_greedy(segments, budget, current_stage):
    """Greedy mode: density order (relevance/token) plus the best single segment.

    Certificate field `abs_gap_bound` satisfies  OPT - V <= abs_gap_bound  (also 0 if
    every candidate fits). Proof: the fractional relaxation is at most
    v(prefix) + v_k, where k is the first candidate in density order that does not fit.
    """
    pinned, R, cands = _plan(segments, budget, current_stage)
    order = sorted(cands, key=lambda s: -(s.relevance / s.tokens))  # stable: ties chronological
    used, chosen, first_miss = 0, [], None
    for s in order:
        if used + s.tokens <= R:
            chosen.append(s)
            used += s.tokens
        elif first_miss is None:
            first_miss = s
    value = sum(s.relevance for s in chosen)
    if cands:
        best = max(cands, key=lambda s: s.relevance)
        if best.relevance > value:
            chosen, value = [best], best.relevance
    bound = first_miss.relevance if first_miss is not None else 0.0
    return _assemble(segments, pinned, chosen, cands,
                     {"dp_cells": 0, "mode": "greedy", "abs_gap_bound": round(bound, 6)})


def select_context(segments, budget, current_stage, mode="auto", max_cells=MAX_EXACT_CELLS):
    """Policy entry point: 'exact', 'greedy', or 'auto' (exact iff cells <= max_cells)."""
    if mode not in ("auto", "exact", "greedy"):
        raise ValueError("mode must be one of: auto, exact, greedy")
    if mode == "greedy":
        return select_segments_greedy(segments, budget, current_stage)
    if mode == "exact":
        return select_segments(segments, budget, current_stage)
    cells = estimate_cells(segments, budget, current_stage)
    res = (select_segments(segments, budget, current_stage) if cells <= max_cells
           else select_segments_greedy(segments, budget, current_stage))
    res["est_cells"] = cells
    return res


def recent_baseline(segments, budget, current_stage):
    """Naive baseline: keep the most recent eligible segments that fit."""
    _validate(segments, budget, current_stage)
    used, out = 0, []
    for s in reversed(segments):
        if (s.pinned or s.stage in ELIGIBLE[current_stage]) and used + s.tokens <= budget:
            out.append(s)
            used += s.tokens
    return {
        "selected_segment_ids": [s.id for s in reversed(out)],
        "total_relevance": round(sum(s.relevance for s in out), 6),
        "tokens_used": used,
    }
