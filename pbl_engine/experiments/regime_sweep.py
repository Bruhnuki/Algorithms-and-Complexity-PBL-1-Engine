"""When does greedy stop being good enough? Sweep item size relative to the budget.

Relevance follows the Task 1 model (recency + stage affinity + critical flag).
Run from the repo root:  python -m experiments.regime_sweep
"""
import math, random, time
from engine.context_chaining import Segment, select_segments, select_segments_greedy


def instance(rng, n, lo, hi):
    segs = []
    for i in range(n):
        age = n - 1 - i
        iota = 1 if rng.random() < 0.10 else 0
        v = 0.4 * math.exp(-math.log(2) * age / 20) + 0.2 * 0.75 + 0.4 * iota
        segs.append(Segment(f"s{i}", rng.randint(lo, hi), v, "BUILD"))
    return segs


REGIMES = {
    "small items (20-300 tok)": (20, 300),
    "large items (500-1500 tok)": (500, 1500),
    "very large (1000-3000 tok)": (1000, 3000),
}
B, N, TRIALS = 4000, 300, 100
print(f"n={N} segments, B={B} tokens, {TRIALS} instances per regime (seed 7)")
print(f"{'regime':<28} {'mean OPT':>9} {'greedy/DP mean':>15} {'worst':>7} {'mean bound':>11} {'bound holds':>12} {'DP ms':>7}")
for name, (lo, hi) in REGIMES.items():
    rng = random.Random(7)
    opts, ratios, bounds, ok, t = [], [], [], True, 0.0
    for _ in range(TRIALS):
        segs = instance(rng, N, lo, hi)
        s = time.perf_counter(); dp = select_segments(segs, B, "BUILD"); t += time.perf_counter() - s
        gr = select_segments_greedy(segs, B, "BUILD")
        ok &= (dp["total_relevance"] - gr["total_relevance"] <= gr["abs_gap_bound"] + 1e-6)
        opts.append(dp["total_relevance"]); bounds.append(gr["abs_gap_bound"])
        ratios.append(gr["total_relevance"] / dp["total_relevance"])
    m = lambda xs: sum(xs) / len(xs)
    print(f"{name:<28} {m(opts):>9.2f} {m(ratios):>15.4f} {min(ratios):>7.4f} {m(bounds):>11.3f} {str(ok):>12} {1000*t/TRIALS:>7.0f}")
