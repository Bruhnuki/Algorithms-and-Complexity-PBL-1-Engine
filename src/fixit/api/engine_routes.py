"""The AlgoCom engines over HTTP, for the admin Engines tab: the solve endpoint, the live feed of real engine calls, workbenches, benchmark."""
from __future__ import annotations

import math
import random
import time
from typing import Literal

from fastapi import Body, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..engines import e1, e2, real
from ..gateway import context as gctx
from ..gateway.gateway import DOD_TEXT

cc, lg = real.cc, real.lg
HTTP = {"MALFORMED_REQUEST": 400, "UNKNOWN_ALGORITHM": 400, "VALIDATION_ERROR": 422, "INFEASIBLE": 422, "ILLEGAL_TRANSITION": 409, "LIMIT_EXCEEDED": 413, "INTERNAL_ERROR": 500}
EXACT_CELLS_LIMIT = 8_000_000   # the exact comparator is skipped above this: it would stall the server for seconds


class E1In(BaseModel):
    source: Literal["synthetic", "run"] = "synthetic"
    run_id: int | None = None
    n: int = Field(default=120, ge=1, le=2000)
    seed: int = 1
    stage: Literal["PLANNING", "STANDUP", "BUILD", "REVIEW"] = "BUILD"
    advance_to: Literal["STANDUP", "BUILD", "REVIEW"] | None = None
    budget: int = Field(default=3000, ge=50, le=32000)
    mode: Literal["auto", "exact", "greedy"] = "auto"


class E2In(BaseModel):
    source: Literal["synthetic", "cohort"] = "synthetic"
    n: int = Field(default=30, ge=1, le=2000)
    mean_pre: float = Field(default=40, ge=0, le=100)
    mean_post: float = Field(default=65, ge=0, le=100)
    spread: float = Field(default=15, ge=0, le=50)
    seed: int = 1
    B: int = Field(default=1000, ge=100, le=10000)
    run_id: int | None = None


def _synthetic_segments(n: int, seed: int) -> list:
    """The paper's Task 1 instance: tokens 20-300, relevance v = 0.4 e^(-ln2 age/20) + 0.2 a + 0.4 iota with 10% flagged, stages in order."""
    rng, out, stages = random.Random(seed), [], ["PLANNING", "STANDUP", "BUILD", "REVIEW"]
    for i in range(n):
        stage = stages[min(3, i * 4 // n)]
        v = 0.4 * math.exp(-math.log(2) * (n - 1 - i) / 20) + 0.2 * (1.0 if stage == "BUILD" else 0.5) + (0.4 if rng.random() < 0.10 else 0)
        out.append(cc.Segment(f"s{i}", rng.randint(20, 300), round(v, 6), stage))
    return out


def _stat(res: dict, ms: float) -> dict:
    return {"mode": res.get("mode", "recent"), "value": res["total_relevance"], "tokens_used": res["tokens_used"], "n_selected": len(res["selected_segment_ids"]),
            "dp_cells": res.get("dp_cells"), "gap_bound": res.get("abs_gap_bound"), "ms": round(ms, 3)}


def register(app, *, instructor, ApiError, DbSession, db_dep, M, get_cached, content):
    def timed(fn, *a, **k):
        t0 = time.perf_counter()
        r = fn(*a, **k)
        return r, (time.perf_counter() - t0) * 1000

    @app.post("/api/v1/algorithm/solve")
    def solve_endpoint(request: dict = Body(...), _=Depends(instructor)):
        """The engines' single entry point (pbl_engine/engine/solve.py): `algorithm` is context_chaining or learning_gain."""
        t0 = time.perf_counter()
        out = real.solver.solve(request)
        real.record("E1" if out.get("algorithm") == "context_chaining" else "E2", "solve:" + str(out.get("algorithm")), t0, status=out["status"], source="api",
                    **{k: v for k, v in (out.get("metrics") or {}).items() if k != "runtime_ms"})
        return JSONResponse(out, status_code=200 if out["status"] == "ok" else HTTP.get(out["error"]["code"], 400))

    @app.get("/api/v1/instructor/engines/feed")
    def feed(since: int = 0, _=Depends(instructor)):
        return real.feed(since)

    def my_runs(db, user):
        runs = []
        for co in db.scalars(select(M.Cohort).where(M.Cohort.instructor_id == user.id)):
            for stu in db.scalars(select(M.User).where(M.User.cohort_id == co.id, M.User.role == "student")):
                for r in db.scalars(select(M.Run).where(M.Run.user_id == stu.id).order_by(M.Run.id)):
                    runs.append((stu, r))
        return runs

    @app.get("/api/v1/instructor/engines/runs")
    def runs(user=Depends(instructor), db: DbSession = Depends(db_dep)):
        with db:
            out = []
            for stu, r in my_runs(db, user):
                s = get_cached(db, r)["state"]
                if (s.get("x") or {}).get("tutorial"):
                    continue
                out.append({"run_id": r.id, "student": stu.display_name, "status": r.status, "log": len(s["process_log"])})
            return {"runs": out}

    def owned(db, user, run_id):
        for _stu, r in my_runs(db, user):
            if r.id == run_id:
                return r
        raise ApiError(403, "FORBIDDEN", "not your cohort")

    @app.post("/api/v1/instructor/engines/e1")
    def e1_workbench(body: E1In, user=Depends(instructor), db: DbSession = Depends(db_dep)):
        """Run E1 on a synthetic transcript or on a real run's transcript, with the policy you pick, and compare it with the baselines."""
        with db:
            if body.source == "run":
                if body.run_id is None:
                    raise ApiError(422, "VALIDATION_ERROR", "pick a run")
                run = owned(db, user, body.run_id)
                state = get_cached(db, run)["state"]
                lines = db.scalars(select(M.TranscriptLine).where(M.TranscriptLine.run_id == run.id).order_by(M.TranscriptLine.id)).all()
                raw = [{"id": "persona", "text": "Persona and rules for the teammate.", "seq": 0, "pinned": True}, {"id": "dod", "text": DOD_TEXT, "seq": 0, "pinned": True}]
                raw += gctx.memory_segments(state, content) + [{"id": f"l{ln.id}", "text": f"{ln.speaker}: {ln.text}", "seq": 1000 + ln.id} for ln in lines]
                segs, _ = e1.to_engine(raw, body.stage)
                names = {s["id"]: s["text"] for s in raw}
            else:
                segs = [cc.Segment("persona", 60, 1.0, "PLANNING", True)] + _synthetic_segments(body.n, body.seed)
                names = {}
            stage = body.stage
            if body.advance_to:
                try:
                    stage = cc.advance(stage, body.advance_to)
                except cc.IllegalTransitionError as e:
                    raise ApiError(409, "ILLEGAL_TRANSITION", str(e)) from e
            try:
                cells = cc.estimate_cells(segs, body.budget, stage)
                chosen, ms = timed(cc.select_context, segs, body.budget, stage, mode=body.mode)
            except cc.InfeasibleError as e:
                raise ApiError(422, "INFEASIBLE", str(e)) from e
            real.record("E1", "select_context", 0, ms=ms, stage=stage, mode=chosen["mode"], segments=len(segs), budget=body.budget,
                        chosen=len(chosen["selected_segment_ids"]), tokens_used=chosen["tokens_used"], dp_cells=chosen["dp_cells"], est_cells=cells,
                        gap_bound=chosen.get("abs_gap_bound"), source="admin")
            compare = {"chosen": _stat(chosen, ms)}
            g, gms = timed(cc.select_segments_greedy, segs, body.budget, stage)
            compare["greedy"] = _stat(g, gms)
            if cells <= EXACT_CELLS_LIMIT:
                ex, ems = timed(cc.select_segments, segs, body.budget, stage)
                compare["exact"] = _stat(ex, ems)
            else:
                compare["exact"] = {"skipped": f"{cells:,} DP cells is too many to run live"}
            rc, rms = timed(cc.recent_baseline, segs, body.budget, stage)
            compare["recent"] = _stat(rc, rms)
            if "value" in compare["exact"]:
                opt = compare["exact"]["value"] or 1
                for k in ("exact", "greedy", "recent", "chosen"):
                    compare[k]["of_optimal"] = round(compare[k]["value"] / opt, 4)
            picked = set(chosen["selected_segment_ids"])
            eligible = cc.ELIGIBLE[stage]
            rows = [{"id": s.id, "tokens": s.tokens, "relevance": round(s.relevance, 4), "stage": s.stage, "pinned": s.pinned, "eligible": s.pinned or s.stage in eligible,
                     "selected": s.id in picked, "text": names.get(s.id)} for s in segs]
            return {"stage": stage, "budget": body.budget, "est_cells": cells, "compare": compare, "segments": rows[-400:], "total_segments": len(rows)}

    @app.post("/api/v1/instructor/engines/e2")
    def e2_workbench(body: E2In, user=Depends(instructor), db: DbSession = Depends(db_dep)):
        """Learning gain with a bootstrap interval (synthetic cohort, or the real cohort's first-to-latest run), and the saturating process score on a run's behaviours."""
        with db:
            note = None
            if body.source == "cohort":
                per: dict = {}
                for stu, r in my_runs(db, user):
                    s = get_cached(db, r)["state"]
                    if r.status == "ended" and not (s.get("x") or {}).get("tutorial"):
                        per.setdefault(stu.id, []).append(e2.process_score(s["process_log"], content.balance["process_score"]))
                students = [{"pre": v[0], "post": v[-1]} for v in per.values() if len(v) >= 2]
                maxs = 100.0
                if not students:
                    note = "No student has two finished runs yet: the gain is measured from each student's first to latest run's process score."
            else:
                rng = random.Random(body.seed)
                clamp = lambda x: min(100.0, max(0.0, x))   # noqa: E731
                students = []
                for _ in range(body.n):
                    pre = clamp(rng.gauss(body.mean_pre, body.spread))
                    students.append({"pre": round(pre, 2), "post": round(clamp(pre + rng.gauss(body.mean_post - body.mean_pre, body.spread / 2)), 2)})
                maxs = 100.0
            t0 = time.perf_counter()
            summary = lg.cohort_summary(students, maxs, B=body.B, seed=body.seed)
            real.record("E2", "cohort_summary", t0, students=len(students), bootstrap=body.B, source="admin")
            gains = [round(g, 4) for g in (lg.normalized_gain(s["pre"], s["post"], maxs) for s in students) if g is not None]
            out = {"summary": summary, "gains": gains, "students": students[:200], "note": note, "source": body.source}
            log = None
            if body.run_id is not None:
                log = get_cached(db, owned(db, user, body.run_id))["state"]["process_log"]
            elif body.source == "synthetic":
                keys = list(e2.CATEGORIES) + ["dod_skipped"]
                rng = random.Random(body.seed)
                log = [rng.choice(keys) for _ in range(30)]
            if log is not None:
                w = content.balance["process_score"]
                good = [k for k in log if k in e2.CATEGORIES]
                sat = e2.saturating(log)
                out["process"] = {"events": [k for k in log], "linear": [e2.process_score(log[: i + 1], w) for i in range(len(log))],
                                  "saturating_curve": sat["curve"], "saturating": sat["score"], "by_stage": sat["by_stage"], "good_events": len(good)}
            return out

    @app.post("/api/v1/instructor/engines/benchmark")
    def benchmark(_=Depends(instructor)):
        """The engines' own measurements (from pbl_engine/benchmark.py), taken here on this machine: DP scaling, policy, bootstrap, accumulator."""
        rng = random.Random(0)
        mk = lambda n: [cc.Segment(f"s{i}", rng.randint(20, 300), rng.random(), "BUILD") for i in range(n)]   # noqa: E731

        def best(fn, reps=3):
            return min(timed(fn)[1] for _ in range(reps))
        dp = []
        for n, B in ((100, 2000), (200, 4000), (400, 8000)):
            segs = mk(n)
            cells = cc.select_segments(segs, B, "BUILD")["dp_cells"]
            ms = best(lambda: cc.select_segments(segs, B, "BUILD"), 2)
            dp.append({"n": n, "budget": B, "cells": cells, "ms": round(ms, 2), "ns_per_cell": round(ms * 1e6 / cells, 1)})
        big = mk(2000)
        g = cc.select_segments_greedy(big, 32000, "BUILD")
        policy = {"n": 2000, "budget": 32000, "est_cells": cc.estimate_cells(big, 32000, "BUILD"), "greedy_ms": round(best(lambda: cc.select_segments_greedy(big, 32000, "BUILD")), 2),
                  "auto_mode": cc.select_context(big, 32000, "BUILD")["mode"], "gap_bound": g["abs_gap_bound"]}
        vals = [rng.random() for _ in range(10)]
        boot = [{"B": b, "ms": round(best(lambda b=b: lg.bootstrap_ci(vals, B=b)), 2)} for b in (500, 1000, 2000, 4000)]
        cats = {"a": {"weight": 0.4, "eta": 0.3}, "b": {"weight": 0.3, "eta": 0.5}, "c": {"weight": 0.2, "eta": 0.2}, "d": {"weight": 0.1, "eta": 0.6}}
        st = list(cc.STAGES)
        ev = [(f"e{i}", st[i % 4], "abcd"[i % 4], rng.random()) for i in range(10_000)]

        def acc():
            a = lg.ProcessAccumulator(cats)
            for e in ev:
                a.record(*e)
        ams = best(acc, 3)
        real.record("E1", "benchmark", 0, ms=sum(d["ms"] for d in dp), source="admin")
        return {"dp": dp, "ns_per_cell_ratio": round(max(d["ns_per_cell"] for d in dp) / min(d["ns_per_cell"] for d in dp), 2), "policy": policy, "bootstrap": boot,
                "accumulator": {"events": len(ev), "ms": round(ams, 1), "us_per_event": round(ams * 1000 / len(ev), 2)}}
