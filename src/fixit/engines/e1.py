"""E1 stand-in: stage machine + memory-segment selection under a token budget.

The real `pbl_engine` package is not in this repo. This mirrors only the behaviour the spec states
(allowed transitions; budget default 3,000, cap 4,000; pinned segments). Swap the adapter when
pbl_engine is available; keep these signatures.
"""
from __future__ import annotations

STAGES = ("PLANNING", "STANDUP", "BUILD", "REVIEW")
ALLOWED = {"PLANNING": {"STANDUP"}, "STANDUP": {"BUILD"}, "BUILD": {"STANDUP", "REVIEW"}, "REVIEW": set()}
BUDGET_DEFAULT, BUDGET_CAP = 3000, 4000


def can_transition(src: str, dst: str) -> bool:
    return dst in ALLOWED.get(src, set())


def tokens(text: str) -> int:
    return len(text) // 4 + 1


def select_segments(segments: list[dict], stage: str, budget: int = BUDGET_DEFAULT) -> list[dict]:
    """segments: {id, text, seq, pinned?, stages?}. Pinned first, then newest eligible that fit."""
    budget = min(budget, BUDGET_CAP)
    chosen, used = [], 0
    for s in (x for x in segments if x.get("pinned")):
        chosen.append(s); used += tokens(s["text"])
    for s in sorted((x for x in segments if not x.get("pinned") and stage in x.get("stages", STAGES)),
                    key=lambda x: -x["seq"]):
        t = tokens(s["text"])
        if used + t <= budget:
            chosen.append(s); used += t
    return sorted(chosen, key=lambda x: (not x.get("pinned"), x["seq"]))
