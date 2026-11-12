"""The local AI server, tested against a fake Ollama (no model, no GPU needed)."""
import asyncio
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from ai_server.app import create_app
from ai_server.backend import OllamaBackend
from ai_server.config import Settings

TOKEN = "t" * 32
TAILNET = ("100.101.102.103", 40000)


def fake_ollama(calls=None, delay=0.0, fail=None, content='{"ok": true}'):
    async def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append((request.url.path, json.loads(request.content or b"{}")))
        if fail:
            return httpx.Response(fail)
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "9.9.9"})
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "m1"}]})
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "m1", "size": 6 * 2**30, "size_vram": 6 * 2**30, "expires_at": "x"}]})
        if request.url.path == "/api/chat":
            if delay:
                await asyncio.sleep(delay)
            return httpx.Response(200, json={"model": "m1", "message": {"content": content}, "eval_count": 50, "eval_duration": 1_000_000_000,
                                             "prompt_eval_count": 20, "prompt_eval_duration": 100_000_000, "load_duration": 5_000_000})
        return httpx.Response(200, json={})
    return handler


def make(settings=None, **kw):
    s = settings or Settings(model="m1", allowed_models=("m1",), tokens=(TOKEN,))
    backend = OllamaBackend("http://engine", transport=httpx.MockTransport(fake_ollama(**kw)))
    app = create_app(s, backend)
    return TestClient(app, client=TAILNET), app


H = {"Authorization": f"Bearer {TOKEN}"}
BODY = {"messages": [{"role": "user", "content": "hi"}], "schema": {"type": "object"}}


def test_AIS_healthz_needs_no_token_but_everything_else_does():
    with make()[0] as c:
        assert c.get("/healthz").json() == {"status": "ok", "engine": True}
        assert c.post("/v1/generate", json=BODY).status_code == 401
        assert c.post("/v1/generate", json=BODY, headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert c.get("/v1/status").status_code == 401
        assert c.post("/v1/generate", json=BODY, headers=H).status_code == 200


def test_AIS_only_the_tailnet_and_this_machine_may_connect():
    s = Settings(model="m1", allowed_models=("m1",), tokens=(TOKEN,))
    for ip, ok in (("100.64.0.9", True), ("127.0.0.1", True), ("100.127.255.1", True), ("8.8.8.8", False), ("192.168.1.50", False), ("100.128.0.1", False)):
        backend = OllamaBackend("http://engine", transport=httpx.MockTransport(fake_ollama()))
        with TestClient(create_app(s, backend), client=(ip, 5)) as c:
            r = c.post("/v1/generate", json=BODY, headers=H)
            assert (r.status_code == 200) == ok, ip
            if not ok:
                assert r.json()["code"] == "forbidden_network"


def test_AIS_schema_is_enforced_by_the_engine_and_thinking_is_off():
    calls = []
    c, _ = make(calls=calls)
    with c:
        r = c.post("/v1/generate", json={**BODY, "temperature": 0.3, "seed": 7, "max_tokens": 200}, headers=H)
    out = r.json()
    assert json.loads(out["content"]) == {"ok": True} and out["usage"]["tokens_per_s"] == 50.0 and out["usage"]["completion_tokens"] == 50
    path, sent = next(x for x in calls if x[0] == "/api/chat")
    assert sent["format"] == {"type": "object"} and sent["think"] is False and sent["options"]["seed"] == 7 and sent["options"]["num_predict"] == 200
    assert sent["keep_alive"] == "10m" and sent["stream"] is False


def test_AIS_a_model_that_is_not_enabled_is_refused_and_bad_input_is_422():
    with make()[0] as c:
        assert c.post("/v1/generate", json={**BODY, "model": "other:70b"}, headers=H).json()["code"] == "model_not_allowed"
        assert c.post("/v1/generate", json={"messages": []}, headers=H).status_code == 422
        assert c.post("/v1/generate", json={**BODY, "max_tokens": 999999}, headers=H).status_code == 422


def test_AIS_engine_down_and_model_missing_are_clean_errors():
    with make(fail=404)[0] as c:
        assert c.post("/v1/generate", json=BODY, headers=H).json()["code"] == "model_missing"
    with make(fail=500)[0] as c:
        r = c.post("/v1/generate", json=BODY, headers=H)
        assert r.status_code == 503 and r.json()["code"] == "backend_error"

    def boom(request):
        raise httpx.ConnectError("down")
    app = create_app(Settings(model="m1", allowed_models=("m1",), tokens=(TOKEN,)), OllamaBackend("http://engine", transport=httpx.MockTransport(boom)))
    with TestClient(app, client=TAILNET) as c:
        r = c.post("/v1/generate", json=BODY, headers=H)
        assert r.status_code == 503 and r.json()["code"] == "backend_down"
        assert c.get("/healthz").json()["engine"] is False


def test_AIS_status_reports_the_model_in_vram_and_the_queue():
    with make()[0] as c:
        c.post("/v1/generate", json=BODY, headers=H)
        st = c.get("/v1/status", headers=H).json()
    assert st["engine_up"] and st["model_installed"] and st["loaded"][0]["vram_mb"] == 6144 and st["requests"] == 1 and st["queue"]["concurrency"] == 1


def test_AIS_openai_shape_so_the_dialogue_gateway_works_unchanged():
    with make()[0] as c:
        r = c.post("/v1/chat/completions", headers=H, json={"model": "x", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 50,
                                                           "response_format": {"type": "json_schema", "json_schema": {"name": "line", "schema": {"type": "object"}}}})
    d = r.json()
    assert d["choices"][0]["message"]["content"] == '{"ok": true}' and d["usage"]["completion_tokens"] == 50


def test_AIS_only_one_request_runs_on_the_gpu_at_a_time_and_interactive_goes_first():
    order, running, peak = [], [0], [0]

    async def handler(request):
        if request.url.path == "/api/chat":
            body = json.loads(request.content)
            running[0] += 1
            peak[0] = max(peak[0], running[0])
            await asyncio.sleep(0.15)
            order.append(body["messages"][0]["content"])
            running[0] -= 1
            return httpx.Response(200, json={"model": "m1", "message": {"content": "{}"}})
        return httpx.Response(200, json={"version": "1"})
    s = Settings(model="m1", allowed_models=("m1",), tokens=(TOKEN,))
    app = create_app(s, OllamaBackend("http://engine", transport=httpx.MockTransport(handler)))

    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=TAILNET), base_url="http://ai") as c:
            async with app.router.lifespan_context(app):
                msg = lambda t, p: c.post("/v1/generate", headers=H, json={"messages": [{"role": "user", "content": t}], "priority": p, "schema": {"type": "object"}})   # noqa: E731
                first = asyncio.create_task(msg("first", "background"))
                await asyncio.sleep(0.05)
                rest = [asyncio.create_task(msg("bg2", "background")), asyncio.create_task(msg("urgent", "interactive"))]
                return [r.status_code for r in await asyncio.gather(first, *rest)]
    assert asyncio.run(go()) == [200, 200, 200]
    assert peak[0] == 1                                    # never two at once
    assert order == ["first", "urgent", "bg2"]             # the interactive request jumped the waiting background one


def test_AIS_a_full_queue_says_busy_instead_of_hanging():
    s = Settings(model="m1", allowed_models=("m1",), tokens=(TOKEN,), max_queue_interactive=1, queue_wait_s=0.3, request_timeout_s=5)
    c, app = make(settings=s, delay=0.6)
    codes = []

    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=TAILNET), base_url="http://ai") as cl:
            async with app.router.lifespan_context(app):
                rs = await asyncio.gather(*[cl.post("/v1/generate", headers=H, json=BODY) for _ in range(3)])
                codes.extend(sorted(r.status_code for r in rs))
    asyncio.run(go())
    assert codes[0] == 200 and 429 in codes


def test_AIS_settings_refuse_unsafe_configuration(monkeypatch):
    for k in ("AI_BIND", "AI_TOKEN", "AI_TOKENS_FILE", "AI_ALLOW_ANY_BIND"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("AI_TOKEN", TOKEN)
    monkeypatch.setenv("AI_BIND", "0.0.0.0")
    with pytest.raises(SystemExit, match="every interface"):
        Settings.from_env()
    monkeypatch.setenv("AI_BIND", "127.0.0.1")
    monkeypatch.setenv("AI_TOKEN", "short")
    with pytest.raises(SystemExit, match="24 characters"):
        Settings.from_env()
    monkeypatch.setenv("AI_TOKEN", TOKEN)
    s = Settings.from_env()
    assert s.host == "127.0.0.1" and s.tokens == (TOKEN,) and s.max_concurrency == 1
    monkeypatch.delenv("AI_TOKEN")
    with pytest.raises(SystemExit, match="No access token"):
        Settings.from_env()


def test_AIS_free_form_requests_are_refused_because_only_structured_answers_are_served():
    with make()[0] as c:
        r = c.post("/v1/generate", json={"messages": [{"role": "user", "content": "tell me a joke"}]}, headers=H)
        assert r.status_code == 422 and r.json()["code"] == "schema_required"
        big = {**BODY, "messages": [{"role": "user", "content": "x" * 15000}]}
        assert c.post("/v1/generate", json=big, headers=H).json()["code"] == "prompt_too_large"


def test_AIS_an_answer_that_breaks_the_schema_is_retried_once_then_refused():
    calls, schema = [], {"type": "object", "required": ["a"], "properties": {"a": {"type": "integer"}}}

    def run(replies):
        async def handler(request):
            if request.url.path != "/api/chat":
                return httpx.Response(200, json={"version": "1"})
            calls.append(json.loads(request.content)["options"].get("seed"))
            return httpx.Response(200, json={"model": "m1", "message": {"content": replies[min(len(calls) - 1, len(replies) - 1)]}})
        app = create_app(Settings(model="m1", allowed_models=("m1",), tokens=(TOKEN,)), OllamaBackend("http://engine", transport=httpx.MockTransport(handler)))
        with TestClient(app, client=TAILNET) as c:
            return c.post("/v1/generate", json={**BODY, "schema": schema, "seed": 5}, headers=H), c.get("/v1/status", headers=H).json()
    r, st = run(['{"a": "no"}', '{"a": 1}'])
    assert r.status_code == 200 and r.json()["usage"]["attempts"] == 2 and calls == [5, 6] and st["output_retries"] == 1
    calls.clear()
    r, _ = run(["not json", "{}"])
    assert r.status_code == 502 and r.json()["code"] == "bad_output" and len(calls) == 2


def test_AIS_llamacpp_engine_speaks_the_same_interface():
    from ai_server.backend_llamacpp import LlamaCppBackend
    seen = {}

    async def handler(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/props":
            return httpx.Response(200, json={"model_path": "C:\models\qwen.gguf"})
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"model": "qwen", "choices": [{"message": {"content": '{"ok": true}'}}],
                                         "timings": {"prompt_n": 30, "prompt_ms": 20.4, "predicted_n": 40, "predicted_ms": 600.0, "predicted_per_second": 66.7, "cache_n": 25}})
    be = LlamaCppBackend("http://engine", transport=httpx.MockTransport(handler))
    s = Settings(model="qwen.gguf", allowed_models=("qwen.gguf",), tokens=(TOKEN,), engine="llamacpp")
    with TestClient(create_app(s, be), client=TAILNET) as c:
        r = c.post("/v1/generate", json={**BODY, "seed": 3}, headers=H).json()
        st = c.get("/v1/status", headers=H).json()
    assert json.loads(r["content"]) == {"ok": True} and r["usage"]["tokens_per_s"] == 66.7 and r["usage"]["cached_prompt_tokens"] == 25
    assert seen["response_format"]["json_schema"]["schema"] == {"type": "object"} and seen["chat_template_kwargs"] == {"enable_thinking": False} and seen["seed"] == 3
    assert st["engine_up"] and st["loaded"][0]["name"] == "qwen.gguf"


def test_AIS_console_page_is_public_but_ask_and_status_need_the_token_and_the_answer_is_structured():
    calls = []
    c, _ = make(calls=calls, content='{"answer": "A fixed-length time box."}')
    with c:
        page = c.get("/console")
        assert page.status_code == 200 and "AI console" in page.text and page.headers["cache-control"] == "no-store"
        assert c.post("/v1/ask", json={"question": "hi"}).status_code == 401
        assert c.post("/v1/ask", json={"question": ""}, headers=H).status_code == 422
        assert c.post("/v1/ask", json={"question": "x" * 501}, headers=H).status_code == 422
        r = c.post("/v1/ask", json={"question": "What is a Sprint?"}, headers=H).json()
    assert r["model"] == "m1" and r["tokens_per_s"] == 50.0 and "answer" in r
    sent = next(x for x in calls if x[0] == "/api/chat")[1]
    assert sent["format"]["required"] == ["answer"] and sent["options"]["num_predict"] == 220          # still a short, structured answer
    assert sent["messages"][1]["content"] == "What is a Sprint?" and "Scrum" in sent["messages"][0]["content"]


def test_AIS_console_is_refused_outside_the_tailnet():
    s = Settings(model="m1", allowed_models=("m1",), tokens=(TOKEN,))
    backend = OllamaBackend("http://engine", transport=httpx.MockTransport(fake_ollama()))
    with TestClient(create_app(s, backend), client=("8.8.8.8", 5)) as c:
        assert c.get("/console").status_code == 403
