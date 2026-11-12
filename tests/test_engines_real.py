"""The real AlgoCom engines (pbl_engine) inside the game: adapters, call feed, solve endpoint, admin workbenches."""
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fixit.api.app import Settings, create_app
from fixit.engines import e1, e2, real
from fixit.rules import content as content_mod
from api_helpers import PW

ROOT = Path(__file__).resolve().parents[1]


def seg(i, text="word " * 20, **kw):
    return {"id": f"s{i}", "text": text, "seq": i, **kw}


# ---------------------------------------------------------------- the engines themselves
def test_ENG1_the_zip_engines_own_tests_still_pass():
    r = subprocess.run([sys.executable, "run_tests.py"], cwd=ROOT / "pbl_engine", capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]


def test_ENG2_game_memory_is_chosen_by_the_real_knapsack():
    big = [seg(i, "x" * 400) for i in range(40)]            # 101 tokens each: far more than 600 tokens
    out = e1.select_segments(big, "BUILD", budget=600)
    assert sum(e1.tokens(s["text"]) for s in out) <= 600 and 1 <= len(out) <= 5
    assert [s["seq"] for s in out] == sorted(s["seq"] for s in out)
    assert out[-1]["id"] == "s39"                             # the newest segment is the most relevant, so it is kept
    call = real.feed()["calls"][-1]
    assert call["engine"] == "E1" and call["op"] == "select_context" and call["mode"] in ("exact", "greedy") and call["source"] == "game"


def test_ENG3_stage_eligibility_pinned_and_infeasible_budgets_keep_their_old_behaviour():
    segs = [{"id": "p", "text": "persona " * 30, "seq": 0, "pinned": True}, seg(1, stages=["STANDUP", "BUILD", "REVIEW"]), seg(2)]
    assert [s["id"] for s in e1.select_segments(segs, "PLANNING")] == ["p", "s2"]            # the standup note is not eligible during Planning
    assert [s["id"] for s in e1.select_segments(segs, "BUILD")] == ["p", "s1", "s2"]
    assert [s["id"] for s in e1.select_segments(segs, "RETRO")] == ["p", "s1", "s2"]         # the game's extra stage recalls everything
    assert [s["id"] for s in e1.select_segments(segs, "BUILD", budget=10)] == ["p"]          # pinned alone is over budget: still sent
    assert len(e1.select_segments([seg(1), seg(1)], "BUILD")) == 1                           # a repeated id is one segment


def test_ENG4_stage_edges_come_from_the_engine_and_every_pair_agrees_with_the_game_table():
    for a in e1.STAGES:
        for b in e1.STAGES:
            assert e1.can_transition(a, b) == (b in e1.ALLOWED[a])
    assert real.cc.TRANSITIONS["BUILD"] == {"STANDUP", "REVIEW"}


def test_ENG5_learning_gain_is_the_engines_normalized_gain_with_a_bootstrap_interval():
    pre, post = [0.3, 0.4, 0.5, 0.2, 0.6], [0.6, 0.7, 0.8, 0.4, 0.7]
    g = e2.learning_gain(pre, post, seed=7)
    ref = real.lg.cohort_summary([{"pre": a, "post": b} for a, b in zip(pre, post)], 1.0, B=1000, seed=7)
    assert g["mean"] == ref["mean_individual_gain"] and [g["low"], g["high"]] == ref["ci95"] and g["low"] <= g["mean"] <= g["high"]
    assert e2.learning_gain([], []) == {"mean": 0.0, "low": 0.0, "high": 0.0, "n": 0}


def test_ENG6_the_saturating_process_score_is_bounded_monotone_and_idempotent():
    log = ["standup_held", "coach", "dod_skipped", "coach", "coach", "dod_honest", "review_before_push", "blocker_cleared"] * 6
    r = e2.saturating(log)
    assert r["curve"] == sorted(r["curve"]) and 0 < r["score"] < 100 and len(r["curve"]) == 42   # dod_skipped is not a good behaviour
    assert abs(sum(r["by_stage"].values()) - r["score"]) < 0.01                                  # the stage buckets add up to the score
    assert e2.saturating(log + log)["score"] > r["score"] and e2.saturating([])["score"] == 0


# ---------------------------------------------------------------- over HTTP
@pytest.fixture()
def web(tmp_path):
    app = create_app(str(tmp_path / "a.db"), content_mod.load(), settings=Settings(instructor_code="x", login_per_minute=100, dialogue_inline=True), seed_fn=lambda: 3)

    def user(email, role):
        c = TestClient(app, base_url="https://testserver")
        body = {"email": email, "password": PW, "display_name": email[:3], "role": role}
        if role == "instructor":
            body["instructor_code"] = "x"
        assert c.post("/api/v1/auth/register", json=body).status_code == 201
        c.headers["X-CSRF-Token"] = c.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()["csrf"]
        return c
    return user("prof@x.co", "instructor"), user("stu@x.co", "student")


SOLVE = {"job_id": "j1", "algorithm": "context_chaining", "input": {"current_stage": "BUILD", "token_budget": 100, "mode": "auto",
         "segments": [{"id": "a", "tokens": 60, "relevance": 5, "stage": "BUILD"}, {"id": "b", "tokens": 50, "relevance": 4, "stage": "PLANNING"},
                      {"id": "c", "tokens": 40, "relevance": 3, "stage": "STANDUP"}]}}


def test_ENG7_solve_endpoint_matches_the_engine_and_maps_errors_to_http_codes(web):
    prof, stu = web
    r = prof.post("/api/v1/algorithm/solve", json=SOLVE)
    assert r.status_code == 200 and r.json() == {**real.solver.solve(SOLVE), "metrics": r.json()["metrics"]}
    assert r.json()["result"]["selected_segment_ids"] == ["a", "c"] and r.json()["result"]["total_relevance"] == 8   # 5 + 3 fills the 100 tokens; b + c would only be 7
    bad = lambda **kw: prof.post("/api/v1/algorithm/solve", json={**SOLVE, **kw})   # noqa: E731
    assert bad(algorithm="nope").status_code == 400
    assert bad(input={**SOLVE["input"], "advance_to": "PLANNING"}).status_code == 409
    assert bad(input={**SOLVE["input"], "token_budget": 10}).json()["result"]["selected_segment_ids"] == []
    assert bad(input={**SOLVE["input"], "token_budget": 999_999}).status_code == 413
    assert bad(input={"current_stage": "BUILD"}).status_code == 400
    assert stu.post("/api/v1/algorithm/solve", json=SOLVE).status_code == 403


def test_ENG8_the_live_feed_shows_real_calls_and_only_instructors_see_it(web):
    prof, stu = web
    last = prof.get("/api/v1/instructor/engines/feed").json()["total"]
    e1.select_segments([seg(i) for i in range(5)], "BUILD")
    prof.post("/api/v1/algorithm/solve", json=SOLVE)
    f = prof.get(f"/api/v1/instructor/engines/feed?since={last}").json()
    assert [c["source"] for c in f["calls"]] == ["game", "api"] and f["summary"]["E1"]["calls"] >= 2 and f["total"] == last + 2
    assert stu.get("/api/v1/instructor/engines/feed").status_code == 403


def test_ENG9_the_e1_workbench_compares_exact_greedy_and_recent_on_one_instance(web):
    prof, _ = web
    r = prof.post("/api/v1/instructor/engines/e1", json={"n": 200, "budget": 2500, "seed": 4, "mode": "auto"})
    assert r.status_code == 200
    c = r.json()["compare"]
    assert c["exact"]["value"] >= c["greedy"]["value"] and c["exact"]["value"] >= c["recent"]["value"]   # the DP is optimal
    assert c["exact"]["value"] - c["greedy"]["value"] <= c["greedy"]["gap_bound"] + 1e-6                 # and the greedy certificate holds
    assert c["chosen"]["tokens_used"] <= 2500 and 0 < c["recent"]["of_optimal"] <= 1
    assert real.feed()["calls"][-1]["source"] == "admin"
    assert prof.post("/api/v1/instructor/engines/e1", json={"stage": "PLANNING", "advance_to": "BUILD"}).status_code == 409
    assert prof.post("/api/v1/instructor/engines/e1", json={"source": "run", "run_id": 999}).status_code == 403


def test_ENG10_the_e2_workbench_runs_the_real_bootstrap_and_the_accumulator(web):
    prof, _ = web
    r = prof.post("/api/v1/instructor/engines/e2", json={"n": 30, "mean_pre": 30, "mean_post": 70, "seed": 2, "B": 500})
    assert r.status_code == 200
    s = r.json()["summary"]
    assert s["n_students"] == 30 and s["effect_detected"] is True and s["ci95"][0] > 0
    p = r.json()["process"]
    assert len(p["linear"]) == len(p["events"]) == 30 and p["saturating_curve"] == sorted(p["saturating_curve"]) and p["saturating"] < 100
    assert prof.post("/api/v1/instructor/engines/e2", json={"source": "cohort"}).json()["note"]       # no finished runs yet: it says so


def test_ENG11_the_benchmark_measures_this_machine(web):
    prof, _ = web
    b = prof.post("/api/v1/instructor/engines/benchmark").json()
    assert [d["n"] for d in b["dp"]] == [100, 200, 400] and all(d["cells"] > 0 and d["ms"] > 0 for d in b["dp"])
    assert b["policy"]["auto_mode"] == "greedy" and b["accumulator"]["events"] == 10000 and len(b["bootstrap"]) == 4
