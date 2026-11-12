"""FastAPI app: auth, runs, commands, instructor read, static front end. The server owns the rules."""
from __future__ import annotations

import hashlib
import ipaddress
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
from ..gateway import drama
from ..gateway.chat import PLAIN, TAKE_AT, Chat, addressed, item_asked
from ..gateway.gateway import Gateway
from ..rules import content as content_mod, reducer
from ..rules.reducer import GameError
from ..store import db as M

TAILNET = ipaddress.ip_network("100.64.0.0/10")
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
        self.debug = kw.get("debug", os.environ.get("FIXIT_DEBUG") == "1")   # developer shortcuts; never on in a class


COMPLAINTS = {   # {what dropped: {level: {teammate: line}}}
    "morale": {35: {"dev1": "Honestly? I'm running out of motivation. Can we talk about how this Sprint is going?",
                    "dev2": "Sorry, I just feel like nothing I do is good enough lately. Could we talk?",
                    "po": "The mood on this team is dropping and it's showing in the work. I need us to talk."},
               20: {"dev1": "I'm close to checking out. If nobody backs us up, I'm done.",
                    "dev2": "I can't do this anymore... I really can't. Please, say something encouraging.",
                    "po": "This is a crisis. The team has lost faith and I can't cover for it. Say something, now."}},
    "sanity": {35: {"dev1": "I'm frayed. Every message lately feels like another hit. Please ease off.",
                    "dev2": "I'm shaking a bit, sorry. I can't think straight when it's like this.",
                    "po": "Tempers are short and nobody's thinking clearly. Let's reset."},
               20: {"dev1": "I can't think. Everything's noise. I need this to stop.",
                    "dev2": "I'm panicking, I can't focus on anything. Please, please be kind.",
                    "po": "We are one bad message from falling apart. Calm down and talk to us properly."}}}


IDLE_LINES = {   # a teammate you leave without work says so, each in their own voice
    "dev1": ["Not that I'm complaining, but I haven't touched a ticket in a while. Am I on this team or just decoration?",
             "You keep doing it all yourself. Fine. I'll just sit here being unproductive.",
             "I'm not doing a good enough job here, am I? Or you'd hand me something."],
    "dev2": ["Um, sorry, I feel like I'm not contributing at all. Did I do something wrong?",
             "I'm so useless to the team right now... you do everything. Maybe you don't trust me?",
             "I feel like I'm not doing a good enough job. Please, can I take something? Anything?"]}
PEER_LINES = {
    "peer_support": {("dev1", "dev2"): "Hey Tobi, you okay? You've been quiet. Tell me what's stuck and I'll look at it with you.",
                     ("dev2", "dev1"): "Ines, I know you're pretending it's fine, but you're doing really well. Want to talk it through?"},
    "peer_drag": {("dev1", "dev2"): "Tobi, I'm done with this. Honestly, nothing we do seems to matter. Don't look at me like that.",
                  ("dev2", "dev1"): "Ines... I just can't do this anymore. Everything we try goes wrong. I'm sorry, I'm sorry."}}


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
    project: int = Field(default=1, ge=1, le=3)   # 2 and 3 are the AI-written projects; they unlock after the project before them


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)


class TickIn(BaseModel):
    real_ms: int = Field(ge=0, le=10 ** 9)


def public_event(e: dict) -> dict:
    """Events as the student sees them: a shipped bug or hole is not revealed until Review."""
    if e["type"] == "pushed" and e["result"] in ("buggy", "security_hole"):
        return {**e, "result": "pending", "label": "Pushed"}
    return e


def create_app(db_path: str, content=None, gateway: Gateway | None = None, settings: Settings | None = None,
               now=time.time, seed_fn=None, library=None, ai=None, runsets=None, projects=None) -> FastAPI:
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
        host = request.url.hostname or ""
        try:
            local = host == "localhost" or ipaddress.ip_address(host).is_loopback or ipaddress.ip_address(host) in TAILNET   # loopback, or Tailscale's encrypted tunnel
        except ValueError:
            local = host.endswith(".ts.net")   # a MagicDNS name: same tunnel, and Tailscale HTTPS is served on it
        # a Secure cookie is not sent back over plain http, so on loopback and the tailnet it is left off; any other plain-http host still gets Secure
        resp.set_cookie("sid", token, httponly=True, secure=request.url.scheme == "https" or not local, samesite="lax", max_age=st.absolute_seconds, path="/")
        return resp

    @app.get("/api/v1/auth/csrf")
    def fresh_csrf(request: Request, user=Depends(current), db: DbSession = Depends(db_dep)):
        """After a page refresh the browser still holds the session cookie but has lost the CSRF token: issue a new one for this session."""
        row = db.get(M.Session, sha(request.cookies["sid"]))
        csrf = secrets.token_urlsafe(24)
        row.csrf_hash = sha(csrf)
        db.commit()
        resp = JSONResponse({"csrf": csrf})
        resp.headers["Cache-Control"] = "no-store"
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
                "cohort_id": user.cohort_id, "consented": user.consent_at is not None, "debug": st.debug}

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

    def pub(run_id: int, state: dict) -> dict:
        """The player's view of the state, plus how the AI is doing on this run's new problems (the roadmap shows it)."""
        out = reducer.public_state(state, content)
        if runsets is not None and (a := runsets.status(run_id)):
            out["ai"] = a
        return out

    def argue(run_id: int, seq: int, events: list[dict], state: dict):
        """The team's arguments: each conflict event becomes lines in the chat, written by the AI in the speaker's voice (authored lines if it is off)."""
        wanted = [e for e in events if e["type"] in ("conflict_started", "conflict_round", "conflict_break", "conflict_resolved", "conflict_unmoved", "conflict_dismissed")]
        if not wanted:
            return

        def work():
            with DbSession(engine) as d2:
                last = d2.scalars(select(M.TranscriptLine).where(M.TranscriptLine.run_id == run_id).order_by(M.TranscriptLine.id.desc()).limit(8)).all()
                history = [f"{PLAIN.get(l.speaker, 'Scrum Master (the player)')}: {l.text}" for l in reversed(last)]
                out = []
                for e in wanted:
                    t = e["type"]
                    mood = state["x"]["mood"]
                    if t in ("conflict_started", "conflict_round"):
                        a, b = e["a"], e["b"]
                        speaker = e["speaker"] if t == "conflict_round" else a
                        rounds = [(speaker, e.get("round", 0))] + ([(b, 1)] if t == "conflict_started" else [])
                        for who, rnd in rounds:
                            other = b if who == a else a
                            about = next(x[2] for pr, tps in reducer.TOPICS.items() for x in tps if x[0] == e["topic"])
                            facts = {"morale": mood[who]["morale"], "sanity": mood[who]["sanity"]}
                            ln = drama.line(content, ai, chat.model, who, other, e["topic"], about, rnd, facts, history)
                            out.append((who, ln["text"], "heated", ln["source"]))
                            history.append(f"{PLAIN[who]}: {ln['text']}")
                    elif t == "conflict_break":
                        out.append((e["dev"], drama.BREAK[e["dev"]], "heated", "fallback"))
                    elif t == "conflict_resolved":
                        if e["how"] == "sided":
                            out.append((e["b"], drama.SIDED_LOSER, "pushy", "fallback"))
                            out.append((e["a"], drama.RESOLVED["sided"][e["a"]], "calm", "fallback"))
                        else:
                            out += [(e["a"], drama.RESOLVED[e["how"]][e["a"]], "calm", "fallback"), (e["b"], drama.RESOLVED[e["how"]][e["b"]], "calm", "fallback")]
                    elif t == "conflict_unmoved":
                        out.append((min((e["a"], e["b"]), key=lambda x: mood[x]["morale"]), drama.UNMOVED[min((e["a"], e["b"]), key=lambda x: mood[x]["morale"])], "heated", "fallback"))
                    elif t == "conflict_dismissed":
                        out.append((e["a"], drama.DISMISSED[e["a"]], "heated", "fallback"))
                for who, text, tone, src in out:
                    d2.add(M.TranscriptLine(run_id=run_id, seq=seq, speaker=who, text=text, source=src, latency_ms=0, tone=tone))
                d2.commit()
        if st.dialogue_inline:
            work()
        else:
            threading.Thread(target=work, daemon=True, name=f"argue-{run_id}").start()

    def speak_up(run_id: int, seq: int, events: list[dict]):
        """A teammate whose morale or sanity just dropped under a warning level says so in the chat (authored lines: it must not depend on the AI)."""
        lines = []
        for e in events:
            if e["type"] == "mood_low":
                lines.append((e["dev"], COMPLAINTS[e["what"]][e["level"]][e["dev"]], "panicked"))
            elif e["type"] == "feels_idle":
                pool = IDLE_LINES[e["dev"]]
                lines.append((e["dev"], pool[(e["n"] // 2) % len(pool)], "panicked" if e["dev"] == "dev2" else "pushy"))
            elif e["type"] in ("peer_support", "peer_drag"):
                lines.append((e["dev"], PEER_LINES[e["type"]][(e["dev"], e["to"])], "calm" if e["type"] == "peer_support" else "pushy"))
        if lines:
            with DbSession(engine) as d2:
                for who, text, tone in lines:
                    d2.add(M.TranscriptLine(run_id=run_id, seq=seq, speaker=who, text=text, source="fallback", latency_ms=0, tone=tone))
                d2.commit()

    def execute(db, run: M.Run, command: dict, client_seq: int | None) -> dict:
        with run_locks[run.id]:
            c = get_cached(db, run)
            base, pre, taken = c["state"], [], []
            if runsets is not None and command["type"] != "ai_set":
                taken = runsets.take_pending(run.id)   # problems the AI finished for this run: stored as a command, then used by later Sprints
                if taken:
                    acmd = {"type": "ai_set", "payload": {"ids": taken}}
                    base, aev = reducer.apply(base, acmd, content)
                    pre = [("cmd", base["clock_s"], {"command": acmd, "response": {"events": len(aev)}}, None)]
            try:
                state2, events = reducer.apply(base, command, content)
            except GameError:
                cache.pop(run.id, None)
                if taken:
                    runsets.put_back(run.id, taken)
                raise
            rows = pre + [("cmd", state2["clock_s"], {"command": command, "response": {"events": len(events)}}, client_seq)]
            rows += [(e["type"], e["t"], e, None) for e in events]
            try:
                seq = append(db, run.id, c["seq"], rows)
                if state2["status"] != "active":
                    run.status, run.ending = state2["status"], state2["ending"]
                db.commit()
            except Exception:
                db.rollback()
                cache.pop(run.id, None)
                if taken:
                    runsets.put_back(run.id, taken)
                raise
            c["state"], c["seq"] = state2, seq
        dialogue(run.id, run.user_id, seq, state2, events)
        speak_up(run.id, seq, events)
        argue(run.id, seq, events, state2)
        return {"seq": seq, "events": [public_event(e) for e in events], "state": pub(run.id, state2)}

    # ------------------------------------------------------------ run routes
    def meta_unlocks(db, user) -> list[str]:
        """M16: practices and Heat unlocked by achievements in the student's earlier runs."""
        got: set[str] = set()
        for r in db.scalars(select(M.Run).where(M.Run.user_id == user.id, M.Run.status == "ended")).all():
            try:
                x = get_cached(db, r)["state"].get("x") or {}
            except GameError:
                continue
            got.update(x.get("achievements", []))
        rules = content.balance["experimental"].get("meta_unlocks", {})
        return sorted({u for a in got for u in rules.get(a, [])})

    LEVELS = {1: "Easy", 2: "Medium", 3: "Hard"}

    def project_facts(db, user) -> tuple[set[int], set[str]]:
        """Which projects this player has finished (any ending), and which AI-written projects they have already played."""
        done, played = set(), set()
        for r in db.scalars(select(M.Run).where(M.Run.user_id == user.id)).all():
            try:
                x = get_cached(db, r)["state"].get("x") or {}
            except GameError:   # an old run the current rules can no longer replay: it just does not count
                continue
            if x.get("tutorial"):
                continue
            if x.get("pack"):
                played.add(x["pack"])
            if r.status == "ended":
                done.add(x.get("project_n", 1))
        return done, played

    def project_pack(user, n: int, played: set[str]) -> str | None:
        """The player's own project if the AI has finished it, else a ready-made one from the library that they have not played."""
        own = projects.status(user.id, n) if projects is not None else None
        if own and own["status"] == "ready":
            return own["pack"]   # the player's own project can be played again; only library projects are never dealt twice
        if own and own["status"] == "building" and user.id in projects.excluded:
            return None   # after a debug reset the player waits for their own new project (so its writing can be watched), not for a library one
        if library:
            library.merge_into(content)
        skip = played | (projects.excluded.get(user.id, set()) if projects is not None else set())
        spare = sorted(pid for pid, g in content.packs.items() if g["project_n"] == n and pid not in skip)
        if spare:
            return spare[0]
        again = sorted(pid for pid in played if pid in content.packs and content.packs[pid]["project_n"] == n)
        return again[-1] if again else None   # nothing new to offer: let them play one they have played before

    def project_list(db, user) -> list[dict]:
        done, played = project_facts(db, user)
        themes = lambda g: [g["sprints"][k]["theme"] for k in sorted(g.get("sprints", {}))]   # noqa: E731
        out = [{"n": 1, "level": LEVELS[1], "status": "open", "title": "The Checkout Fix", "themes": themes(content.guide), "ai": None}]
        for n in (2, 3):
            unlocked = (n - 1) in done or st.debug
            own = projects.status(user.id, n) if projects is not None else None
            pack = project_pack(user, n, played)
            title = content.packs[pack]["premise"]["title"] if pack else None
            if not unlocked:
                status = "locked"
            else:
                status = "open" if pack else ("building" if own and own["status"] == "building" else "waiting")
            out.append({"n": n, "level": LEVELS[n], "status": status, "title": title, "themes": themes(content.packs[pack]) if pack else [],
                        "ai": ({"status": own["status"], "made": own["made"], "target": own["target"], "stage": own["stage"]} if own else None)})
        return out

    @app.get("/api/v1/me/projects")
    def my_projects(user=Depends(current), db: DbSession = Depends(db_dep)):
        """Project 1 is always open; Projects 2 and 3 open after the one before is finished, and play once the AI has written them."""
        return {"projects": project_list(db, user), "ai": projects is not None}

    @app.post("/api/v1/debug/projects/reset")
    def reset_projects(user=Depends(current)):
        """Developer shortcut (FIXIT_DEBUG=1): start writing this player's Projects 2 and 3 again, so the progress can be watched."""
        if not st.debug:
            raise ApiError(403, "FORBIDDEN", "debug shortcuts are off (start the server with FIXIT_DEBUG=1)")
        if projects is None:
            raise ApiError(409, "AI_OFF", "the AI is not connected, so no project can be written")
        projects.reset(user.id, seed_fn())
        return {"ok": True}

    @app.post("/api/v1/runs", status_code=201)
    def create_run(body: NewRunIn | None = Body(default=None), user=Depends(current), db: DbSession = Depends(db_dep)):
        if user.role != "student":
            raise ApiError(403, "FORBIDDEN", "only students play")
        if user.consent_at is None:
            raise ApiError(403, "CONSENT_REQUIRED", "accept the consent screen before playing")
        body = body or NewRunIn()
        exp = reducer._exp(content)
        seed = seed_fn()
        project = {"n": 1, "pack": None}
        if body.project > 1 and not body.tutorial:
            done, played = project_facts(db, user)
            if (body.project - 1) not in done and not st.debug:
                raise ApiError(409, "PROJECT_LOCKED", f"finish Project {body.project - 1} first")
            pack = project_pack(user, body.project, played)
            if pack is None:
                if st.debug and projects is not None:
                    projects.enqueue(user.id, seed, levels=(body.project,))   # developer shortcut: start writing one now
                raise ApiError(409, "PROJECT_NOT_READY", "the AI is still writing this project")
            project = {"n": body.project, "pack": pack}
        run = M.Run(user_id=user.id, seed=seed, content_version=content.version,
                    balance_version=content.balance["version"])
        db.add(run)
        db.flush()
        s, events = reducer.start_run(run.seed, content)
        seq = append(db, run.id, 0, [(e["type"], e["t"], e, None) for e in events])
        if exp:   # stored as the run's first command, so replay rebuilds the same run
            if library:
                library.merge_into(content)   # pick up what the background generator added
            cfg = {"type": "configure", "payload": {"unlocks": meta_unlocks(db, user), "heat": body.heat, "tutorial": body.tutorial,
                                                    "lib": library.ids(content) if library else [], "project": project, "redeal": True}}   # frozen here so replay deals the same items
            s, ev2 = reducer.apply(s, cfg, content)
            seq = append(db, run.id, seq, [("cmd", 0.0, {"command": cfg, "response": {"events": len(ev2)}}, None)]
                         + [(e["type"], e["t"], e, None) for e in ev2])
            events += ev2
        db.commit()
        cache[run.id] = {"state": s, "seq": seq}
        if runsets is not None and exp and not body.tutorial:
            runsets.enqueue(run.id, run.seed)   # a new set of problems is written while Sprint 1 is played
        if projects is not None and exp and not body.tutorial and project["n"] == 1:
            projects.enqueue(user.id, run.seed)   # Project 2 and 3 are written for this player while they play Project 1
        dialogue(run.id, user.id, seq, s, events)
        return {"id": run.id, "seq": seq, "state": pub(run.id, s)}

    @app.get("/api/v1/ai/status")
    def ai_status(user=Depends(current)):
        """Is the AI helping right now? The game plays the same either way; this only reports it."""
        if ai is None or library is None:
            return {"enabled": False, "library": {}}
        return {"enabled": True, "circuit_open": ai.circuit_open, "last_error": ai.last_error, "last_ok": ai.last_ok, "library": library.count()}

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
        return {"seq": c["seq"], "state": pub(run.id, c["state"]),
                "events": [{"seq": e.seq, **public_event(e.payload)} for e in evs],
                "lines": [{"id": ln.id, "seq": ln.seq, "speaker": ln.speaker, "text": ln.text, "tone": ln.tone} for ln in lines]}

    @app.post("/api/v1/runs/{run_id}/commands")
    def post_command(run_id: int, body: CommandIn, user=Depends(current), db: DbSession = Depends(db_dep)):
        run = load_run(db, run_id, user)
        if body.type in reducer.SERVER_ONLY:
            raise ApiError(403, "FORBIDDEN", "this command is issued by the server")
        if body.type == "debug_skip" and not st.debug:
            raise ApiError(403, "FORBIDDEN", "debug shortcuts are off (start the server with FIXIT_DEBUG=1)")
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
            return {"seq": c["seq"], "events": [public_event(e.payload) for e in evs], "state": pub(run.id, c["state"]),
                    "replayed": True}
        return execute(db, run, command, body.client_seq)

    @app.post("/api/v1/runs/{run_id}/tick")
    def post_tick(run_id: int, body: TickIn, user=Depends(current), db: DbSession = Depends(db_dep)):
        run = load_run(db, run_id, user)
        if run.status != "active":
            return {"seq": get_cached(db, run)["seq"], "events": [], "state": pub(run.id, get_cached(db, run)["state"])}
        return execute(db, run, {"type": "tick", "payload": {"real_ms": body.real_ms}}, None)

    @app.get("/api/v1/runs/{run_id}/debrief")
    def get_debrief(run_id: int, user=Depends(current), db: DbSession = Depends(db_dep)):
        run = load_run(db, run_id, user)
        s = get_cached(db, run)["state"]
        if s["status"] != "ended":
            raise ApiError(409, "RUN_ACTIVE", "the run has not ended")
        return reducer.debrief(s, content)

    # ------------------------------------------------------------ team chat (Slackish)
    chat = Chat(content, ai)
    app.state.chat = chat

    def chat_work(run_id: int, text: str, targets: list[str]):
        """Each addressed teammate answers in turn; the game applies the tolerance change and, when asked and earned, the delegation."""
        for dev in targets:
            with DbSession(engine) as d:
                run = d.get(M.Run, run_id)
                if run.status != "active":
                    return
                s = get_cached(d, run)["state"]
                mine = d.scalars(select(M.TranscriptLine).where(M.TranscriptLine.run_id == run_id, M.TranscriptLine.speaker == "you")
                                 .order_by(M.TranscriptLine.id.desc()).limit(5)).all()
                last = d.scalars(select(M.TranscriptLine).where(M.TranscriptLine.run_id == run_id).order_by(M.TranscriptLine.id.desc()).limit(10)).all()
                history = [f"{PLAIN.get(l.speaker, 'Scrum Master (the player)')}: {l.text}" for l in reversed(last)]
                card = item_asked(text, s["pile"], content) if dev != "po" else None
                title = content.tickets[card["ticket"]]["title"] if card else None
                code = [c for c in s["pile"] if c.get("ticket") and c.get("state") in ("pile", "open")]
                mood = {**s["x"]["mood"][dev], "feeling": reducer._g_feeling(s, dev)[0]}
                facts = {"stage": s["stage"], "sprint": s["sprint"], "morale": mood["morale"], "sanity": mood["sanity"], "feeling": mood["feeling"], "open_items": [content.tickets[c["ticket"]]["title"] for c in code][:6]}
                forbidden = [o["text"] for c in code for o in content.tickets[c["ticket"]]["options"] if o["effect"] == "correct"]
                rep = chat.reply(dev, text, tolerance=s["x"]["tolerance"][dev], history=history, facts=facts, recent_player=[l.text for l in mine[1:]],
                                 item=title, forbidden=forbidden, seed=run.seed)
                try:
                    delta = chat.allowed_gain((run_id, dev), rep["delta"])
                    morale = chat.allowed_morale((run_id, dev), rep["morale"])
                    cf = s["x"].get("conflict")
                    peace = ((5 if rep["delta"] >= 2 else 3 if rep["delta"] == 1 or rep["morale"] > 0 else 0) - (6 if rep["morale"] < 0 else 0)) if cf and dev in (cf["a"], cf["b"]) else 0
                    execute(d, run, {"type": "chat_effect", "payload": {"dev": dev, "delta": delta, "morale": morale, "sanity": rep["sanity"], "msg": 1, "peace": peace}}, None)
                    if rep["intent"] == "agree_help" and card:
                        now_s = get_cached(d, run)["state"]
                        if now_s["x"]["tolerance"][dev] >= TAKE_AT:
                            try:
                                execute(d, run, {"type": "delegate", "payload": {"card_id": card["id"], "to": dev}}, None)
                            except GameError:
                                rep.update(text=f"I can't take \"{title}\" right now. Ask me again while we're working on the items.", intent="none")
                except GameError:
                    return
                d.add(M.TranscriptLine(run_id=run_id, seq=get_cached(d, run)["seq"], speaker=dev, text=rep["text"], source=rep["source"],
                                       latency_ms=rep["latency_ms"], tone=rep["tone"], model=rep.get("model")))
                d.commit()

    @app.post("/api/v1/runs/{run_id}/chat", status_code=202)
    def post_chat(run_id: int, body: ChatIn, user=Depends(current), db: DbSession = Depends(db_dep)):
        run = load_run(db, run_id, user)
        c = get_cached(db, run)
        if run.status != "active" or c["state"].get("guide") is None:
            raise ApiError(409, "CHAT_CLOSED", "the team chat is open while a run is being played")
        text = " ".join(body.text.split())
        if not text:
            raise ApiError(422, "EMPTY_MESSAGE", "write something first")
        _rate(attempts, f"chat:{run.id}", 15, now())
        line = M.TranscriptLine(run_id=run.id, seq=c["seq"], speaker="you", text=text, source="player", latency_ms=0, tone="mine")
        db.add(line)
        db.commit()
        targets = addressed(text)
        if st.dialogue_inline:
            chat_work(run.id, text, targets)
        else:
            threading.Thread(target=chat_work, args=(run.id, text, targets), daemon=True, name=f"chat-{run.id}").start()
        return {"line": {"id": line.id, "seq": line.seq, "speaker": "you", "text": text, "tone": "mine"}, "to": targets}

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
                            "process_score": reducer.process_score(s, content), "process_saturating": reducer.e2.saturating(s["process_log"])["score"], "meters": s["meters"]})
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

    # ------------------------------------------------------------ simulation (admin)
    from . import sim_routes
    sim_routes.register(app, instructor=instructor, ApiError=ApiError, content=content, hasher=HASHER, ai_provider=lambda: ai)
    from . import engine_routes
    engine_routes.register(app, instructor=instructor, ApiError=ApiError, DbSession=DbSession, db_dep=db_dep, M=M, get_cached=get_cached, content=content)

    # ------------------------------------------------------------ ops
    @app.get("/healthz")
    def healthz():
        """Is the app up, and is the AI connected? (no secrets: just up, down or off)"""
        state = "off" if ai is None else "down" if ai.circuit_open else "up" if ai.last_ok else "unknown"
        return {"ok": True, "ai": state}

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
    if url:
        from ..ai.client import tailnet_check
        try:
            tailnet_check(url)   # the chat model is the same AI PC: only a Tailscale address is accepted
        except ValueError as e:
            print(f"Live chat disabled: {e}")
            url = None
    gw = Gateway(content_mod.get(), HttpModelClient(url, os.environ.get("MODEL_NAME", "model"), token=os.environ.get("MODEL_TOKEN")) if url else None,
                 slots=int(os.environ.get("MODEL_SLOTS", "4")))
    ai = lib = None
    if os.environ.get("FIXIT_AI_URL"):   # optional: the AI server is never needed to play
        from ..ai.client import AiClient
        from ..ai.generator import Generator
        from ..ai.library import Library
        ai, lib = AiClient.from_env(), Library()
        if ai:
            lib.merge_into(content_mod.get())
            if os.environ.get("FIXIT_AI_GENERATE", "1") == "1":
                threading.Thread(target=Generator(ai, content_mod.get(), lib).run_forever, args=(threading.Event(),), daemon=True, name="ai-generator").start()
    runsets = None
    if ai and lib and os.environ.get("FIXIT_AI_PER_RUN", "1") == "1":
        from ..ai.generator import Generator as _G
        from ..ai.runset import RunSets
        runsets = RunSets(_G(ai, content_mod.get(), lib))   # background priority: live chat lines always go first
    projects = None
    if ai and lib and os.environ.get("FIXIT_AI_PROJECTS", "1") == "1":
        from ..ai.generator import Generator as _G2
        from ..ai.pack import PackBuilder, ProjectJobs
        g2 = _G2(ai, content_mod.get(), lib)   # background priority: chat lines always go first
        projects = ProjectJobs(PackBuilder(g2, lib, content_mod.get()), spare=int(os.environ.get("FIXIT_AI_SPARE_PROJECTS", "2")))
    return create_app(os.environ.get("DB_PATH", "fixit.db"), gateway=gw, library=lib, ai=ai, runsets=runsets, projects=projects)
