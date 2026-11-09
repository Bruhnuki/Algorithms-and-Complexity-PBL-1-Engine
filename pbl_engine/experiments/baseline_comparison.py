"""Task 2 justification: exact DP vs recent-first truncation vs density-greedy.

Relevance follows the Task 1 model: v = 0.4*exp(-ln2*age/20) + 0.2*a + 0.4*iota,
where iota=1 marks segments with an unresolved impediment / Definition-of-Done change
/ complexity claim (10% of segments), a=1 if same stage else 0.5.
Run from the repo root:  python -m experiments.baseline_comparison
"""
import math, random
from engine.context_chaining import Segment, select_segments, recent_baseline


def instance(rng, n=300):
    segs, flagged = [], set()
    stages = ["PLANNING", "STANDUP", "BUILD"]
    for i in range(n):
        age = n - 1 - i
        iota = 1 if rng.random() < 0.10 else 0
        a = 1.0 if stages[min(2, i * 3 // n)] == "BUILD" else 0.5
        v = 0.4 * math.exp(-math.log(2) * age / 20) + 0.2 * a + 0.4 * iota
        segs.append(Segment(f"s{i}", rng.randint(20, 300), v, stages[min(2, i * 3 // n)]))
        if iota:
            flagged.add(f"s{i}")
    return segs, flagged


def density_greedy(segs, B):
    order = sorted(segs, key=lambda s: s.relevance / s.tokens, reverse=True)
    used, val, pick = 0, 0.0, []
    for s in order:
        if used + s.tokens <= B:
            used += s.tokens; val += s.relevance; pick.append(s.id)
    best1 = max((s for s in segs if s.tokens <= B), key=lambda s: s.relevance, default=None)
    if best1 and best1.relevance > val:
        return best1.relevance, [best1.id]
    return val, pick


rng = random.Random(2026)
rows = {"recent": [], "greedy": []}
rec = {"dp": [], "recent": [], "greedy": []}
for _ in range(300):
    segs, flagged = instance(rng)
    B = 4000
    dp = select_segments(segs, B, "BUILD")
    rc = recent_baseline(segs, B, "BUILD")
    gv, gp = density_greedy(segs, B)
    rows["recent"].append(rc["total_relevance"] / dp["total_relevance"])
    rows["greedy"].append(gv / dp["total_relevance"])
    for k, ids in (("dp", dp["selected_segment_ids"]), ("recent", rc["selected_segment_ids"]), ("greedy", gp)):
        rec[k].append(len(flagged & set(ids)) / len(flagged))
m = lambda xs: sum(xs) / len(xs)
print("300 random instances, n=300 segments, B=4000 tokens")
print(f"value / DP value : recent-first mean={m(rows['recent']):.3f} min={min(rows['recent']):.3f} | "
      f"density-greedy mean={m(rows['greedy']):.4f} min={min(rows['greedy']):.4f}")
print(f"critical-segment recall: DP={m(rec['dp']):.3f}  recent-first={m(rec['recent']):.3f}  greedy={m(rec['greedy']):.3f}")
