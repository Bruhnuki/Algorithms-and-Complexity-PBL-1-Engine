"""Instructor-only routes for the Modeling and Simulation demo: presets, jobs (batch experiments and the live run), controls, CSV export."""
from __future__ import annotations

from fastapi import Depends
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from ..sim import experiments as E
from ..sim import reference
from ..sim.calibration import measure_deployment
from ..sim.jobs import KINDS, SimJobs, to_csv
from ..sim.model import PAPER_DISTS, SimParams


class JobIn(BaseModel):
    kind: str = Field(pattern="^(live|baseline|stress|optimize|validate)$")
    params: dict = Field(default_factory=dict)
    reps: int | None = Field(default=None, ge=1, le=20)
    rates: list[float] | None = Field(default=None, max_length=40)
    rate: float | None = Field(default=None, gt=0, le=1000)
    speed: float | None = Field(default=None, ge=1, le=7200)


class ControlIn(BaseModel):
    action: str = Field(pattern="^(cancel|pause|resume|speed|apply)$")
    speed: float | None = Field(default=None, ge=1, le=7200)
    changes: dict | None = None


PRESETS = [
    {"id": "paper", "name": "Paper baseline (10 students/h)", "params": {"user_arrival_rate": 10}, "note": "Experiment 1: 2 auth workers, 5 LLM slots, 1 sandbox worker, no E1"},
    {"id": "launch", "name": "Launch day (60 students/h)", "params": {"user_arrival_rate": 60}, "note": "Experiment 2 at the broken load: about half of the students give up"},
    {"id": "option_a", "name": "Option A: scale resources (7 LLM + 2 sandbox)", "params": {"user_arrival_rate": 60, "llm_slots": 7, "sandbox_workers": 2}, "note": "9 resource units, no E1"},
    {"id": "option_b", "name": "Option B: E1 budgeted context (6 LLM + 2 sandbox)", "params": {"user_arrival_rate": 60, "llm_slots": 6, "sandbox_workers": 2, "budgeted_context": True},
     "note": "8 resource units, shorter LLM calls"},
]


def register(app, *, instructor, ApiError, content, hasher, ai_provider):
    jobs = SimJobs()
    app.state.sim_jobs = jobs

    def bad(e: Exception):
        raise ApiError(422, "BAD_SIMULATION_REQUEST", str(e)) from e

    @app.get("/api/v1/instructor/sim/presets")
    def presets(_=Depends(instructor)):
        return {"presets": PRESETS, "defaults": SimParams().to_dict(), "paper_dists": {k: list(v) for k, v in PAPER_DISTS.items()}, "kinds": list(KINDS)}

    @app.get("/api/v1/instructor/sim/reference")
    def ref(_=Depends(instructor)):
        return {"exp2": {str(k): dict(zip(reference.EXP2_COLUMNS, v)) for k, v in reference.EXP2.items()}, "table1": reference.TABLE1,
                "table3": [dict(zip(("name", "llm_slots", "sandbox_workers", "units", "M11_abandon_pct", "M2_session_min", "M3_throughput_per_h", "M4_llm_util_pct", "budgeted_context"), r))
                           for r in reference.TABLE3], "thresholds": reference.THRESHOLDS, "break_point": reference.BREAK_POINT_PER_H,
                "saturation": reference.ANALYTIC_SATURATION_PER_H}

    @app.post("/api/v1/instructor/sim/calibrate")
    def calibrate(_=Depends(instructor)):
        """Time this deployment's real authentication, interpreter and AI server (a few seconds)."""
        return measure_deployment(content, hasher, ai_provider())

    @app.post("/api/v1/instructor/sim/jobs", status_code=201)
    def start(body: JobIn, _=Depends(instructor)):
        try:
            job = jobs.start(body.kind, body.params, {"reps": body.reps, "rates": body.rates, "rate": body.rate, "speed": body.speed})
        except OverflowError as e:
            raise ApiError(429, "TOO_MANY_SIMULATIONS", str(e)) from e
        except (ValueError, TypeError) as e:
            bad(e)
        return job.view(full=False)

    @app.get("/api/v1/instructor/sim/jobs")
    def listing(_=Depends(instructor)):
        return {"jobs": [j.view(full=False) for j in sorted(jobs.jobs.values(), key=lambda j: -j.created)]}

    def find(job_id: str):
        job = jobs.get(job_id)
        if job is None:
            raise ApiError(404, "NOT_FOUND", "no such simulation")
        return job

    @app.get("/api/v1/instructor/sim/jobs/{job_id}")
    def show(job_id: str, _=Depends(instructor)):
        return find(job_id).view()

    @app.post("/api/v1/instructor/sim/jobs/{job_id}/control")
    def control(job_id: str, body: ControlIn, _=Depends(instructor)):
        job = find(job_id)
        try:
            jobs.control(job, body.action, body.speed, body.changes)
        except (ValueError, TypeError) as e:
            bad(e)
        return job.view()

    @app.get("/api/v1/instructor/sim/jobs/{job_id}/export.csv")
    def export(job_id: str, _=Depends(instructor)):
        return PlainTextResponse(to_csv(find(job_id)), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=simulation-{job_id}.csv"})
