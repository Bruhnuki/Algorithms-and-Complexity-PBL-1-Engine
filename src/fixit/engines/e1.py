"""E1 for the game: stage machine and memory selection, run by the real `pbl_engine` (context window chaining).

The game keeps its own segment format ({id, text, seq, pinned?, stages?}) and its RETRO stage; this adapter translates to the engine's
`Segment` and back. The engine does the work: exact knapsack DP while it is small enough, density greedy with a gap bound beyond that.
"""
from __future__ import annotations

import math
import time

from . import real

STAGES = ("PLANNING", "STANDUP", "BUILD", "REVIEW", "RETRO")
# RETRO is only entered in learning mode (balance.calm.enabled); the engine has no such stage, so its edges stay here.
ALLOWED = {"PLANNING": {"STANDUP"}, "STANDUP": {"BUILD"}, "BUILD": {"STANDUP", "REVIEW"}, "REVIEW": {"RETRO"}, "RETRO": {"PLANNING"}}
BUDGET_DEFAULT, BUDGET_CAP = 3000, 4000


def can_transition(src: str, dst: str) -> bool:
    """The four core edges are decided by the engine's state machine; the RETRO edges are the game's."""
    if src in real.cc.STAGES and dst in real.cc.STAGES:
        t0 = time.perf_counter()
        try:
            real.cc.advance(src, dst)
            ok = True
        except ValueError:
            ok = False
        real.record("E1", "advance", t0, stage=f"{src}>{dst}", ok=ok)
        return ok
    return dst in ALLOWED.get(src, set())


def tokens(text: str) -> int:
    return len(text) // 4 + 1


def relevance(index: int, count: int, origin: str, stage: str, flagged: bool = False) -> float:
    """The paper's relevance model: v = 0.4 e^(-ln2 age/20) + 0.2 a + 0.4 iota (age = how many segments ago, a = 1 if from this stage, else 0.5)."""
    return 0.4 * math.exp(-math.log(2) * (count - 1 - index) / 20) + 0.2 * (1.0 if origin == stage else 0.5) + 0.4 * (1 if flagged else 0)


def to_engine(segments: list[dict], stage: str) -> tuple[list, str]:
    """Game segments (oldest first) -> engine Segments, and the engine's name for the current stage."""
    cur = stage if stage in real.cc.STAGES else "REVIEW"   # a retrospective may recall everything
    ordered = sorted({x["id"]: x for x in segments}.values(), key=lambda x: (not x.get("pinned"), x["seq"]))
    count, out, i = sum(1 for x in ordered if not x.get("pinned")), [], 0
    for x in ordered:
        origin = (x.get("stages") or ["PLANNING"])[0]   # no stage list: it may be recalled at any stage (PLANNING-origin segments are eligible everywhere)
        origin = origin if origin in real.cc.STAGES else "PLANNING"
        out.append(real.cc.Segment(x["id"], tokens(x["text"]), relevance(i, count, origin, cur, bool(x.get("flag"))), origin, bool(x.get("pinned"))))
        i += not x.get("pinned")
    return out, cur


def select_segments(segments: list[dict], stage: str, budget: int = BUDGET_DEFAULT, mode: str = "auto") -> list[dict]:
    """Which memory segments go into the model's context: pinned first, then the most relevant that fit the token budget."""
    budget = min(budget, BUDGET_CAP)
    segs, cur = to_engine(segments, stage)
    t0 = time.perf_counter()
    try:
        res = real.cc.select_context(segs, budget, cur, mode=mode)
    except real.cc.InfeasibleError:   # the pinned persona alone is over budget: send it anyway, as before
        res = {"selected_segment_ids": [s.id for s in segs if s.pinned], "mode": "pinned_only", "dp_cells": 0, "tokens_used": sum(s.tokens for s in segs if s.pinned), "candidates": 0}
    real.record("E1", "select_context", t0, stage=cur, mode=res["mode"], segments=len(segs), budget=budget, chosen=len(res["selected_segment_ids"]),
                tokens_used=res["tokens_used"], dp_cells=res["dp_cells"], est_cells=res.get("est_cells"), gap_bound=res.get("abs_gap_bound"), source="game")
    by_id = {x["id"]: x for x in segments}
    return sorted((by_id[i] for i in res["selected_segment_ids"]), key=lambda x: (not x.get("pinned"), x["seq"]))
