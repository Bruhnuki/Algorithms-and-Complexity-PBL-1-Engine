"""The paper's model: one Student entity moving through login, repeated agent turns (LLM), sandbox autograding and final scoring,
competing with other students for three resource pools. Block names in comments are the AnyLogic blocks of the paper's flowchart.

Paper parameter -> field:  user_arrival_rate, authWorkers=auth_workers, llmSlots=llm_slots, numSandboxWorkers=sandbox_workers,
budgetedContext=budgeted_context, baseTurns=base_turns, lazyExtraTurns=lazy_extra_turns, passProbLazy / passProbPerfectionist,
loginSuccessProb, patienceSeconds, sandboxPatience, warmupSeconds.
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field, fields

from .des import Pool, Scheduler

# (min, mode, max) of the triangular distributions, in seconds unless the name says minutes (paper, Section 3.2)
PAPER_DISTS = {
    "login_auth": (0.05, 0.10, 0.25), "login_retry": (10, 20, 40), "think": (20, 45, 90), "build_context": (0.001, 0.05, 0.13),
    "llm": (4, 10, 25), "llm_e1": (3, 8, 20), "sandbox": (20, 40, 90), "revise_min": (2, 4, 8), "score": (0.002, 0.003, 0.006),
}


@dataclass
class SimParams:
    user_arrival_rate: float = 10.0          # students starting a session per hour
    auth_workers: int = 2
    llm_slots: int = 5
    sandbox_workers: int = 1
    budgeted_context: bool = False           # Engine E1 budgeted context (Option B): shorter LLM calls, tiny extra step
    base_turns: int = 30
    lazy_extra_turns: int = 4
    pass_prob_lazy: float = 0.70
    pass_prob_perfectionist: float = 0.80
    login_success_prob: float = 0.94
    patience_seconds: float = 120.0
    sandbox_patience: float = 300.0
    warmup_seconds: float = 1800.0
    run_seconds: float = 86400.0
    seed: int = 1
    max_attempts: int = 3
    dists: dict = field(default_factory=lambda: {k: tuple(v) for k, v in PAPER_DISTS.items()})

    @classmethod
    def from_dict(cls, d: dict | None) -> "SimParams":
        names = {f.name for f in fields(cls)}
        clean = {k: v for k, v in (d or {}).items() if k in names and k != "dists"}
        p = cls(**clean)
        for k, v in ((d or {}).get("dists") or {}).items():
            if k in PAPER_DISTS and len(v) == 3:
                p.dists[k] = tuple(float(x) for x in v)
        p.validate()
        return p

    def validate(self) -> None:
        if not 0 < self.user_arrival_rate <= 1000:
            raise ValueError("user_arrival_rate must be between 0 and 1000 per hour")
        for name, lo, hi in (("auth_workers", 1, 64), ("llm_slots", 1, 256), ("sandbox_workers", 1, 64)):
            if not lo <= getattr(self, name) <= hi:
                raise ValueError(f"{name} must be between {lo} and {hi}")
        if not 0 <= self.login_success_prob <= 1 or not 0 <= self.pass_prob_lazy <= 1 or not 0 <= self.pass_prob_perfectionist <= 1:
            raise ValueError("probabilities must be between 0 and 1")
        if not 0 <= self.warmup_seconds < self.run_seconds <= 31 * 86400:
            raise ValueError("run_seconds must be longer than warmup_seconds and at most 31 days")
        for k, (a, m, b) in self.dists.items():
            if not 0 <= a <= m <= b:
                raise ValueError(f"distribution {k}: need min <= mode <= max")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["dists"] = {k: list(v) for k, v in self.dists.items()}
        return d


# event kinds
ARRIVAL, AUTH_DONE, LOGIN_RETRY, THINK_DONE, CTX_DONE, LLM_DONE, SBX_DONE, REVISE_DONE, SCORE_DONE, TIMEOUT, WARMUP, SAMPLE = range(12)


class Student:
    """The entity. Attributes as in the paper (Section 3.2)."""
    __slots__ = ("persona", "turns_needed", "turns_done", "pass_prob", "attempts", "tests_pass", "t_start", "t_sent", "t_q", "waiting", "token")

    def __init__(self):
        self.turns_done = self.attempts = self.token = 0
        self.tests_pass = False
        self.waiting = None
        self.t_q = self.t_sent = 0.0


class Simulation:
    """One run. `run_until(t)` advances the clock, so the same object serves batch runs and the live demo."""

    def __init__(self, params: SimParams):
        self.p = params
        self.rng = random.Random(params.seed)
        self.sch = Scheduler()
        self.auth, self.llm, self.sbx = Pool("auth", params.auth_workers), Pool("llm", params.llm_slots), Pool("sandbox", params.sandbox_workers)
        self.in_system = 0
        self.series: list[dict] = []
        self._reset_counters()
        self._last = {"t": 0.0, "llm": (0.0, 0.0), "sbx": (0.0, 0.0), "auth": (0.0, 0.0)}
        self.sch.at(self.rng.expovariate(params.user_arrival_rate / 3600.0), ARRIVAL)
        if params.warmup_seconds > 0:
            self.sch.at(params.warmup_seconds, WARMUP)
        self.sch.at(60.0, SAMPLE)
        self._handlers = {ARRIVAL: self._arrival, AUTH_DONE: self._auth_done, LOGIN_RETRY: self._login_retry, THINK_DONE: self._think_done,
                          CTX_DONE: self._ctx_done, LLM_DONE: self._llm_done, SBX_DONE: self._sbx_done, REVISE_DONE: self._revise_done,
                          SCORE_DONE: self._score_done, TIMEOUT: self._timeout, WARMUP: self._warmup, SAMPLE: self._sample}

    # ---- statistics (reset once, at the end of the warm-up period)
    def _reset_counters(self) -> None:
        self.n_arrived = self.n_completed = self.n_abandon_llm = self.n_abandon_sbx = self.n_turns = 0
        self.turn_sum = self.session_sum = self.llm_wait_sum = self.sbx_wait_sum = 0.0
        self.llm_wait_n = self.sbx_wait_n = 0
        self.n_logins = self.n_login_retries = self.n_gradings = self.n_resubmissions = self.n_sessions_graded = 0
        self.t_stats = self.sch.now if hasattr(self, "sch") else 0.0

    def _warmup(self, _):
        self._reset_counters()
        self.t_stats = self.sch.now
        for pool in (self.auth, self.llm, self.sbx):
            pool.reset_stats(self.sch.now)
        self._last = {"t": self.sch.now, "llm": (0.0, 0.0), "sbx": (0.0, 0.0), "auth": (0.0, 0.0)}   # the per-minute samples measure from here

    def _tri(self, name: str) -> float:
        a, m, b = self.p.dists[name]
        return self.rng.triangular(a, b, m) if b > a else a

    # ---- the flowchart
    def _arrival(self, _):                       # studentSource
        now, p = self.sch.now, self.p
        self.sch.at(now + self.rng.expovariate(p.user_arrival_rate / 3600.0), ARRIVAL)
        s = Student()
        lazy = self.rng.random() < 0.5
        s.persona = 1 if lazy else 2
        s.turns_needed = p.base_turns + (p.lazy_extra_turns if lazy else 0)
        s.pass_prob = p.pass_prob_lazy if lazy else p.pass_prob_perfectionist
        s.t_start = now
        self.n_arrived += 1
        self.in_system += 1
        self._seize_auth(s)

    def _seize_auth(self, s):                    # seizeAuth (no patience: logins wait)
        if self.auth.take(self.sch.now):
            self.sch.after(self._tri("login_auth"), AUTH_DONE, s)   # loginAuth
        else:
            self.auth.wait(self.sch.now, s)

    def _auth_done(self, s):                     # releaseAuth, checkLogin
        nxt = self.auth.release(self.sch.now)
        if nxt is not None:
            self.sch.after(self._tri("login_auth"), AUTH_DONE, nxt)
        self.n_logins += 1
        if self.rng.random() < self.p.login_success_prob:
            self._think(s)
        else:
            self.n_login_retries += 1
            self.sch.after(self._tri("login_retry"), LOGIN_RETRY, s)   # loginRetry

    def _login_retry(self, s):
        self._seize_auth(s)

    def _think(self, s):                         # studentThink
        self.sch.after(self._tri("think"), THINK_DONE, s)

    def _think_done(self, s):
        s.t_sent = self.sch.now                  # records the send time
        if self.p.budgeted_context:              # buildContext (Engine E1)
            self.sch.after(self._tri("build_context"), CTX_DONE, s)
        else:
            self._seize_llm(s)

    def _ctx_done(self, s):
        self._seize_llm(s)

    def _seize_llm(self, s):                     # seizeLLM, with an exit on timeout after patienceSeconds
        now = self.sch.now
        s.t_q = now
        if self.llm.take(now):
            self._llm_start(s, 0.0)
        else:
            s.token += 1
            s.waiting = self.llm
            self.llm.wait(now, s)
            self.sch.at(now + self.p.patience_seconds, TIMEOUT, (s, s.token))

    def _llm_start(self, s, waited: float):
        self.llm_wait_sum += waited
        self.llm_wait_n += 1
        self.sch.after(self._tri("llm_e1" if self.p.budgeted_context else "llm"), LLM_DONE, s)   # llmCall

    def _llm_done(self, s):                      # releaseLLM
        now = self.sch.now
        nxt = self.llm.release(now)
        if nxt is not None:
            nxt.waiting = None
            self._llm_start(nxt, now - nxt.t_q)
        s.turns_done += 1
        self.n_turns += 1
        self.turn_sum += now - s.t_sent
        if s.turns_done < s.turns_needed:        # moreTurns
            self._think(s)
        else:
            self._seize_sbx(s)

    def _seize_sbx(self, s):                     # seizeSandbox, timeout after sandboxPatience
        now = self.sch.now
        s.t_q = now
        if self.sbx.take(now):
            self._sbx_start(s, 0.0)
        else:
            s.token += 1
            s.waiting = self.sbx
            self.sbx.wait(now, s)
            self.sch.at(now + self.p.sandbox_patience, TIMEOUT, (s, s.token))

    def _sbx_start(self, s, waited: float):
        self.sbx_wait_sum += waited
        self.sbx_wait_n += 1
        s.attempts += 1
        self.n_gradings += 1
        self.sch.after(self._tri("sandbox"), SBX_DONE, s)   # runTests

    def _sbx_done(self, s):                      # releaseSandbox, checkTests
        now = self.sch.now
        nxt = self.sbx.release(now)
        if nxt is not None:
            nxt.waiting = None
            self._sbx_start(nxt, now - nxt.t_q)
        s.tests_pass = self.rng.random() < s.pass_prob or s.attempts >= self.p.max_attempts
        if s.tests_pass:
            self.sch.after(self._tri("score"), SCORE_DONE, s)   # computeScore (Engine E2)
        else:
            self.n_resubmissions += 1
            self.sch.after(self._tri("revise_min") * 60.0, REVISE_DONE, s)   # reviseSolution

    def _revise_done(self, s):
        self._seize_sbx(s)

    def _score_done(self, s):                    # studentExit
        self.n_completed += 1
        self.n_sessions_graded += 1
        self.session_sum += self.sch.now - s.t_start
        self.in_system -= 1

    def _timeout(self, payload):                 # sinkAbandonedLLM / sinkAbandonedSbx
        s, token = payload
        pool = s.waiting
        if pool is None or s.token != token:
            return                               # it was served in time
        pool.leave_queue(self.sch.now, s)
        s.waiting = None
        if pool is self.llm:
            self.n_abandon_llm += 1
        else:
            self.n_abandon_sbx += 1
        self.in_system -= 1

    def _sample(self, _):                        # the cyclic 60 s sampling event
        now = self.sch.now
        for pool in (self.auth, self.llm, self.sbx):
            pool._tick(now)
        dt = max(now - self._last["t"], 1e-9)
        row = {"t": now}
        for key, pool in (("auth", self.auth), ("llm", self.llm), ("sbx", self.sbx)):
            prev_busy, prev_cap = self._last[key]
            row[f"util_{key}"] = (pool._busy_area - prev_busy) / max(pool._cap_area - prev_cap, 1e-9)
            row[f"queue_{key}"] = len(pool.queue)
            self._last[key] = (pool._busy_area, pool._cap_area)
        row.update(in_system=self.in_system, abandoned=self.abandoned, completed=self.n_completed, arrived=self.n_arrived)
        self._last["t"] = now
        self.series.append(row)
        if len(self.series) > 4000:
            self.series = self.series[::2]
        self.sch.at(now + 60.0, SAMPLE)

    # ---- live changes (the admin page can scale resources and switch E1 while the simulation runs)
    LIVE_FIELDS = {"user_arrival_rate": float, "auth_workers": int, "llm_slots": int, "sandbox_workers": int, "budgeted_context": bool,
                   "patience_seconds": float, "sandbox_patience": float, "login_success_prob": float}

    def apply(self, changes: dict) -> dict:
        """Change parameters mid-run. Added capacity serves the people waiting at once; removed capacity retires units as they finish."""
        done = {}
        for k, caster in self.LIVE_FIELDS.items():
            if k in changes and changes[k] is not None:
                done[k] = caster(changes[k])
        trial = SimParams.from_dict({**self.p.to_dict(), **done})   # validates the whole set
        for k in done:
            setattr(self.p, k, getattr(trial, k))
        now = self.sch.now
        for key, pool, start in (("auth_workers", self.auth, None), ("llm_slots", self.llm, self._llm_start), ("sandbox_workers", self.sbx, self._sbx_start)):
            if key in done:
                pool._tick(now)
                pool.capacity = getattr(self.p, key)
                while pool.queue and pool.spare():
                    nxt = pool.queue.popleft()
                    pool.busy += 1
                    nxt.waiting = None
                    if pool is self.auth:
                        self.sch.after(self._tri("login_auth"), AUTH_DONE, nxt)
                    else:
                        start(nxt, now - nxt.t_q)
        return done

    # ---- running
    @property
    def abandoned(self) -> int:
        return self.n_abandon_llm + self.n_abandon_sbx

    def run_until(self, t: float) -> None:
        handlers = self._handlers
        for kind, payload in self.sch.pop_until(t):
            handlers[kind](payload)

    def run(self) -> dict:
        self.run_until(self.p.run_seconds)
        return self.metrics()

    def abandon_pct(self) -> float:
        total = self.n_completed + self.abandoned
        return 100.0 * self.abandoned / total if total else 0.0

    def snapshot(self) -> dict:
        """The live dashboard (paper, Figure 6): what is happening right now."""
        now = self.sch.now
        for pool in (self.auth, self.llm, self.sbx):
            pool._tick(now)
        hours = max((now - self.t_stats) / 3600.0, 1e-9)
        return {"t": now, "in_system": self.in_system, "arrived": self.n_arrived, "completed": self.n_completed, "abandoned": self.abandoned,
                "abandon_pct": self.abandon_pct(), "throughput": self.n_completed / hours, "events": self.sch.events,
                "pools": {k: {"capacity": pl.capacity, "busy": pl.busy, "queue": len(pl.queue), "utilization": min(100.0, pl.utilization(now) * 100.0)}
                          for k, pl in (("auth", self.auth), ("llm", self.llm), ("sandbox", self.sbx))},
                "avg_turn_s": self.turn_sum / self.n_turns if self.n_turns else 0.0}

    def metrics(self) -> dict:
        """M1..M11 of the paper (Section 4.3), measured after the warm-up."""
        now = self.sch.now
        hours = (now - self.t_stats) / 3600.0
        done = self.n_completed
        return {
            "M1_turn_response_s": self.turn_sum / self.n_turns if self.n_turns else 0.0,
            "M2_session_min": self.session_sum / done / 60.0 if done else 0.0,
            "M3_throughput_per_h": done / hours if hours > 0 else 0.0,
            "M4_llm_util_pct": self.llm.utilization(now) * 100.0,
            "M5_sandbox_util_pct": self.sbx.utilization(now) * 100.0,
            "M6_llm_queue_avg": self.llm.avg_queue(now),
            "M7_llm_queue_max": self.llm.max_queue,
            "M8_llm_wait_s": self.llm_wait_sum / self.llm_wait_n if self.llm_wait_n else 0.0,
            "M9_sandbox_wait_s": self.sbx_wait_sum / self.sbx_wait_n if self.sbx_wait_n else 0.0,
            "M10_abandoned": self.abandoned,
            "M11_abandon_pct": self.abandon_pct(),
            "auth_util_pct": self.auth.utilization(now) * 100.0,
            "arrived": self.n_arrived, "completed": done, "abandoned_llm": self.n_abandon_llm, "abandoned_sandbox": self.n_abandon_sbx,
            "turns": self.n_turns, "logins": self.n_logins, "login_retries": self.n_login_retries,
            "gradings": self.n_gradings, "resubmissions": self.n_resubmissions, "in_system_end": self.in_system,
            "events": self.sch.events, "hours_measured": hours,
        }


def run_params(d: dict) -> dict:
    """One replication from a plain dict (used by the process pool): parameters in, metrics out."""
    p = SimParams.from_dict(d)
    m = Simulation(p).run()
    m["seed"] = p.seed
    return m
