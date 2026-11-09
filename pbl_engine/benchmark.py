"""Empirical profiling for Task 3 (scaling) and Task 5 (CI thresholds).
Run:  python benchmark.py
Numbers are machine-dependent; re-run on your own hardware and report those."""
import random, time, tracemalloc
from engine.context_chaining import (MAX_EXACT_CELLS, Segment, estimate_cells,
                                     select_context, select_segments, select_segments_greedy)
from engine.learning_gain import ProcessAccumulator, bootstrap_ci


def best_ms(fn, reps=3):
    best = float("inf")
    for _ in range(reps):
        s = time.perf_counter(); fn(); best = min(best, time.perf_counter() - s)
    return best * 1000


def make(rng, n):
    return [Segment(f"s{i}", rng.randint(20, 300), rng.random(), "BUILD") for i in range(n)]


rng = random.Random(0)
print("== Engine 1 (exact DP): runtime vs. DP cells ==")
print(f"{'n':>6} {'B':>7} {'ms':>9} {'cells':>10} {'ns/cell':>8}")
nsc = []
for n in (100, 200, 400):
    for B in (2000, 4000, 8000):
        segs = make(rng, n)
        cells = select_segments(segs, B, "BUILD")["dp_cells"]
        ms = best_ms(lambda: select_segments(segs, B, "BUILD"))
        nsc.append(ms * 1e6 / cells)
        print(f"{n:>6} {B:>7} {ms:>9.1f} {cells:>10} {nsc[-1]:>8.1f}")
print(f"ns/cell: min={min(nsc):.1f} max={max(nsc):.1f} ratio={max(nsc)/min(nsc):.2f}  (assertion A3: ratio <= 3.0)")

print(f"\n== Engine 1: policy (auto uses exact iff cells <= {MAX_EXACT_CELLS:,}) ==")
for n, B in ((400, 8000), (2000, 32000)):
    segs = make(rng, n)
    cells = estimate_cells(segs, B, "BUILD")
    t_greedy = best_ms(lambda: select_segments_greedy(segs, B, "BUILD"))
    t0 = time.perf_counter(); ex = select_segments(segs, B, "BUILD"); t_exact = (time.perf_counter() - t0) * 1000
    tracemalloc.start(); select_segments(segs, B, "BUILD")
    _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
    gr = select_segments_greedy(segs, B, "BUILD")
    auto = select_context(segs, B, "BUILD")["mode"]
    print(f"n={n:>5} B={B:>6} cells={cells:>10,} | exact {t_exact:8.1f} ms, {peak/1e6:5.1f} MB | "
          f"greedy {t_greedy:6.2f} ms | greedy/exact value {gr['total_relevance']/ex['total_relevance']:.4f} "
          f"| gap bound {gr['abs_gap_bound']:.3f} | auto -> {auto}")

print("\n== Engine 1: auto-policy latency for the largest instance that still runs exact ==")
rng2 = random.Random(3)
pool = [Segment(f"s{i}", rng2.randint(20, 300), rng2.random(), "BUILD") for i in range(400)]
n_star = max(n for n in range(50, 400) if estimate_cells(pool[:n], 8000, "BUILD") <= MAX_EXACT_CELLS)
segs = pool[:n_star]
res = select_context(segs, 8000, "BUILD")
t = best_ms(lambda: select_context(segs, 8000, "BUILD"))
print(f"n={n_star} B=8000 cells={res['est_cells']:,} mode={res['mode']}  {t:.1f} ms  (assertion A9: < 500 ms)")

print("\n== Engine 2: bootstrap CI (ms) ==")
vals10 = [rng.random() for _ in range(10)]
prev = None
for L in (500, 1000, 2000, 4000):
    t = best_ms(lambda: bootstrap_ci(vals10, B=L))
    print(f"N=10   L={L:>5}  {t:8.2f} ms" + (f"   ratio {t/prev:.2f}" if prev else ""))
    prev = t
vals1k = [rng.random() for _ in range(1000)]
print(f"N=1000 L= 1000  {best_ms(lambda: bootstrap_ci(vals1k, B=1000), reps=1):8.1f} ms")

print("\n== Engine 2: saturating accumulator throughput ==")
cats = {"a": {"weight": 0.4, "eta": 0.3}, "b": {"weight": 0.3, "eta": 0.5},
        "c": {"weight": 0.2, "eta": 0.2}, "d": {"weight": 0.1, "eta": 0.6}}
stages = ["PLANNING", "STANDUP", "BUILD", "REVIEW"]
for K in (10_000, 100_000):
    ev = [(f"e{i}", stages[i % 4], "abcd"[i % 4], rng.random()) for i in range(K)]
    def run():
        acc = ProcessAccumulator(cats)
        for e in ev: acc.record(*e)
    t = best_ms(run, reps=5)
    print(f"K={K:>7} events: {t:8.1f} ms  ({t*1000/K:.2f} us/event)")
