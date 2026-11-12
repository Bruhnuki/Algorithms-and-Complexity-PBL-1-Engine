"""Optional engine: llama.cpp's `llama-server` (OpenAI-compatible, one model per process). Same interface as OllamaBackend.

Start it with the model file and lean flags, for example:
  llama-server -m model.gguf --host 127.0.0.1 --port 8081 -ngl 99 -c 3072 -fa on -ctk q8_0 -ctv q8_0 --parallel 1 --cache-reuse 256 --no-webui
"""
from __future__ import annotations

import httpx

from .backend import BackendError


class LlamaCppBackend:
    def __init__(self, base_url: str, *, transport: httpx.AsyncBaseTransport | None = None):
        self.http = httpx.AsyncClient(base_url=base_url, transport=transport, timeout=None)

    async def aclose(self):
        await self.http.aclose()

    async def version(self, timeout: float = 2.0) -> str | None:
        try:
            r = await self.http.get("/health", timeout=timeout)
            return "llama.cpp" if r.status_code == 200 and r.json().get("status") == "ok" else None
        except (httpx.HTTPError, ValueError):
            return None

    async def loaded(self) -> list[dict]:
        try:
            r = await self.http.get("/props", timeout=2.0)
            path = r.json().get("model_path") or r.json().get("model_alias") or "model"
            return [{"name": str(path).replace("\\", "/").rsplit("/", 1)[-1], "size_mb": None, "vram_mb": None, "expires_at": None}]
        except (httpx.HTTPError, ValueError):
            return []

    async def installed(self) -> list[str]:
        return [m["name"] for m in await self.loaded()]

    async def chat(self, *, model: str, messages: list[dict], schema: dict | None, options: dict, keep_alive: str, think: bool, timeout: float) -> dict:
        body = {"messages": messages, "stream": False, "temperature": options.get("temperature", 0.7), "max_tokens": options.get("num_predict", 600),
                "chat_template_kwargs": {"enable_thinking": think}, "cache_prompt": True}
        if options.get("seed") is not None:
            body["seed"] = options["seed"]
        if schema is not None:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "answer", "strict": True, "schema": schema}}   # grammar-constrained
        try:
            r = await self.http.post("/v1/chat/completions", json=body, timeout=timeout)
        except httpx.TimeoutException as e:
            raise BackendError("timeout", "the model took too long", 504) from e
        except httpx.HTTPError as e:
            raise BackendError("backend_down", "the model engine is not reachable") from e
        if r.status_code != 200:
            raise BackendError("backend_error", f"engine answered {r.status_code}")
        d = r.json()
        t = d.get("timings") or {}
        u = d.get("usage") or {}
        return {"content": ((d.get("choices") or [{}])[0].get("message") or {}).get("content", ""), "model": d.get("model", model),
                "usage": {"prompt_tokens": t.get("prompt_n", u.get("prompt_tokens", 0)), "completion_tokens": t.get("predicted_n", u.get("completion_tokens", 0)),
                          "load_ms": 0, "prompt_ms": round(t.get("prompt_ms", 0)), "gen_ms": round(t.get("predicted_ms", 0)),
                          "tokens_per_s": round(t["predicted_per_second"], 1) if t.get("predicted_per_second") else None,
                          "cached_prompt_tokens": t.get("cache_n")}}

    async def unload(self, model: str) -> None:
        return None   # one process, one model: stop the process to free VRAM (or start it with --sleep-idle-seconds)

    async def warm(self, model: str, keep_alive: str, num_ctx: int) -> None:
        await self.chat(model=model, messages=[{"role": "user", "content": "ok"}], schema=None, options={"num_predict": 1}, keep_alive=keep_alive, think=False, timeout=120.0)
