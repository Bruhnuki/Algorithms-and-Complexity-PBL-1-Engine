"""FastAPI app: auth, runs, commands, instructor read, static front end. The server owns the rules."""
from __future__ import annotations

import hashlib
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Body, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from ..gateway import context as gctx
from ..gateway.gateway import Gateway
from ..rules import content as content_mod, reducer
from ..rules.reducer import GameError
from ..store import db as M

WEB = Path(__file__).resolve().parents[1] / "web"
HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, type=__import__("argon2").Type.ID)
DUMMY_HASH = HASHER.hash("dummy-password-for-timing")
CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"


class ApiError(Exception):
    def __init__(self, status: int, code: str, detail: str = ""):
        self.status, self.code, self.detail = status, code, detail


def problem(status: int, code: str, detail: str = "") -> JSONResponse:
    return JSONResponse({"type": f"about:blank#{code}", "title": code.replace("_", " ").title(), "status": status,
                         "code": code, "detail": detail}, status_code=status, media_type="application/problem+json")


class Settings:
    def __init__(self, **kw):
        self.idle_seconds = kw.get("idle_seconds", 30 * 60)
        self.absolute_seconds = kw.get("absolute_seconds", 8 * 3600)
        self.login_per_minute = kw.get("login_per_minute", 5)
        self.instructor_code = kw.get("instructor_code", os.environ.get("INSTRUCTOR_CODE", ""))
        self.secret = kw.get("secret", os.environ.get("SESSION_SECRET", "dev-secret-change-me"))
        self.min_password = 10
        self.dialogue_inline = kw.get("dialogue_inline", False)


# ---------------------------------------------------------------- request models
class RegisterIn(BaseModel):
    email: str = Field(max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(max_length=200)
    display_name: str = Field(min_length=1, max_length=80)
    role: str = Field(default="student", pattern="^(student|instructor)$")
    cohort_code: str | None = Field(default=None, max_length=24)
    instructor_code: str | None = Field(default=None, max_length=100)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


class CommandIn(BaseModel):
    client_seq: int = Field(ge=0)
    type: str = Field(max_length=40)
    payload: dict = Field(default_factory=dict)


class NewRunIn(BaseModel):
    """Experimental branch: Heat modifiers, and the practice sprint used by the tutorial."""
    tutorial: bool = False
    heat: list[str] = Field(default_factory=list, max_length=10)


class TickIn(BaseModel):
    real_ms: int = Field(ge=0, le=10 ** 9)


def public_event(e: dict) -> dict:
    """Events as the student sees them: a shipped bug or hole is not revealed until Review."""
    if e["type"] == "pushed" and e["result"] in ("buggy", "security_hole"):
        return {**e, "result": "pending", "label": "Pushed"}
    return e


def create_app(db_path: str, content=None, gateway: Gateway | None = None, settings: Settings | None = None,
               now=time.time, seed_fn=None) -> FastAPI:
    seed_fn = seed_fn or (lambda: secrets.randbelow(2 ** 31))
    content = content or content_mod.get()
    st = settings or Settings()
    engine = M.make_engine(db_path)
    app = FastAPI(title="Fix it with Scrum", version="1.0.0")
    app.state.engine, app.state.gateway, app.state.settings = engine, gateway, st
    cache: dict[int, dict] = {}
    run_locks: dict[int, threading.Lock] = defaultdict(threading.Lock)
    attempts: dict[str, deque] = defaultdict(deque)
    counters: dict[int, int] = defaultdict(int)

    def sha(x: str) -> str:
        return hashlib.sha256(x.encode()).hexdigest()

    def iphash(request: Request) -> str:
        return sha(st.secret + (request.client.host if request.client else "?"))[:32]

    def auth_event(db, uid, kind, request):
        db.add(M.AuthEvent(user_id=uid, kind=kind, ip_hash=iphash(request), created_at=now()))

    def db_dep():
        with DbSession(engine) as db:
            yield db

    # ------------------------------------------------------------ errors and headers
    @app.exception_handler(ApiError)
    async def _api_error(_, e: ApiError):
        return problem(e.status, e.code, e.detail)

    @app.exception_handler(GameError)
    async def _game_error(_, e: GameError):
        return problem(409, e.code, e.detail)

    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def _validation(_, e):
        return problem(422, "VALIDATION_ERROR", "invalid request body")

    @app.middleware("http")
    async def headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["Content-Security-Policy"] = CSP
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Cache-Control"] = "no-store"
        return resp

    # ------------------------------------------------------------ auth dependencies
    def current(request: Request, db: DbSession = Depends(db_dep)):
        token = request.cookies.get("sid")
        if not token:
            raise ApiError(401, "UNAUTHENTICATED", "log in first")
        row = db.get(M.Session, sha(token))
        t = now()
        if not row or t > row.expires_at or t - row.last_seen_at > st.idle_seconds:
            if row:
                db.delete(row)
                db.commit()
            raise ApiError(401, "UNAUTHENTICATED", "session expired")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            hdr = request.headers.get("x-csrf-token", "")
            if not hdr or sha(hdr) != row.csrf_hash:
                raise ApiError(403, "CSRF_FAILED", "missing or wrong CSRF header")
        user = db.get(M.User, row.user_id)
        if t - row.last_seen_at > 60:  # touch at most once a minute: a write per request would serialise all players
            row.last_seen_at = t
            db.commit()
        return user

    def instructor(user=Depends(current)):
        if user.role != "instructor":
            raise ApiError(403, "FORBIDDEN", "instructors only")
        return user

    # ------------------------------------------------------------ auth routes
    @app.post("/api/v1/auth/register", status_code=201)
    def register(body: RegisterIn, request: Request, db: DbSession = Depends(db_dep)):
        key = "reg:" + iphash(request)
        _rate(attempts, key, 10, now())
        if len(body.password) < st.min_password:
            raise ApiError(422, "VALIDATION_ERROR", f"password must be at least {st.min_password} characters")
        email = body.email.strip().lower()
        cohort_id = None
        if body.role == "instructor":
            if not st.instructor_code or body.instructor_code != st.instructor_code:
                raise ApiError(403, "FORBIDDEN", "instructor sign-up needs the instructor code")
        elif body.cohort_code:
            c = db.scalar(select(M.Cohort).where(M.Cohort.join_code == body.cohort_code))
            if not c:
                raise ApiError(422, "VALIDATION_ERROR", "unknown cohort code")
            cohort_id = c.id
        user = M.User(email=email, display_name=body.display_name, password_hash=HASHER.hash(body.password),
                      role=body.role, cohort_id=cohort_id)
        db.add(user)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise ApiError(409, "EMAIL_TAKEN", "could not register with that email") from None
        out = {"id": user.id, "role": user.role}
        if body.role == "instructor":
            c = M.Cohort(name=f"{body.display_name}'s cohort", join_code=secrets.token_urlsafe(8)[:10], instructor_id=user.id)
            db.add(c)
            db.flush()
            user.cohort_id = c.id
            out.update(cohort_id=c.id, join_code=c.join_code)
        auth_event(db, user.id, "register", request)
        db.commit()
        return out

    @app.post("/api/v1/auth/login")
    def login(body: LoginIn, request: Request, db: DbSession = Depends(db_dep)):
        email = body.email.strip().lower()
        t = now()
        try:
            _rate(attempts, "acct:" + sha(email), st.login_per_minute, t)
            _rate(attempts, "ip:" + iphash(request), st.login_per_minute, t)
        except ApiError:
            auth_event(db, None, "locked_out", request)
            db.commit()
            raise
        user = db.scalar(select(M.User).where(M.User.email == email))
        try:
            HASHER.verify(user.password_hash if user else DUMMY_HASH, body.password)
            ok = user is not None
        except VerifyMismatchError:
            ok = False
        if not ok:
            auth_event(db, user.id if user else None, "login_fail", request)
            db.commit()
            raise ApiError(401, "INVALID_CREDENTIALS", "Email or password is incorrect")
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        db.add(M.Session(id_hash=sha(token), user_id=user.id, csrf_hash=sha(csrf), created_at=t, last_seen_at=t,
                         expires_at=t + st.absolute_seconds))
        auth_event(db, user.id, "login_ok", request)
        db.commit()
        resp = JSONResponse({"id": user.id, "role": user.role, "display_name": user.display_name, "csrf": csrf})
        resp.set_cookie("sid", token, httponly=True, secure=True, samesite="lax", max_age=st.absolute_seconds, path="/")
        return resp

    @app.post("/api/v1/auth/logout")
    def logout(request: Request, user=Depends(current), db: DbSession = Depends(db_dep)):
        row = db.get(M.Session, sha(request.cookies["sid"]))
        if row:
            db.delete(row)
            db.commit()
        resp = JSONResponse({"ok": True})
        resp.delete_cookie("sid", path="/")
        return resp

    @app.get("/api/v1/me")
    def me(user=Depends(current)):
        return {"id": user.id, "email": user.email, "display_name": user.display_name, "role": user.role,
                "cohort_id": user.cohort_id, "consented": user.consent_at is not None}

    @app.post("/api/v1/consent")
    def consent(user=Depends(current), db: DbSession = Depends(db_dep)):
        u = db.get(M.User, user.id)
        u.consent_at = u.consent_at or now()
        db.commit()
        return {"consented": True}

    # ------------------------------------------------------------ run helpers
    def load_run(db, run_id: int, user) -> M.Run:
        run = db.get(M.Run, run_id)
        if not run:
            raise ApiError(404, "NOT_FOUND", "no such run")
        if run.user_id != user.id:
            raise ApiError(403, "FORBIDDEN", "not your run")
        return run

    def replay(db, run: M.Run) -> dict:
        s, _ = reducer.start_run(run.seed, content)
        rows = db.scalars(select(M.RunEvent).where(M.RunEvent.run_id == run.id, M.RunEvent.type == "cmd")
                          .order_by(M.RunEvent.seq)).all()
        for r in rows:
            s, _ = reducer.apply(s, r.payload["command"], content)
        return {"state": s, "seq": db.scalar(select(func.coalesce(func.max(M.RunEvent.seq), 0)).where(M.RunEvent.run_id == run.id))}

    def get_cached(db, run: M.Run) -> dict:
        if run.id not in cache:
            cache[run.id] = replay(db, run)
        return cache[run.id]

    def append(db, run_id: int, seq: int, rows: list[tuple]) -> int:
        for typ, t, payload, cseq in rows:
            seq += 1
            db.add(M.RunEvent(run_id=run_id, seq=seq, game_time=t, type=typ, payload=payload, client_seq=cseq))
        return seq

    def dialogue(run_id: int, user_id: int, seq: int, state: dict, events: list[dict]):
        gw = app.state.gateway
        if gw is None or not events:
            return
        reqs = gctx.requests_for(events, state, content, f"u{user_id}", counters[run_id])
        counters[run_id] += len(reqs)
        if not reqs:
            return

        def work():
            for rq in reqs:
                line = gw.generate(rq)
                with DbSession(engine) as d2:
                    d2.add(M.TranscriptLine(run_id=run_id, seq=seq, speaker=rq.teammate_id, text=line.text, source=line.source,
                                            latency_ms=line.latency_ms, tone=line.tone, model=line.model,
                                            prompt_tokens=line.prompt_tokens))
                    d2.commit()
        if st.dialogue_inline:
            work()
        else:
            threading.Thread(target=work, daemon=True).start()

    def execute(db, run: M.Run, command: dict, client_seq: int | None) -> dict:
        with run_locks[run.id]:
            c = get_cached(db, run)
            try:
                state2, events = reducer.apply(c["state"], command, content)
            except GameError:
                cache.pop(run.id, None)
                raise
            rows = [("cmd", state2["clock_s"], {"command": command, "response": {"events": len(events)}}, client_seq)]
            rows += [(e["type"], e["t"], e, None) for e in events]
            try:
                seq = append(db, run.id, c["seq"], rows)
                if state2["status"] != "active":
                    run.status, run.ending = state2["status"], state2["ending"]
                db.commit()
            except Exception:
                db.rollback()
                cache.pop(run.id, None)
                raise
            c["state"], c["seq"] = state2, seq
        dialogue(run.id, run.user_id, seq, state2, events)
        return {"seq": seq, "events": [public_event(e) for e in events], "state": reducer.public_state(state2, content)}

    # ------------------------------------------------------------ run routes
    def meta_unlocks(db, user) -> list[str]:
        """M16: practices and Heat unlocked by achievements in the student's earlier runs."""
        got: set[str] = set()
        for r in db.scalars(select(M.Run).where(M.Run.user_id == user.id, M.Run.status == "ended")).all():
            x = get_cached(db, r)["state"].get("x") or {}
            got.update(x.get("achievements", []))
        rules = content.balance["experimental"].get("meta_unlocks", {})
        return sorted({u for a in got for u in rules.get(a, [])})

    @app.post("/api/v1/runs", status_code=201)
    def create_run(body: NewRunIn | None = Body(default=None), user=Depends(current), db: DbSession = Depends(db_dep)):
        if user.role != "student":
            raise ApiError(403, "FORBIDDEN", "only students play")
        if user.consent_at is None:
            raise ApiError(403, "CONSENT_REQUIRED", "accept the consent screen before playing")
        body = body or NewRunIn()
        exp = reducer._exp(content)
        seed = seed_fn()
        run = M.Run(user_id=user.id, seed=seed, content_version=content.version,
                    balance_version=content.balance["version"])
        db.add(run)
        db.flush()
        s, events = reducer.start_run(run.seed, content)
        seq = append(db, run.id, 0, [(e["type"], e["t"], e, None) for e in events])
        if exp:   # stored as the run's first command, so replay rebuilds the same run
            cfg = {"type": "configure", "payload": {"unlocks": meta_unlocks(db, user), "heat": body.heat, "tutorial": body.tutorial}}
            s, ev2 = reducer.apply(s, cfg, content)
            seq = append(db, run.id, seq, [("cmd", 0.0, {"command": cfg, "response": {"events": len(ev2)}}, None)]
                         + [(e["type"], e["t"], e, None) for e in ev2])
            events += ev2
        db.commit()
        cache[run.id] = {"state": s, "seq": seq}
        dialogue(run.id, user.id, seq, s, events)
        return {"id": run.id, "seq": seq, "state": reducer.public_state(s, content)}

    @app.get("/api/v1/me/unlocks")
    def my_unlocks(user=Depends(current), db: DbSession = Depends(db_dep)):
        if not reducer._exp(content):
            return {"unlocks": [], "heat": []}
        u = meta_unlocks(db, user)
        return {"unlocks": u, "heat": sorted(content.balance["experimental"]["heat"]["modifiers"]) if "heat" in u else []}

    @app.get("/api/v1/runs/{run_id}/state")
    def get_state(run_id: int, since: int = 0, since_line: int = 0, user=Depends(current), db: DbSession = Depends(db_dep)):
        run = load_run(db, run_id, user)
        c = get_cached(db, run)
        evs = db.scalars(select(M.RunEvent).where(M.RunEvent.run_id == run.id, M.RunEvent.seq > since,
                                                  M.RunEvent.type != "cmd").order_by(M.RunEvent.seq)).all()
        lines = db.scalars(select(M.TranscriptLine).where(M.TranscriptLine.run_id == run.id, M.TranscriptLine.id > since_line)
                           .order_by(M.TranscriptLine.id)).all()
        return {"seq": c["seq"], "state": reducer.public_state(c["state"], content),
                "events": [{"seq": e.seq, **public_event(e.payload)} for e in evs],
                "lines": [{"id": ln.id, "seq": ln.seq, "speaker": ln.speaker, "text": ln.text, "tone": ln.tone} for ln in lines]}

    @app.post("/api/v1/runs/{run_id}/commands")
    def post_command(run_id: int, body: CommandIn, user=Depends(current), db: DbSession = Depends(db_dep)):
        run = load_run(db, run_id, user)
        if body.type in reducer.SERVER_ONLY:
            raise ApiError(403, "FORBIDDEN", "this command is issued by the server")
        command = {"type": body.type, "payload": body.payload}
        prior = db.scalar(select(M.RunEvent).where(M.RunEvent.run_id == run.id, M.RunEvent.client_seq == body.client_seq))
        if prior is not None:
            if prior.payload["command"] != command:
                raise ApiError(409, "DUPLICATE_SEQ_MISMATCH", "client_seq was already used for a different command")
            c = get_cached(db, run)
            evs = db.scalars(select(M.RunEvent).where(M.RunEvent.run_id == run.id, M.RunEvent.seq > prior.seq,
                                                      M.RunEvent.type != "cmd").order_by(M.RunEvent.seq)).all()
            nxt = db.scalar(select(func.min(M.RunEvent.seq)).where(M.RunEvent.run_id == run.id, M.RunEvent.seq > prior.seq,
                                                                   M.RunEvent.type == "cmd"))
            evs = [e for e in evs if nxt is None or e.seq < nxt]
            return {"seq": c["seq"], "events": [public_event(e.payload) for e in evs], "state": reducer.public_state(c["state"], content),
                    "replayed": True}
        return execute(db, run, command, body.client_seq)

    @app.post("/api/v1/runs/{run_id}/tick")
    def post_tick(run_id: int, body: TickIn, user=Depends(current), db: DbSession = Depends(db_dep)):
        run = load_run(db, run_id, user)
        if run.status != "active":
            return {"seq": get_cached(db, run)["seq"], "events": [], "state": reducer.public_state(get_cached(db, run)["state"], content)}
        return execute(db, run, {"type": "tick", "payload": {"real_ms": body.real_ms}}, None)

    @app.get("/api/v1/runs/{run_id}/debrief")
    def get_debrief(run_id: int, user=Depends(current), db: DbSession = Depends(db_dep)):
        run = load_run(db, run_id, user)
        s = get_cached(db, run)["state"]
        if s["status"] != "ended":
            raise ApiError(409, "RUN_ACTIVE", "the run has not ended")
        return reducer.debrief(s, content)

    # ------------------------------------------------------------ instructor
    def cohort_students(db, cohort_id):
        return db.scalars(select(M.User).where(M.User.cohort_id == cohort_id, M.User.role == "student")).all()

    @app.get("/api/v1/instructor/cohorts/{cohort_id}/runs")
    def cohort_runs(cohort_id: int, user=Depends(instructor), db: DbSession = Depends(db_dep)):
        co = db.get(M.Cohort, cohort_id)
        if not co or co.instructor_id != user.id:
            raise ApiError(403, "FORBIDDEN", "not your cohort")
        out = []
        for stu in cohort_students(db, cohort_id):
            runs = db.scalars(select(M.Run).where(M.Run.user_id == stu.id).order_by(M.Run.id)).all()
            for r in runs:
                s = get_cached(db, r)["state"]
                if (s.get("x") or {}).get("tutorial"):
                    continue   # the practice sprint is not a real run
                out.append({"run_id": r.id, "student": stu.display_name, "status": r.status, "ending": r.ending,
                            "process_score": reducer.process_score(s, content), "meters": s["meters"]})
        return {"cohort_id": cohort_id, "runs": out}

    @app.get("/api/v1/instructor/runs/{run_id}/transcript")
    def transcript(run_id: int, user=Depends(instructor), db: DbSession = Depends(db_dep)):
        run = db.get(M.Run, run_id)
        stu = db.get(M.User, run.user_id) if run else None
        co = db.get(M.Cohort, stu.cohort_id) if stu and stu.cohort_id else None
        if not run or not co or co.instructor_id != user.id:
            raise ApiError(403, "FORBIDDEN", "not your cohort")
        evs = db.scalars(select(M.RunEvent).where(M.RunEvent.run_id == run_id, M.RunEvent.type != "cmd").order_by(M.RunEvent.seq)).all()
        lines = db.scalars(select(M.TranscriptLine).where(M.TranscriptLine.run_id == run_id).order_by(M.TranscriptLine.id)).all()
        return {"run_id": run_id, "student": stu.display_name,
                "events": [{"seq": e.seq, **e.payload} for e in evs],
                "lines": [{"seq": ln.seq, "speaker": ln.speaker, "text": ln.text, "source": ln.source,
                           "latency_ms": ln.latency_ms, "model": ln.model, "prompt_tokens": ln.prompt_tokens} for ln in lines]}

    # ------------------------------------------------------------ ops
    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/api/v1/model/status")
    def model_status(user=Depends(current)):
        gw = app.state.gateway
        return gw.status() if gw else {"enabled": False, "queue_depth": 0, "last_latency_ms": None, "model": None}

    if WEB.exists():
        app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
    return app


def _rate(store: dict, key: str, limit: int, t: float) -> None:
    q = store[key]
    while q and t - q[0] > 60:
        q.popleft()
    if len(q) >= limit:
        raise ApiError(429, "LOCKED_OUT", "too many attempts; wait a minute")
    q.append(t)


def app_from_env() -> FastAPI:
    """uvicorn fixit.api.app:app_from_env --factory"""
    from ..gateway.gateway import HttpModelClient
    url = os.environ.get("MODEL_URL")
    gw = Gateway(content_mod.get(), HttpModelClient(url, os.environ.get("MODEL_NAME", "model")) if url else None,
                 slots=int(os.environ.get("MODEL_SLOTS", "4")))
    return create_app(os.environ.get("DB_PATH", "fixit.db"), gateway=gw)
