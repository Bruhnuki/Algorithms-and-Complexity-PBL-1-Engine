import json, math, os, random
from itertools import combinations

from engine.context_chaining import (Segment, advance, estimate_cells, recent_baseline,
                                     select_context, select_segments, select_segments_greedy)
from engine.learning_gain import (ProcessAccumulator, bootstrap_ci, cohort_summary,
                                  normalized_gain, process_summary)
from engine.solve import solve
from tests.mini_jsonschema import validate

_HERE = os.path.dirname(os.path.dirname(__file__))
REQ = json.load(open(os.path.join(_HERE, "schemas", "solve_request.schema.json")))
RES = json.load(open(os.path.join(_HERE, "schemas", "solve_response.schema.json")))


def clone(x):
    return json.loads(json.dumps(x))


def brute_force_opt(segs, B):
    best = 0.0
    for k in range(len(segs) + 1):
        for comb in combinations(segs, k):
            if sum(s.tokens for s in comb) <= B:
                best = max(best, sum(s.relevance for s in comb))
    return best


CC = {"algorithm": "context_chaining", "job_id": "job-1",
      "input": {"token_budget": 1000, "current_stage": "BUILD", "advance_to": "REVIEW",
                "segments": [
                    {"id": "dod", "tokens": 100, "relevance": 1.0, "stage": "PLANNING", "pinned": True},
                    {"id": "s1", "tokens": 400, "relevance": 0.9, "stage": "BUILD"},
                    {"id": "s2", "tokens": 700, "relevance": 0.5, "stage": "STANDUP"}]}}
CC_NOADV = clone(CC); del CC_NOADV["input"]["advance_to"]
LG = {"algorithm": "learning_gain", "job_id": "job-2",
      "input": {"max_score": 10, "bootstrap_B": 200, "seed": 7,
                "students": [{"id": "a", "pre": 4, "post": 8}, {"id": "b", "pre": 10, "post": 10},
                             {"id": "c", "pre": 5, "post": 7}],
                "process_events": {
                    "categories": {"facilitating": {"weight": 0.5, "eta": 0.5},
                                   "impediment": {"weight": 0.5, "eta": 0.4}},
                    "events": [{"id": "e1", "stage": "STANDUP", "category": "facilitating", "quality": 1.0},
                               {"id": "e2", "stage": "BUILD", "category": "facilitating", "quality": 1.0},
                               {"id": "e3", "stage": "BUILD", "category": "impediment", "quality": 0.5},
                               {"id": "e1", "stage": "STANDUP", "category": "facilitating", "quality": 1.0}]}}}


# ---------------- E1: exact DP ----------------
def test_knapsack_beats_or_equals_baseline():
    rng = random.Random(1)
    segs = [Segment(f"s{i}", rng.randint(50, 400), rng.random(), "BUILD") for i in range(60)]
    dp = select_segments(segs, 2000, "BUILD")
    base = recent_baseline(segs, 2000, "BUILD")
    assert dp["tokens_used"] <= 2000 and dp["total_relevance"] >= base["total_relevance"]


def test_knapsack_known_optimum():
    segs = [Segment("a", 5, 10, "BUILD"), Segment("b", 4, 40, "BUILD"),
            Segment("c", 6, 30, "BUILD"), Segment("d", 3, 50, "BUILD")]
    assert set(select_segments(segs, 10, "BUILD")["selected_segment_ids"]) == {"b", "d"}


def test_knapsack_matches_bruteforce_small():
    rng = random.Random(11)
    for _ in range(150):
        n = rng.randint(1, 10)
        segs = [Segment(f"s{i}", rng.randint(1, 20), round(rng.random(), 3), "BUILD") for i in range(n)]
        B = rng.randint(0, 60)
        assert abs(select_segments(segs, B, "BUILD")["total_relevance"] - brute_force_opt(segs, B)) < 1e-9


def test_pinned_and_eligibility_and_edges():
    segs = [Segment("dod", 100, 1, "PLANNING", pinned=True), Segment("rev", 50, 99, "REVIEW")]
    assert select_segments(segs, 500, "BUILD")["selected_segment_ids"] == ["dod"]  # REVIEW not eligible yet
    assert select_segments([], 100, "BUILD")["selected_segment_ids"] == []
    try:
        select_segments(segs, 50, "BUILD"); assert False
    except ValueError:
        pass


def test_state_machine():
    assert advance("PLANNING", "STANDUP") == "STANDUP"
    try:
        advance("PLANNING", "REVIEW"); assert False
    except ValueError:
        pass


# ---------------- E1: greedy mode and policy ----------------
def test_greedy_certificate_bound_and_half_approximation():
    rng = random.Random(5)
    for _ in range(200):
        n = rng.randint(1, 10)
        segs = [Segment(f"s{i}", rng.randint(1, 25), round(rng.random(), 3), "BUILD") for i in range(n)]
        B = rng.randint(0, 60)
        g = select_segments_greedy(segs, B, "BUILD")
        opt = brute_force_opt(segs, B)
        v = g["total_relevance"]
        assert g["tokens_used"] <= B and g["mode"] == "greedy"
        assert v <= opt + 1e-9
        assert opt - v <= g["abs_gap_bound"] + 1e-6          # data-dependent optimality gap
        assert v >= 0.5 * opt - 1e-9                          # Proposition 2


def test_greedy_keeps_pinned_and_respects_eligibility():
    segs = [Segment("dod", 100, 1, "PLANNING", pinned=True), Segment("rev", 50, 9, "REVIEW"),
            Segment("a", 80, 0.5, "BUILD")]
    g = select_segments_greedy(segs, 300, "BUILD")
    assert "dod" in g["selected_segment_ids"] and "rev" not in g["selected_segment_ids"]


def test_policy_switches_on_estimated_cells():
    rng = random.Random(21)
    segs = [Segment(f"s{i}", rng.randint(20, 300), rng.random(), "BUILD") for i in range(80)]
    cells = estimate_cells(segs, 3000, "BUILD")
    assert select_context(segs, 3000, "BUILD", max_cells=cells)["mode"] == "exact"
    assert select_context(segs, 3000, "BUILD", max_cells=cells - 1)["mode"] == "greedy"
    assert select_context(segs, 3000, "BUILD", mode="greedy")["mode"] == "greedy"
    assert select_context(segs, 3000, "BUILD", mode="exact")["mode"] == "exact"
    assert select_context(segs, 3000, "BUILD", mode="auto")["est_cells"] == cells
    try:
        select_context(segs, 3000, "BUILD", mode="fast"); assert False
    except ValueError:
        pass


# ---------------- E2: normalized gain ----------------
def test_normalized_gain_hake_and_marx_cummings():
    assert normalized_gain(4, 8, 10) == (8 - 4) / (10 - 4)           # Hake gain
    assert abs(normalized_gain(5, 2, 10) - (-0.6)) < 1e-12           # Marx-Cummings loss
    assert normalized_gain(10, 10, 10) is None                       # ceiling, no information
    assert abs(normalized_gain(10, 4, 10) - (-0.6)) < 1e-12          # dropped from ceiling: defined
    assert normalized_gain(0, 0, 10) == 0.0
    rng = random.Random(9)
    for _ in range(2000):
        pre, post = rng.randint(0, 10), rng.randint(0, 10)
        g = normalized_gain(pre, post, 10)
        assert g is None or -1.0 <= g <= 1.0
    for bad in ((11, 5), (-1, 5), (5, float("nan"))):
        try:
            normalized_gain(bad[0], bad[1], 10); assert False
        except ValueError:
            pass


def test_cohort_and_ci():
    s = [{"pre": 4, "post": 8}, {"pre": 10, "post": 10}, {"pre": 5, "post": 7}]
    r = cohort_summary(s, 10, B=200)
    assert r["n_undefined"] == 1 and r["ci95"][0] <= r["mean_individual_gain"] <= r["ci95"][1]
    assert bootstrap_ci([]) is None


def test_bootstrap_ci_within_data_range_and_seeded():
    vals = [0.1, 0.5, 0.9, 0.3, 0.7, 0.2]
    lo, hi = bootstrap_ci(vals, B=500, seed=4)
    assert min(vals) <= lo <= hi <= max(vals) and (lo, hi) == bootstrap_ci(vals, B=500, seed=4)


# ---------------- E2: saturating accumulator ----------------
def test_accumulator_bounds_monotone_and_closed_form():
    rng = random.Random(3)
    acc = ProcessAccumulator({"a": {"weight": 0.6, "eta": 0.3}, "b": {"weight": 0.4, "eta": 0.7}})
    prod, prev = 1.0, 0.0
    for k in range(200):
        q = rng.random()
        acc.record(f"e{k}", "BUILD", "a", q)
        prod *= (1 - 0.3 * q)
        assert 0.0 <= acc.A["a"] <= 1.0 and acc.A["a"] >= prev - 1e-15      # bounded, non-decreasing
        assert abs(acc.A["a"] - (1 - prod)) < 1e-9                          # closed form
        prev = acc.A["a"]
    assert 0.0 <= acc.score() <= 100.0


def test_accumulator_is_idempotent_validated_and_conserves_points():
    s = process_summary(LG["input"]["process_events"]["categories"], LG["input"]["process_events"]["events"])
    assert abs(s["process_score"] - 47.5) < 1e-6
    assert abs(s["by_stage"]["STANDUP"] - 25.0) < 1e-6 and abs(s["by_stage"]["BUILD"] - 22.5) < 1e-6
    assert abs(sum(s["by_stage"].values()) - s["process_score"]) < 1e-5     # conservation
    assert s["duplicates_ignored"] == 1 and s["events_applied"] == 3
    farm = ProcessAccumulator({"a": {"weight": 1.0, "eta": 0.5}})
    for k in range(1000):
        farm.record(f"x{k}", "BUILD", "a", 1.0)
    assert farm.score() <= 100.0                                              # farming cannot exceed the cap
    for bad in (("", "BUILD", "a", 0.5), ("z", "NOPE", "a", 0.5), ("z", "BUILD", "zz", 0.5),
                ("z", "BUILD", "a", 1.5), ("z", "BUILD", "a", float("nan"))):
        try:
            farm.record(*bad); assert False
        except ValueError:
            pass
    for bad_cfg in ({"a": {"weight": 0.5, "eta": 0.5}}, {"a": {"weight": 1.0, "eta": 0.0}}, {}):
        try:
            ProcessAccumulator(bad_cfg); assert False
        except ValueError:
            pass


# ---------------- API contract ----------------
def test_schema_accepts_valid_and_rejects_invalid():
    assert validate(CC, REQ) == [] and validate(LG, REQ) == []
    bad = clone(CC); bad["input"]["segments"][0]["tokens"] = 0
    assert validate(bad, REQ) != []
    bad = clone(CC); bad["algorithm"] = "nope"
    assert validate(bad, REQ) != []
    bad = clone(LG); bad["input"]["bootstrap_B"] = 10
    assert validate(bad, REQ) != []
    bad = clone(CC); bad["input"]["extra"] = 1
    assert validate(bad, REQ) != []
    bad = clone(CC); bad["input"]["mode"] = "fast"
    assert validate(bad, REQ) != []
    bad = clone(LG); bad["input"]["process_events"]["events"][0]["quality"] = 2
    assert validate(bad, REQ) != []


def test_responses_conform_to_response_schema():
    for req in (CC, LG, {"algorithm": "nope", "job_id": "x", "input": {}}):
        resp = solve(req)
        assert validate(resp, RES) == [], (resp, validate(resp, RES))


def test_solve_context_chaining_modes_and_transition():
    r = solve(CC)
    assert r["status"] == "ok" and r["result"]["stage"] == "REVIEW" and r["result"]["mode"] == "exact"
    assert "dod" in r["result"]["selected_segment_ids"] and r["result"]["tokens_used"] <= 1000
    g = clone(CC); g["input"]["mode"] = "greedy"
    rg = solve(g)
    assert rg["result"]["mode"] == "greedy" and "abs_gap_bound" in rg["result"] and rg["metrics"]["dp_cells"] == 0
    bad = clone(CC); bad["input"]["advance_to"] = "PLANNING"
    assert solve(bad)["error"]["code"] == "ILLEGAL_TRANSITION"


def test_error_codes():
    inf = clone(CC); inf["input"]["token_budget"] = 50
    assert solve(inf)["error"]["code"] == "INFEASIBLE"
    dup = clone(CC); dup["input"]["segments"][1]["id"] = "dod"
    assert solve(dup)["error"]["code"] == "VALIDATION_ERROR"
    big = clone(CC); big["input"]["token_budget"] = 10**6
    assert solve(big)["error"]["code"] == "LIMIT_EXCEEDED"
    assert solve({"algorithm": "context_chaining", "job_id": "x"})["error"]["code"] == "MALFORMED_REQUEST"
    assert solve("not a dict")["error"]["code"] == "MALFORMED_REQUEST"
    nan = clone(CC); nan["input"]["segments"][1]["relevance"] = float("nan")
    assert solve(nan)["error"]["code"] == "VALIDATION_ERROR"
    mode = clone(CC); mode["input"]["mode"] = "fast"
    assert solve(mode)["error"]["code"] == "VALIDATION_ERROR"


def test_learning_gain_via_solve():
    r = solve(LG)
    c, p = r["result"]["cohort"], r["result"]["process"]
    assert r["status"] == "ok" and c["n_undefined"] == 1 and "small_sample_ci_unreliable" in c["warnings"]
    assert solve(LG)["result"] == r["result"]                                  # seed => deterministic
    assert abs(p["process_score"] - 47.5) < 1e-6 and p["duplicates_ignored"] == 1
    bad = clone(LG); bad["input"]["process_events"]["events"][0]["category"] = "farm"
    assert solve(bad)["error"]["code"] == "VALIDATION_ERROR"
    bad = clone(LG); bad["input"]["process_events"]["categories"]["facilitating"]["weight"] = 0.9
    assert solve(bad)["error"]["code"] == "VALIDATION_ERROR"


def test_empty_degenerate_limits_and_internal_error():
    import engine.solve as S
    e = solve({"algorithm": "learning_gain", "job_id": "e", "input": {"max_score": 10, "students": []}})
    assert e["status"] == "ok" and e["result"]["cohort"]["warnings"] == ["empty_cohort"]
    z = solve({"algorithm": "context_chaining", "job_id": "z",
               "input": {"token_budget": 0, "current_stage": "PLANNING", "segments": []}})
    assert z["status"] == "ok" and z["result"]["selected_segment_ids"] == []
    big = clone(LG); big["input"]["students"] = [{"id": str(i), "pre": 1, "post": 2} for i in range(5000)]
    big["input"]["bootstrap_B"] = 10000
    assert solve(big)["error"]["code"] == "LIMIT_EXCEEDED"                      # 5e7 draws > 2e7
    orig = S.select_context
    S.select_context = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        r = solve(CC_NOADV)
        assert r["status"] == "error" and r["error"]["code"] == "INTERNAL_ERROR"
        assert "boom" not in json.dumps(r) and validate(r, RES) == []
    finally:
        S.select_context = orig
