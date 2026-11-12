"""Modeling and Simulation: the discrete-event engine, the paper's model, its experiments and validation, and the admin API."""
import random
import time

import pytest

from fixit.rules import content as content_mod
from fixit.sim import experiments as E
from fixit.sim.des import Pool, Scheduler
from fixit.sim.model import SimParams, Simulation, run_params
from fixit.sim.reference import EXP2, TABLE3
from api_helpers import Env


# ---------------------------------------------------------------- the engine against queueing theory
def mm1(lam=0.5, mu=1.0, horizon=200_000, seed=1):
    rng, sch, pool, waiting_since = random.Random(seed), Scheduler(), Pool("server", 1), {}
    ARR, DONE = 0, 1
    sch.at(rng.expovariate(lam), ARR)
    n = 0
    for kind, who in sch.pop_until(horizon):
        if kind == ARR:
            n += 1
            sch.at(sch.now + rng.expovariate(lam), ARR)
            if pool.take(sch.now):
                sch.after(rng.expovariate(mu), DONE, n)
            else:
                pool.wait(sch.now, n)
        else:
            nxt = pool.release(sch.now)
            if nxt is not None:
                sch.after(rng.expovariate(mu), DONE, nxt)
    return pool, sch.now


def test_SIM1_the_event_engine_matches_mm1_queueing_theory():
    pool, now = mm1(0.5, 1.0)
    assert pool.utilization(now) == pytest.approx(0.5, abs=0.02)            # rho = lambda / mu
    assert pool.avg_queue(now) == pytest.approx(0.5, abs=0.08)              # Lq = rho^2 / (1 - rho)
    pool, now = mm1(0.8, 1.0, seed=3)
    assert pool.utilization(now) == pytest.approx(0.8, abs=0.02) and pool.avg_queue(now) == pytest.approx(3.2, rel=0.2)


def test_SIM2_pools_hand_over_in_fifo_order_and_stats_can_be_reset():
    p = Pool("x", 1)
    assert p.take(0) and not p.take(1)
    p.wait(1, "a"); p.wait(2, "b")
    assert p.release(5) == "a" and p.release(6) == "b" and p.release(7) is None and p.busy == 0
    p.reset_stats(10)
    assert p.utilization(20) == 0 and p.max_queue == 0
    p.take(20)
    assert p.utilization(30) == pytest.approx(0.5)
    s = Scheduler()
    for t in (3, 1, 2, 1):
        s.at(t, 0, t)
    assert [pl for _, pl in s.pop_until(10)] == [1, 1, 2, 3] and s.now == 10


# ---------------------------------------------------------------- the paper's model
def test_SIM3_runs_are_deterministic_per_seed_and_the_seed_matters():
    a, b, c = (run_params({"seed": s, "run_seconds": 20000, "user_arrival_rate": 30}) for s in (5, 5, 6))
    assert a == b and a != c


def test_SIM4_parameters_are_validated():
    for bad in ({"user_arrival_rate": 0}, {"llm_slots": 0}, {"login_success_prob": 1.5}, {"run_seconds": 100, "warmup_seconds": 200},
                {"dists": {"llm": [10, 5, 20]}}, {"sandbox_workers": 999}):
        with pytest.raises(ValueError):
            SimParams.from_dict(bad)
    assert SimParams.from_dict({"nonsense": 1}).llm_slots == 5     # unknown fields are ignored


def test_SIM5_baseline_matches_experiment_1_of_the_paper():
    m = E.experiment1({}, reps=6)["mean"]
    assert 12.5 < m["M1_turn_response_s"] < 13.6 and 35 < m["M2_session_min"] < 40            # paper: 13.0 s and 37.3 min
    assert 20 < m["M4_llm_util_pct"] < 25.5 and 15 < m["M5_sandbox_util_pct"] < 19.5            # paper: 22.2% and 16.8%
    assert m["M11_abandon_pct"] == 0 and 9.3 < m["M3_throughput_per_h"] < 10.7                  # paper: 0.00% and 9.99/h


def test_SIM6_stress_test_breaks_where_the_paper_says_and_the_llm_pool_is_the_bottleneck():
    r = E.experiment2({}, rates=[30, 40, 45, 60], reps=3)
    by = {row["rate"]: row for row in r["rows"]}
    assert by[30]["M11_abandon_pct"] < 1 and by[40]["M11_abandon_pct"] < 4
    assert by[45]["M11_abandon_pct"] > 4 and r["break_point"] == 45                              # paper: 7.74% at 45/h
    assert 38 < by[60]["M11_abandon_pct"] < 56 and by[60]["M4_llm_util_pct"] > 93                # paper: 47.3% and 96.2%
    assert by[60]["M5_sandbox_util_pct"] < 70 and r["bottleneck"] == "LLM call slots"
    assert by[45]["M3_throughput_per_h"] > by[60]["M3_throughput_per_h"]                          # past the break point extra arrivals serve fewer
    assert by[60]["M1_turn_response_s"] > 90                                                      # paper: 113.8 s
    ref = EXP2[60]
    assert abs(by[60]["M3_throughput_per_h"] - ref[5]) < 4


def test_SIM7_optimization_finds_the_papers_options_and_option_b_is_cheaper():
    r = E.experiment3({}, reps=3, llm_range=(5, 8), sbx_range=(1, 3))
    a, b = r["best"]["A"], r["best"]["B"]
    assert (a["llm_slots"], a["sandbox_workers"], a["units"]) == (7, 2, 9)                       # paper: Option A needs 7 + 2
    assert (b["llm_slots"], b["sandbox_workers"], b["units"]) == (6, 2, 8)                       # paper: Option B needs 6 + 2
    assert r["saving_units"] == 1 and r["baseline"]["M11_abandon_pct"] > 40
    same = {(x["option"], x["llm_slots"], x["sandbox_workers"]): x for x in r["table"]}
    assert same[("A", 6, 2)]["M11_abandon_pct"] > 10 > same[("B", 6, 2)]["M11_abandon_pct"]       # at 6 + 2 only E1 holds
    assert all(x["M11_abandon_pct"] > 5 for x in r["table"] if x["sandbox_workers"] == 1)         # one sandbox worker never suffices
    assert TABLE3[1][1:3] == (7, 2) and TABLE3[3][1:3] == (6, 2)


def test_SIM8_the_papers_validation_checks_pass_on_the_model():
    v = E.validate(reps=3)
    failed = [c["name"] for c in v["checks"] if not c["passed"]]
    assert not failed and v["passed"] == v["total"] >= 12
    assert abs(v["expected"]["baseline"]["saturation_per_h"] - 43.3) < 0.2                         # 5 x 3600 / (32 x 13)
    assert abs(v["expected"]["baseline"]["llm_util_pct"] - 23.1) < 0.1


def test_SIM9_patience_timeouts_abandon_and_warmup_resets_the_counters():
    heavy = Simulation(SimParams.from_dict({"user_arrival_rate": 80, "run_seconds": 20000, "warmup_seconds": 5000, "seed": 2}))
    heavy.run_until(4999)
    assert heavy.abandoned > 0 and heavy.n_arrived > 0
    heavy.run_until(5001)                                          # the warm-up ended: every counter starts again
    assert heavy.n_arrived < 10 and heavy.abandoned < 10 and heavy.llm.since == 5000
    none = Simulation(SimParams.from_dict({"user_arrival_rate": 80, "patience_seconds": 1e9, "sandbox_patience": 1e9, "run_seconds": 20000, "seed": 2}))
    none.run_until(20000)
    assert none.abandoned == 0 and none.llm.queue


def test_SIM10_changes_made_during_a_live_run_take_effect_at_once():
    s = Simulation(SimParams.from_dict({"user_arrival_rate": 60, "run_seconds": 30000, "seed": 5}))
    s.run_until(10000)
    queued = s.snapshot()["pools"]["llm"]["queue"]
    assert queued > 20 and s.snapshot()["abandon_pct"] > 30
    s.apply({"llm_slots": 8, "sandbox_workers": 2, "budgeted_context": True})
    assert s.snapshot()["pools"]["llm"]["queue"] < queued and s.snapshot()["pools"]["llm"]["capacity"] == 8      # the waiting students are served right away
    s.run_until(20000)
    assert s.snapshot()["pools"]["llm"]["queue"] < 12 and s.p.budgeted_context
    with pytest.raises(ValueError):
        s.apply({"llm_slots": 0})
    s.apply({"llm_slots": 3})                                       # scale down: units retire as they finish
    s.run_until(30000)
    assert s.llm.busy <= 3 + 1 and s.snapshot()["pools"]["llm"]["utilization"] <= 100


def test_SIM11_a_run_is_fast_enough_to_demonstrate():
    t = time.time()
    run_params({"user_arrival_rate": 60, "seed": 9})               # 24 virtual hours at launch-day load
    assert time.time() - t < 4


# ---------------------------------------------------------------- the admin API
@pytest.fixture()
def admin(tmp_path):
    env = Env(tmp_path, content_mod.get())
    return env.signup("boss@x.co", role="instructor"), env


def wait(c, job_id, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        j = c.get(f"/api/v1/instructor/sim/jobs/{job_id}").json()
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.1)
    raise AssertionError("job did not finish")


def test_SIM12_only_instructors_may_use_the_simulation(admin):
    c, env = admin
    student = env.signup("stu@x.co")
    for method, path in (("get", "/api/v1/instructor/sim/presets"), ("post", "/api/v1/instructor/sim/jobs"), ("get", "/api/v1/instructor/sim/jobs"),
                         ("post", "/api/v1/instructor/sim/calibrate"), ("get", "/api/v1/instructor/sim/reference")):
        r = getattr(student, method)(path, **({"json": {"kind": "baseline"}} if method == "post" else {}))
        assert r.status_code == 403, path
        assert getattr(env.client(), method)(path).status_code in (401, 403, 405, 422)
    assert c.get("/api/v1/instructor/sim/presets").json()["presets"][0]["id"] == "paper"


def test_SIM13_an_admin_runs_a_baseline_experiment_and_exports_it(admin):
    c, _ = admin
    r = c.post("/api/v1/instructor/sim/jobs", json={"kind": "baseline", "reps": 3})
    assert r.status_code == 201
    j = wait(c, r.json()["id"])
    assert j["status"] == "done" and j["result"]["mean"]["M11_abandon_pct"] == 0 and j["progress"] == {"done": 3, "total": 3}
    csv = c.get(f"/api/v1/instructor/sim/jobs/{j['id']}/export.csv")
    assert csv.status_code == 200 and csv.text.splitlines()[0].startswith("M1_turn_response_s")
    assert c.get("/api/v1/instructor/sim/jobs/nope").status_code == 404
    bad = c.post("/api/v1/instructor/sim/jobs", json={"kind": "baseline", "params": {"llm_slots": 0}})
    assert bad.status_code == 422 and c.post("/api/v1/instructor/sim/jobs", json={"kind": "mystery"}).status_code == 422


def test_SIM14_the_live_run_can_be_watched_changed_paused_and_stopped(admin):
    c, _ = admin
    r = c.post("/api/v1/instructor/sim/jobs", json={"kind": "live", "params": {"user_arrival_rate": 60, "run_seconds": 40000, "warmup_seconds": 0}, "speed": 3600}).json()
    time.sleep(0.8)
    j = c.get(f"/api/v1/instructor/sim/jobs/{r['id']}").json()
    assert j["status"] == "running" and j["live"]["t"] > 0 and set(j["live"]["pools"]) == {"auth", "llm", "sandbox"} and j["speed"] == 3600
    ok = c.post(f"/api/v1/instructor/sim/jobs/{r['id']}/control", json={"action": "apply", "changes": {"llm_slots": 8, "sandbox_workers": 2}})
    assert ok.status_code == 200
    assert c.post(f"/api/v1/instructor/sim/jobs/{r['id']}/control", json={"action": "apply", "changes": {"llm_slots": 0}}).status_code == 422
    time.sleep(0.5)
    j = c.get(f"/api/v1/instructor/sim/jobs/{r['id']}").json()
    assert j["live"]["pools"]["llm"]["capacity"] == 8 and j["applied"][0]["changes"]["llm_slots"] == 8
    c.post(f"/api/v1/instructor/sim/jobs/{r['id']}/control", json={"action": "pause"})
    t1 = c.get(f"/api/v1/instructor/sim/jobs/{r['id']}").json()["live"]["t"]
    time.sleep(0.4)
    assert c.get(f"/api/v1/instructor/sim/jobs/{r['id']}").json()["live"]["t"] == t1
    c.post(f"/api/v1/instructor/sim/jobs/{r['id']}/control", json={"action": "cancel"})
    done = wait(c, r["id"])
    assert done["status"] == "cancelled" and done["result"]["metrics"]["arrived"] > 0
    assert c.post(f"/api/v1/instructor/sim/jobs/{r['id']}/control", json={"action": "pause"}).status_code == 422     # no longer running


def test_SIM15_this_deployment_can_be_measured(admin):
    c, _ = admin
    r = c.post("/api/v1/instructor/sim/calibrate").json()
    assert r["id"] == "deployment" and r["measured"]["auth_verify_ms"]["median"] > 0 and r["measured"]["sandbox_run_ms"]["samples"] == 40
    assert r["params"]["dists"]["login_auth"][0] > 0 and "llm" in r["kept_from_paper"]       # no AI server in this test: the paper's LLM time stays
    run = c.post("/api/v1/instructor/sim/jobs", json={"kind": "baseline", "reps": 2, "params": r["params"]}).json()
    assert wait(c, run["id"])["status"] == "done"


def test_QA2_arrival_rates_in_a_stress_sweep_must_be_positive_and_sane():
    from fixit.sim.jobs import SimJobs
    jobs = SimJobs()
    for bad in ([0], [-5], [5, 0], [5000], ["x"], [True]):
        with pytest.raises(ValueError):
            jobs.start("stress", {}, {"rates": bad})
