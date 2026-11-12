"""HTTP API in front of the model.

Security: every route except /healthz needs a bearer token, and the caller's address must be inside the
Tailscale network (or this machine). The server listens on the Tailscale address only, never on every interface.
Capacity: one request runs on the GPU at a time; interactive requests go ahead of background pre-generation.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import ipaddress
import itertools
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager

import jsonschema
from fastapi import Depends, FastAPI, Request
from pathlib import Path

from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from .backend import BackendError, OllamaBackend
from .config import Settings, valid_model_name

INTERACTIVE, BACKGROUND = 0, 1


class ApiError(Exception):
    def __init__(self, status: int, code: str, detail: str):
        super().__init__(detail)
        self.status, self.code, self.detail = status, code, detail


class Message(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str = Field(max_length=16000)


class GenerateIn(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=8)
    schema_: dict | None = Field(default=None, alias="schema")   # JSON schema the answer must follow
    model: str | None = None
    max_tokens: int = Field(default=600, ge=1, le=4000)
    temperature: float = Field(default=0.7, ge=0, le=1.5)
    seed: int | None = None
    priority: str = Field(default="interactive", pattern="^(interactive|background)$")


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    model: str | None = None   # must be one of the server's allowed models


ASK_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["answer"], "properties": {"answer": {"type": "string"}}}
ASK_SYSTEM = "You are answering one quick test question from the developer of a classroom game that teaches Scrum. Answer in one to three short plain sentences."
CONSOLE = (Path(__file__).parent / "console.html").read_text(encoding="utf-8")


class _Job:
    __slots__ = ("run", "fut", "started", "cancelled")

    def __init__(self, run):
        self.run, self.fut, self.started, self.cancelled = run, asyncio.get_running_loop().create_future(), asyncio.Event(), False


class Scheduler:
    """A priority queue with a fixed number of workers. Lower number runs first, then first come first served."""

    def __init__(self, workers: int, max_interactive: int, max_background: int):
        self.q: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self.workers, self.caps, self.depth = workers, {INTERACTIVE: max_interactive, BACKGROUND: max_background}, {INTERACTIVE: 0, BACKGROUND: 0}
        self.running, self.seq, self.tasks = 0, itertools.count(), []

    def start(self):
        self.tasks = [asyncio.create_task(self._work()) for _ in range(self.workers)]

    async def stop(self):
        for t in self.tasks:
            t.cancel()

    async def _work(self):
        while True:
            prio, _, job = await self.q.get()
            self.depth[prio] -= 1
            if job.cancelled:
                continue
            self.running += 1
            job.started.set()
            try:
                job.fut.set_result(await job.run())
            except Exception as e:   # noqa: BLE001 (delivered to the waiting request)
                if not job.fut.done():
                    job.fut.set_exception(e)
            finally:
                self.running -= 1

    async def submit(self, prio: int, run, *, wait_s: float, timeout_s: float):
        if self.depth[prio] >= self.caps[prio]:
            raise ApiError(429, "queue_full", "the AI is busy; try again shortly")
        job = _Job(run)
        self.depth[prio] += 1
        await self.q.put((prio, next(self.seq), job))
        try:
            await asyncio.wait_for(job.started.wait(), wait_s)
        except asyncio.TimeoutError:
            job.cancelled = True
            raise ApiError(429, "queue_timeout", "waited too long for the AI") from None
        try:
            return await asyncio.wait_for(job.fut, timeout_s)
        except asyncio.TimeoutError:
            raise ApiError(504, "timeout", "the model took too long") from None


def _fits(text: str, schema: dict) -> bool:
    try:
        jsonschema.validate(json.loads(text), schema)
        return True
    except (ValueError, jsonschema.SchemaError, jsonschema.ValidationError):
        return False


class _Stats:
    def __init__(self):
        self.t0, self.requests, self.errors, self.last_ms, self.retries = time.monotonic(), 0, 0, None, 0
        self.rate: dict[str, deque] = defaultdict(deque)


def create_app(settings: Settings, backend: OllamaBackend | None = None) -> FastAPI:
    nets = settings.networks()
    stats = _Stats()
    if backend is None and settings.engine == "llamacpp":
        from .backend_llamacpp import LlamaCppBackend
        backend = LlamaCppBackend(settings.backend_url)
    be = backend or OllamaBackend(settings.backend_url)
    sched = Scheduler(settings.max_concurrency, settings.max_queue_interactive, settings.max_queue_background)

    @asynccontextmanager
    async def lifespan(_):
        sched.start()
        yield
        await sched.stop()
        await be.aclose()

    app = FastAPI(title="Local AI server", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings, app.state.backend, app.state.sched = settings, be, sched

    @app.exception_handler(ApiError)
    async def _err(_, e: ApiError):
        return JSONResponse({"code": e.code, "detail": e.detail}, status_code=e.status)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        try:
            ip = ipaddress.ip_address(request.client.host if request.client else "")
        except ValueError:
            return JSONResponse({"code": "forbidden_network", "detail": "unknown caller"}, status_code=403)
        if not any(ip in n for n in nets):   # defence in depth: even if the port were reachable, only the tailnet may talk to it
            return JSONResponse({"code": "forbidden_network", "detail": "not on the private network"}, status_code=403)
        if int(request.headers.get("content-length") or 0) > 200_000:
            return JSONResponse({"code": "too_large", "detail": "request too large"}, status_code=413)
        return await call_next(request)

    def auth(request: Request) -> str:
        got = request.headers.get("authorization", "")
        tok = got[7:] if got.lower().startswith("bearer ") else ""
        hit = next((t for t in settings.tokens if hmac.compare_digest(t.encode(), tok.encode())), None)
        if hit is None:
            raise ApiError(401, "unauthorized", "missing or wrong access token")
        now, q = time.monotonic(), stats.rate[hit]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= settings.rate_per_min:
            raise ApiError(429, "rate_limited", "too many requests")
        q.append(now)
        return hit

    async def run_model(body: GenerateIn) -> dict:
        model = body.model or settings.model
        if model not in settings.allowed_models or not valid_model_name(model):
            raise ApiError(422, "model_not_allowed", "that model is not enabled on this server")
        if settings.require_schema and not body.schema_:
            raise ApiError(422, "schema_required", "this server only produces structured answers; send a schema")
        if sum(len(m.content) for m in body.messages) > settings.max_prompt_chars:
            raise ApiError(413, "prompt_too_large", "prompt too large")
        prio = INTERACTIVE if body.priority == "interactive" else BACKGROUND
        options = {"temperature": body.temperature, "num_ctx": settings.num_ctx, "num_predict": min(body.max_tokens, settings.max_tokens_cap)}
        if body.seed is not None:
            options["seed"] = body.seed
        t0 = time.monotonic()

        async def call():
            msgs = [m.model_dump() for m in body.messages]
            out = None
            for attempt in range(2 if settings.validate_output and body.schema_ else 1):   # one cheap retry with a different seed
                opts = {**options, "seed": (options.get("seed") or 0) + attempt} if attempt else options
                out = await be.chat(model=model, messages=msgs, schema=body.schema_, options=opts, keep_alive=settings.keep_alive,
                                    think=settings.think, timeout=settings.request_timeout_s)
                if len(out["content"]) > settings.max_output_chars:
                    raise BackendError("output_too_large", "the model answered with too much text", 502)
                if not (settings.validate_output and body.schema_) or _fits(out["content"], body.schema_):
                    out["usage"]["attempts"] = attempt + 1
                    return out
                stats.retries += 1
            raise BackendError("bad_output", "the model did not produce a valid answer", 502)
        stats.requests += 1
        try:
            out = await sched.submit(prio, call, wait_s=settings.queue_wait_s if prio == INTERACTIVE else settings.background_wait_s,
                                     timeout_s=settings.request_timeout_s + 5)
        except BackendError as e:
            stats.errors += 1
            raise ApiError(e.status, e.code, e.detail) from e
        except ApiError:
            stats.errors += 1
            raise
        total = round((time.monotonic() - t0) * 1000)
        stats.last_ms = total
        out["usage"]["total_ms"] = total
        out["request_id"] = uuid.uuid4().hex[:12]
        return out

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok", "engine": await be.version(timeout=1.5) is not None}

    @app.get("/console", response_class=HTMLResponse)
    async def console():
        """A small page to check the AI is running and ask it a test question. The page itself is public; everything it does needs the token."""
        return HTMLResponse(CONSOLE, headers={"Cache-Control": "no-store"})

    @app.post("/v1/ask")
    async def ask(body: AskIn, _: str = Depends(auth)):
        """A diagnostic: one short question, one short answer, still behind the token and the network guard."""
        out = await run_model(GenerateIn(messages=[{"role": "system", "content": ASK_SYSTEM}, {"role": "user", "content": body.question}],
                                         schema=ASK_SCHEMA, max_tokens=220, temperature=0.4, priority="interactive", model=body.model))
        try:
            answer = str(json.loads(out["content"]).get("answer", "")).strip()
        except ValueError:
            answer = out["content"].strip()
        u = out["usage"]
        return {"answer": answer, "model": out["model"], "total_ms": u.get("total_ms"), "tokens_per_s": u.get("tokens_per_s")}

    @app.get("/v1/status")
    async def status(_: str = Depends(auth)):
        version = await be.version()
        return {"server": "ok", "model": settings.model, "allowed_models": list(settings.allowed_models), "engine_version": version,
                "engine_up": version is not None, "model_installed": settings.model in await be.installed() if version else False,
                "loaded": await be.loaded() if version else [], "queue": {"waiting_interactive": sched.depth[INTERACTIVE], "waiting_background": sched.depth[BACKGROUND],
                                                                          "running": sched.running, "concurrency": settings.max_concurrency},
                "last_total_ms": stats.last_ms, "requests": stats.requests, "errors": stats.errors, "output_retries": stats.retries, "uptime_s": round(time.monotonic() - stats.t0),
                "keep_alive": settings.keep_alive, "num_ctx": settings.num_ctx}

    @app.post("/v1/generate")
    async def generate(body: GenerateIn, _: str = Depends(auth)):
        return await run_model(body)

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request, _: str = Depends(auth)):
        """OpenAI-shaped, so the game's existing dialogue gateway works through this server unchanged."""
        raw = await request.json()
        schema = (((raw.get("response_format") or {}).get("json_schema") or {}).get("schema"))
        body = GenerateIn(messages=raw.get("messages", []), schema=schema, max_tokens=min(int(raw.get("max_tokens") or 200), 4000),
                          temperature=min(float(raw.get("temperature", 0.7)), 1.5), priority="interactive")
        out = await run_model(body)
        u = out["usage"]
        return {"id": out["request_id"], "object": "chat.completion", "model": out["model"],
                "choices": [{"index": 0, "message": {"role": "assistant", "content": out["content"]}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": u["prompt_tokens"], "completion_tokens": u["completion_tokens"], "total_tokens": u["prompt_tokens"] + u["completion_tokens"]}}

    @app.post("/v1/warmup")
    async def warmup(_: str = Depends(auth)):
        """Load the model into VRAM before the first player needs it."""
        t0 = time.monotonic()
        try:
            await be.warm(settings.model, settings.keep_alive, settings.num_ctx)
        except Exception:   # noqa: BLE001
            raise ApiError(503, "backend_down", "the model engine is not reachable") from None
        return {"loaded": True, "ms": round((time.monotonic() - t0) * 1000)}

    @app.post("/v1/unload")
    async def unload(_: str = Depends(auth)):
        """Free the VRAM now (for example before you start a game on this PC)."""
        try:
            await be.unload(settings.model)
        except Exception:   # noqa: BLE001
            raise ApiError(503, "backend_down", "the model engine is not reachable") from None
        return {"unloaded": True}

    return app
