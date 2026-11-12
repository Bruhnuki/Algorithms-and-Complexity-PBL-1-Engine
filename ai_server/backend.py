"""The only file that knows about Ollama. Replace it to use another engine (for example llama.cpp)."""
from __future__ import annotations

import httpx


class BackendError(Exception):
    def __init__(self, code: str, detail: str, status: int = 503):
        super().__init__(detail)
        self.code, self.detail, self.status = code, detail, status


class OllamaBackend:
    def __init__(self, base_url: str, *, transport: httpx.AsyncBaseTransport | None = None):
        self.http = httpx.AsyncClient(base_url=base_url, transport=transport, timeout=None)

    async def aclose(self):
        await self.http.aclose()

    async def version(self, timeout: float = 2.0) -> str | None:
        try:
            r = await self.http.get("/api/version", timeout=timeout)
            return r.json().get("version") if r.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            return None

    async def loaded(self) -> list[dict]:
        """Models currently in VRAM, from Ollama's own report."""
        try:
            r = await self.http.get("/api/ps", timeout=2.0)
            return [{"name": m.get("name"), "size_mb": round(m.get("size", 0) / 2**20), "vram_mb": round(m.get("size_vram", 0) / 2**20),
                     "expires_at": m.get("expires_at")} for m in r.json().get("models", [])]
        except (httpx.HTTPError, ValueError):
            return []

    async def installed(self) -> list[str]:
        try:
            r = await self.http.get("/api/tags", timeout=3.0)
            return [m["name"] for m in r.json().get("models", [])]
        except (httpx.HTTPError, ValueError, KeyError):
            return []

    async def chat(self, *, model: str, messages: list[dict], schema: dict | None, options: dict, keep_alive: str, think: bool, timeout: float) -> dict:
        body = {"model": model, "messages": messages, "stream": False, "think": think, "keep_alive": keep_alive, "options": options}
        if schema is not None:
            body["format"] = schema            # grammar-constrained decoding: the model cannot emit invalid JSON
        try:
            r = await self.http.post("/api/chat", json=body, timeout=timeout)
        except httpx.TimeoutException as e:
            raise BackendError("timeout", "the model took too long", 504) from e
        except httpx.HTTPError as e:
            raise BackendError("backend_down", "the model engine is not reachable") from e
        if r.status_code == 404:
            raise BackendError("model_missing", f"model {model!r} is not installed")
        if r.status_code != 200:
            raise BackendError("backend_error", f"engine answered {r.status_code}")
        d = r.json()
        ns = lambda k: d.get(k) or 0   # noqa: E731
        ev, en = ns("eval_count"), ns("eval_duration")
        return {"content": (d.get("message") or {}).get("content", ""), "model": d.get("model", model),
                "usage": {"prompt_tokens": ns("prompt_eval_count"), "completion_tokens": ev, "load_ms": round(ns("load_duration") / 1e6),
                          "prompt_ms": round(ns("prompt_eval_duration") / 1e6), "gen_ms": round(en / 1e6),
                          "tokens_per_s": round(ev / (en / 1e9), 1) if en else None}}

    async def unload(self, model: str) -> None:
        await self.http.post("/api/generate", json={"model": model, "keep_alive": 0}, timeout=10.0)

    async def warm(self, model: str, keep_alive: str, num_ctx: int) -> None:
        await self.http.post("/api/generate", json={"model": model, "keep_alive": keep_alive, "options": {"num_ctx": num_ctx}}, timeout=120.0)
