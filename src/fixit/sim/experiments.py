"""The paper's three experiments and its validation checks, run on the model in model.py.

Replications are spread over a process pool (one run is independent of the next) and every function reports progress and honours a
cancel flag, so the admin page can show a progress bar and stop a long run.
"""
from __future__ import annotations

import os
import statistics
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Callable

from .model import SimParams, run_params
from .reference import ANALYTIC_SATURATION_PER_H, THRESHOLDS

AVG_KEYS = ("M1_turn_response_s", "M2_session_min", "M3_throughput_per_h", "M4_llm_util_pct", "M5_sandbox_util_pct", "M6_llm_queue_avg", "M7_llm_queue_max",
            "M8_llm_wait_s", "M9_sandbox_wait_s", "M10_abandoned", "M11_abandon_pct", "auth_util_pct", "arrived", "completed", "login_retries", "logins",
            "resubmissions", "gradings", "turns", "in_system_end")

_POOL: ProcessPoolExecutor | None = None


class Cancelled(Exception):
    pass


def _pool() -> ProcessPoolExecutor | None:
    global _POOL
    if _POOL is None and (os.cpu_count() or 1) > 1:
        try:
            _POOL = ProcessPoolExecutor(max_workers=min(8, os.cpu_count() or 2))
        except (OSError, ValueError):
            _POOL = None
    return _POOL


def mean_of(runs: list[dict]) -> dict:
    out = {k: statistics.fmean(r[k] for r in runs) for k in AVG_KEYS}
    out["reps"] = len(runs)
    if len(runs) > 1:
        out["M11_abandon_sd"] = statistics.stdev(r["M11_abandon_pct"] for r in runs)
    return out


def run_many(jobs: list[dict], progress: Callable[[int, int], None] | None = None, cancel: Callable[[], bool] | None = None) -> list[dict]:
    """Run parameter dicts, in parallel when a pool is available. Results come back in the same order."""
    results: list[dict | None] = [None] * len(jobs)
    pool, done = _pool(), 0
    if pool is None or len(jobs) < 2:
        for i, j in enumerate(jobs):
            if cancel and cancel():
                raise Cancelled()
            results[i] = run_params(j)
            done += 1
            if progress:
                progress(done, len(jobs))
        return results   # type: ignore[return-value]
    futures = {pool.submit(run_params, j): i for i, j in enumerate(jobs)}
    try:
        for f in as_completed(futures):
            if cancel and cancel():
                raise Cancelled()
            results[futures[f]] = f.result()
            done += 1
            if progress:
                progress(done, len(jobs))
    except Cancelled:
        for f in futures:
            f.cancel()
        raise
    return results   # type: ignore[return-value]


def _seeds(base: int, reps: int) -> list[int]:
    return [base + 1000 * i for i in range(reps)]


def _grid(base: dict, overrides: list[dict], reps: int, seed: int) -> list[dict]:
    return [{**base, **o, "seed": s} for o in overrides for s in _seeds(seed, reps)]


def experiment1(params: dict, reps: int = 10, progress=None, cancel=None) -> dict:
    """Baseline analysis: the expected normal load."""
    p = SimParams.from_dict(params).to_dict()
    runs = run_many(_grid(p, [{}], reps, p["seed"]), progress, cancel)
    return {"kind": "baseline", "params": p, "mean": mean_of(runs), "runs": runs}


def experiment2(params: dict, rates: list[float] | None = None, reps: int = 10, progress=None, cancel=None) -> dict:
    """Stress test ("launch day"): the arrival rate swept upwards on fixed capacities."""
    rates = rates or [float(r) for r in range(5, 85, 5)]
    p = SimParams.from_dict(params).to_dict()
    runs = run_many(_grid(p, [{"user_arrival_rate": r} for r in rates], reps, p["seed"]), progress, cancel)
    rows = [{"rate": r, **mean_of(runs[i * reps:(i + 1) * reps])} for i, r in enumerate(rates)]
    over = [r["rate"] for r in rows if r["M11_abandon_pct"] > THRESHOLDS["abandon_pct"]]
    b = max(rows, key=lambda r: r["M4_llm_util_pct"] - r["M5_sandbox_util_pct"]) if rows else None
    llm_busier = sum(r["M4_llm_util_pct"] for r in rows) >= sum(r["M5_sandbox_util_pct"] for r in rows)
    return {"kind": "stress", "params": p, "rows": rows, "break_point": min(over) if over else None,
            "bottleneck": "LLM call slots" if llm_busier else "sandbox workers", "at_peak": b}


def experiment3(params: dict, rate: float = 60.0, llm_range=(5, 12), sbx_range=(1, 4), reps: int = 5, progress=None, cancel=None,
                abandon_limit: float = THRESHOLDS["abandon_pct"], session_limit: float = THRESHOLDS["session_min"]) -> dict:
    """Optimization and scaling at the broken load: minimise llmSlots + sandboxWorkers subject to abandonment and session-time limits,
    once without E1 (Option A: scale resources) and once with E1 budgeted context (Option B: optimise the application)."""
    p = SimParams.from_dict({**params, "user_arrival_rate": rate}).to_dict()
    combos = [(a, b) for a in range(llm_range[0], llm_range[1] + 1) for b in range(sbx_range[0], sbx_range[1] + 1)]
    overrides = [{"llm_slots": a, "sandbox_workers": b, "budgeted_context": opt} for opt in (False, True) for a, b in combos]
    runs = run_many(_grid(p, overrides, reps, p["seed"]), progress, cancel)
    table = []
    for i, o in enumerate(overrides):
        m = mean_of(runs[i * reps:(i + 1) * reps])
        table.append({"option": "B" if o["budgeted_context"] else "A", "llm_slots": o["llm_slots"], "sandbox_workers": o["sandbox_workers"],
                      "units": o["llm_slots"] + o["sandbox_workers"], **m,
                      "feasible": m["M11_abandon_pct"] <= abandon_limit and m["M2_session_min"] <= session_limit})
    best = {}
    for opt in ("A", "B"):
        ok = [r for r in table if r["option"] == opt and r["feasible"]]
        best[opt] = min(ok, key=lambda r: (r["units"], r["M11_abandon_pct"])) if ok else None
    margin = {}
    for opt in ("A", "B"):
        if best[opt]:
            nxt = [r for r in table if r["option"] == opt and r["llm_slots"] == best[opt]["llm_slots"] + 1 and r["sandbox_workers"] == best[opt]["sandbox_workers"]]
            margin[opt] = nxt[0] if nxt else None
    base = next((r for r in table if r["option"] == "A" and r["llm_slots"] == 5 and r["sandbox_workers"] == 1), None)
    return {"kind": "optimize", "params": p, "rate": rate, "table": table, "best": best, "margin": margin, "baseline": base,
            "limits": {"abandon_pct": abandon_limit, "session_min": session_limit},
            "saving_units": (best["A"]["units"] - best["B"]["units"]) if best["A"] and best["B"] else None}


# ---------------------------------------------------------------- validation (paper, Section 5.3)
def expected_values(p: SimParams) -> dict:
    """The analytic quantities the paper checks the simulation against."""
    tri = lambda k: sum(p.dists[k]) / 3.0   # noqa: E731  (mean of a triangular distribution)
    turns = (p.base_turns + p.lazy_extra_turns + p.base_turns) / 2.0
    gradings = sum(0.5 * (1 + (1 - q) + (1 - q) ** 2) for q in (p.pass_prob_lazy, p.pass_prob_perfectionist))   # third attempt always passes
    es = tri("llm_e1") if p.budgeted_context else tri("llm")
    login_fail = 1 - p.login_success_prob
    session = (turns * (tri("think") + es + (tri("build_context") if p.budgeted_context else 0.0)) + gradings * tri("sandbox")
               + (gradings - 1) * tri("revise_min") * 60.0 + (1 / p.login_success_prob) * tri("login_auth") + (login_fail / p.login_success_prob) * tri("login_retry")
               + tri("score"))
    rate = p.user_arrival_rate
    return {"turns": turns, "gradings": gradings, "resubmissions": gradings - 1, "llm_s": es, "session_s": session,
            "llm_util_pct": 100.0 * rate * turns * es / (3600.0 * p.llm_slots), "sandbox_util_pct": 100.0 * rate * gradings * tri("sandbox") / (3600.0 * p.sandbox_workers),
            "saturation_per_h": p.llm_slots * 3600.0 / (turns * es), "login_retry_share": login_fail}


def _check(name: str, expected: float, measured: float, tol: float, unit: str, note: str, rel: bool = False) -> dict:
    err = abs(measured - expected) / (abs(expected) or 1.0) if rel else abs(measured - expected)
    return {"name": name, "expected": round(expected, 3), "measured": round(measured, 3), "tolerance": tol, "tolerance_kind": "relative" if rel else "absolute",
            "unit": unit, "passed": bool(err <= tol), "error": round(err, 4), "note": note}


def validate(params: dict | None = None, reps: int = 4, progress=None, cancel=None) -> dict:
    """The paper's six checks, each against a quantity that does not need the simulation."""
    base = SimParams.from_dict({**(params or {}), "user_arrival_rate": 10, "llm_slots": 5, "sandbox_workers": 1, "auth_workers": 2, "budgeted_context": False})
    low = {**base.to_dict(), "user_arrival_rate": 5}
    plans = {"low": _grid(low, [{}], reps, 11), "base": _grid(base.to_dict(), [{}], reps, 21),
             "forty": _grid(base.to_dict(), [{"user_arrival_rate": 40}], reps, 31),
             "sweep": _grid(base.to_dict(), [{"user_arrival_rate": r} for r in (35, 40, 45, 50, 55)], 3, 41),
             "ample": _grid(base.to_dict(), [{"user_arrival_rate": 60, "llm_slots": 12, "sandbox_workers": 4}], 2, 51),
             "broken": _grid(base.to_dict(), [{"user_arrival_rate": 60}], 2, 61)}
    flat = [j for v in plans.values() for j in v]
    res = run_many(flat, progress, cancel)
    out, i = {}, 0
    for k, v in plans.items():
        out[k], i = res[i:i + len(v)], i + len(v)
    e_low, e_base = expected_values(SimParams.from_dict(low)), expected_values(base)
    m_low, m_base, m_forty = mean_of(out["low"]), mean_of(out["base"]), mean_of(out["forty"])
    e_forty = expected_values(SimParams.from_dict({**base.to_dict(), "user_arrival_rate": 40}))
    checks = [
        _check("1 Sanity: session time at 5/h equals the sum of mean service times", e_low["session_s"] / 60.0, m_low["M2_session_min"], 0.06, "min",
               "no queueing at the lowest load, so the session is the sum of its parts", rel=True),
        _check("1b Sanity: turn response at 5/h equals the mean LLM call", e_low["llm_s"], m_low["M1_turn_response_s"], 0.04, "s", "no waiting for a slot", rel=True),
        _check("2 Utilization law: LLM utilization at 10/h = rate x turns x E[S] / (3600 x slots)", e_base["llm_util_pct"], m_base["M4_llm_util_pct"], 2.5, "%",
               "the paper reports 22.2% and 23.1%"),
        _check("2b Utilization law: sandbox utilization at 10/h", e_base["sandbox_util_pct"], m_base["M5_sandbox_util_pct"], 2.5, "%", "the paper reports 16.8% and 17.3%"),
        _check("2c Utilization law at 40/h (a little lower once queueing starts)", e_forty["llm_util_pct"], m_forty["M4_llm_util_pct"], 9.0, "%", "paper: 92.4% expected, 86.5% measured"),
        _check("3 Input probabilities: login retries per login attempt", e_base["login_retry_share"], m_base["login_retries"] / max(m_base["logins"], 1), 0.015, "ratio",
               "input 6%; the paper measured 6.4%"),
        _check("3b Input probabilities: resubmissions per completed session", e_base["resubmissions"], m_base["resubmissions"] / max(m_base["completed"], 1), 0.06, "per session",
               "expected 0.315 from the pass probabilities 0.70 and 0.80 with a limit of 3 attempts"),
        _check("4 Conservation: throughput equals the arrival rate when nothing is lost (10/h)", 10.0, m_base["M3_throughput_per_h"], 0.06, "per h", "the paper measured 9.99", rel=True),
    ]
    # Little's law: L = lambda x W, with L the average number of students in the system (from the per-minute samples after the warm-up)
    sweep = {}
    for j, row in zip(plans["sweep"], out["sweep"]):
        sweep.setdefault(j["user_arrival_rate"], []).append(row)
    sweep_rows = {r: mean_of(v) for r, v in sweep.items()}
    over = [r for r, m in sweep_rows.items() if m["M11_abandon_pct"] > THRESHOLDS["abandon_pct"]]
    observed_break = min(over) if over else None
    checks.append({"name": "5 Saturation point: analytic LLM saturation vs the first rate above 5% abandonment", "expected": round(e_base["saturation_per_h"], 1),
                   "measured": observed_break, "tolerance": 12.0, "tolerance_kind": "absolute", "unit": "students/h",
                   "passed": observed_break is not None and 0 <= observed_break - e_base["saturation_per_h"] <= 12.0, "error": None,
                   "note": f"analytic {e_base['saturation_per_h']:.1f}/h (paper {ANALYTIC_SATURATION_PER_H}), observed break near 45/h in the paper"})
    ample, broken = mean_of(out["ample"]), mean_of(out["broken"])
    checks.append(_check("6 Extreme value: 12 LLM slots + 4 workers at 60/h lose nobody", 0.0, ample["M11_abandon_pct"], 0.3, "%", "paper: 0.00%"))
    checks.append(_check("6b Extreme value: with ample capacity the turn response is the mean LLM call", 13.0, ample["M1_turn_response_s"], 0.1, "s", "paper: 13.1 s", rel=True))
    checks.append(_check("6c Extreme value: 5 slots + 1 worker at 60/h lose about half", 47.7, broken["M11_abandon_pct"], 8.0, "%", "paper: 47.7%"))
    return {"kind": "validate", "checks": checks, "passed": sum(c["passed"] for c in checks), "total": len(checks),
            "expected": {"baseline": e_base, "low": e_low}, "sweep": [{"rate": r, **m} for r, m in sorted(sweep_rows.items())]}
