"""Simulation jobs for the admin page: batch experiments (with a progress bar) and the live run (simulated time advancing in real time).

In memory only: results can be exported, and a restart starts clean. At most MAX_RUNNING jobs run at once.
"""
from __future__ import annotations

import secrets
import threading
import time

from . import experiments as E
from .model import SimParams, Simulation

MAX_RUNNING, MAX_KEPT = 3, 30
KINDS = ("live", "baseline", "stress", "optimize", "validate")


class Job:
    def __init__(self, kind: str, params: dict, options: dict):
        self.id = secrets.token_urlsafe(6)
        self.kind, self.params, self.options = kind, params, options
        self.status, self.created, self.finished = "queued", time.time(), None
        self.progress = {"done": 0, "total": 1}
        self.result: dict | None = None
        self.error: str | None = None
        self.cancel = threading.Event()
        # live run
        self.sim: Simulation | None = None
        self.speed = float(options.get("speed", 600.0))
        self.paused = False
        self.live: dict | None = None
        self.series: list[dict] = []
        self.pending: list[dict] = []
        self.applied: list[dict] = []
        self.lock = threading.Lock()

    def view(self, full: bool = True) -> dict:
        d = {"id": self.id, "kind": self.kind, "status": self.status, "progress": self.progress, "created": self.created, "finished": self.finished,
             "error": self.error, "options": self.options, "params": self.params}
        if full:
            d.update(result=self.result, live=self.live, series=self.series[-240:], speed=self.speed, paused=self.paused, applied=self.applied[-20:])
        return d


class SimJobs:
    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def running(self) -> int:
        return sum(1 for j in self.jobs.values() if j.status in ("queued", "running"))

    def start(self, kind: str, params: dict | None, options: dict | None = None) -> Job:
        if kind not in KINDS:
            raise ValueError(f"unknown kind {kind!r}")
        options = {k: v for k, v in (options or {}).items() if v is not None}
        SimParams.from_dict(params)   # fail early on bad parameters
        reps = int(options.get("reps", 0) or 0)
        if reps and not 1 <= reps <= 20:
            raise ValueError("reps must be between 1 and 20")
        if len(options.get("rates") or []) > 40:
            raise ValueError("at most 40 arrival rates")
        if any(not isinstance(r, (int, float)) or isinstance(r, bool) or not 0 < r <= 1000 for r in options.get("rates") or []):
            raise ValueError("every arrival rate must be between 0 and 1000 students per hour")
        with self._lock:
            if self.running() >= MAX_RUNNING:
                raise OverflowError("too many simulations are running; wait for one to finish or cancel it")
            job = Job(kind, SimParams.from_dict(params).to_dict(), options)
            self.jobs[job.id] = job
            for old in sorted(self.jobs.values(), key=lambda j: j.created)[:-MAX_KEPT]:
                if old.status not in ("queued", "running"):
                    self.jobs.pop(old.id, None)
        threading.Thread(target=self._run, args=(job,), daemon=True, name=f"sim-{job.id}").start()
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    # ---- running
    def _run(self, job: Job) -> None:
        job.status = "running"
        try:
            if job.kind == "live":
                self._live(job)
            else:
                job.result = self._batch(job)
            job.status = "cancelled" if job.cancel.is_set() else "done"
        except E.Cancelled:
            job.status = "cancelled"
        except Exception as e:   # noqa: BLE001  (shown to the admin instead of killing the thread silently)
            job.status, job.error = "error", f"{type(e).__name__}: {e}"
        job.finished = time.time()

    def _batch(self, job: Job) -> dict:
        o = job.options

        def progress(done, total):
            job.progress = {"done": done, "total": total}
        common = {"progress": progress, "cancel": job.cancel.is_set}
        if job.kind == "baseline":
            return E.experiment1(job.params, reps=int(o.get("reps", 10)), **common)
        if job.kind == "stress":
            return E.experiment2(job.params, rates=o.get("rates"), reps=int(o.get("reps", 5)), **common)
        if job.kind == "optimize":
            return E.experiment3(job.params, rate=float(o.get("rate", 60)), reps=int(o.get("reps", 5)), **common)
        return E.validate(job.params, reps=int(o.get("reps", 4)), **common)

    def _live(self, job: Job) -> None:
        sim = Simulation(SimParams.from_dict(job.params))
        job.sim = sim
        end, last = sim.p.run_seconds, time.monotonic()
        job.live = sim.snapshot()
        while not job.cancel.is_set() and sim.sch.now < end:
            time.sleep(0.1)
            now = time.monotonic()
            dt, last = now - last, now
            with job.lock:
                while job.pending:
                    ch = job.pending.pop(0)
                    try:
                        job.applied.append({"t": sim.sch.now, "changes": sim.apply(ch)})
                    except ValueError as e:
                        job.applied.append({"t": sim.sch.now, "error": str(e), "changes": ch})
                if job.paused:
                    continue
                sim.run_until(min(end, sim.sch.now + job.speed * dt))
                job.live = sim.snapshot()
                job.series = sim.series[-240:]
            job.progress = {"done": int(sim.sch.now), "total": int(end)}
        job.result = {"kind": "live", "metrics": sim.metrics(), "params": sim.p.to_dict(), "applied": job.applied}

    # ---- controls
    def control(self, job: Job, action: str, speed: float | None = None, changes: dict | None = None) -> None:
        if action == "cancel":
            job.cancel.set()
            return
        if job.kind != "live" or job.status != "running":
            raise ValueError("only a running live simulation can be controlled")
        with job.lock:
            if action == "pause":
                job.paused = True
            elif action == "resume":
                job.paused = False
            elif action == "speed":
                job.speed = float(min(max(speed or 1.0, 1.0), 7200.0))
            elif action == "apply":
                if not changes:
                    raise ValueError("no changes given")
                SimParams.from_dict({**job.sim.p.to_dict(), **{k: v for k, v in changes.items() if k in Simulation.LIVE_FIELDS}})   # validate before queueing
                job.pending.append(changes)
            else:
                raise ValueError(f"unknown action {action!r}")


def to_csv(job: Job) -> str:
    """The job's result as CSV (one table per kind)."""
    r = job.result or {}
    rows: list[dict] = []
    if job.kind == "stress":
        rows = r.get("rows", [])
    elif job.kind == "optimize":
        rows = r.get("table", [])
    elif job.kind == "baseline":
        rows = [r.get("mean", {})]
    elif job.kind == "validate":
        rows = r.get("checks", [])
    elif job.kind == "live":
        rows = job.series
    if not rows:
        return ""
    cols = list(rows[0].keys())
    esc = lambda v: '"' + str(v).replace('"', '""') + '"' if isinstance(v, str) else ("" if v is None else str(v))   # noqa: E731
    return "\n".join([",".join(cols)] + [",".join(esc(row.get(c)) for c in cols) for row in rows]) + "\n"
