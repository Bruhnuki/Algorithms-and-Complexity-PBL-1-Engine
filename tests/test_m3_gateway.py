import json
import sqlite3
import time

import httpx
import pytest

from api_helpers import Driver, Env, mock_client, new_run
from fixit import bot
from fixit.engines import e1
from fixit.gateway import context as gctx
from fixit.gateway.gateway import EVENT_TYPES, Gateway, Request

GOOD = {"text": "Did your last push really match the doc? Be honest.", "tone": "pushy"}


def reply(obj, delay=0.0):
    def handler(request: httpx.Request) -> httpx.Response:
        if delay:
            time.sleep(delay)
        content = obj if isinstance(obj, str) else json.dumps(obj)
        return httpx.Response(200, json={"model": "mock-model", "usage": {"prompt_tokens": 123},
                                         "choices": [{"message": {"content": content}}]})
    return handler


def dead(request):
    raise httpx.ConnectError("model server is off")


def gw(content, handler, **kw):
    return Gateway(content, mock_client(handler), **kw)


def req(content, **kw):
    t = content.tickets["final_price"]
    base = dict(event_type="standup_question", teammate_id="dev1", seed=3, n=1, user_key="u1",
                facts={"ticket_title": t["title"]}, forbidden=[o["text"] for o in t["options"] if o["effect"] == "correct"])
    base.update(kw)
    return Request(**base)


def test_TEAM1_ok_line_from_model(content):
    line = gw(content, reply(GOOD)).generate(req(content))
    assert line.source == "llm" and line.text == GOOD["text"] and line.tone == "pushy"
    assert line.model == "mock-model" and line.prompt_tokens == 123


def test_TEAM1_model_down_fallback(content):
    line = gw(content, dead).generate(req(content))
    assert line.source == "fallback" and line.reason == "model_error" and line.text


def test_TEAM1_no_model_configured_fallback(content):
    assert Gateway(content, None).generate(req(content)).source == "fallback"


def test_TEAM1_timeout_fallback(content):
    line = gw(content, reply(GOOD, delay=0.4), run_timeout=0.1).generate(req(content))
    assert line.source == "fallback" and line.reason == "timeout"


def test_TEAM1_queue_wait_timeout_fallback(content):
    g = gw(content, reply(GOOD, delay=0.5), slots=1, queue_wait=0.05, run_timeout=2)
    import threading
    t = threading.Thread(target=lambda: g.generate(req(content, user_key="a")))
    t.start()
    time.sleep(0.1)
    line = g.generate(req(content, user_key="b"))
    t.join()
    assert line.source == "fallback" and line.reason == "queue_timeout"


@pytest.mark.parametrize("bad", ["not json at all", {"text": "hi"}, {"text": "hi", "tone": "angry"},
                                 {"text": "hi", "tone": "calm", "extra": 1}, {"text": "", "tone": "calm"}])
def test_TEAM1_schema_invalid_retry_once_then_fallback(content, bad):
    calls = []

    def h(request):
        calls.append(1)
        return reply(bad)(request)
    line = gw(content, h).generate(req(content))
    assert line.source == "fallback" and len(calls) == 2


def test_TEAM1_retry_recovers(content):
    seq = iter(["garbage", json.dumps(GOOD)])

    def h(request):
        return reply(next(seq))(request)
    line = gw(content, h).generate(req(content))
    assert line.source == "llm"


def test_TEAM1_no_spoiler(content):
    spoil = {"text": "Just change it to return price * 0.9 and you are done.", "tone": "calm"}
    calls = []

    def h(request):
        calls.append(1)
        return reply(spoil)(request)
    line = gw(content, h).generate(req(content))
    assert line.source == "fallback" and line.reason == "invalid:spoiler" and len(calls) == 2
    assert not any("0.9" in ln for ln in content.teammates["dev1"]["fallback_lines"]["standup_question"])


def test_TEAM1_no_secret_leak(content):
    leak = {"text": "Ines is interviewing at another company, you know.", "tone": "calm"}
    g = gw(content, reply(leak))
    assert g.generate(req(content, teammate_id="po")).reason == "invalid:secret"
    assert g.generate(req(content, teammate_id="dev1")).source == "llm"  # her own secret is not "another teammate's"


def test_TEAM1_max_40_words(content):
    long = {"text": " ".join(["word"] * 41), "tone": "calm"}
    assert gw(content, reply(long)).generate(req(content)).reason == "invalid:length"
    ok = {"text": " ".join(["word"] * 40), "tone": "calm"}
    assert gw(content, reply(ok)).generate(req(content)).source == "llm"


def test_TEAM1_quota_20_per_minute(content):
    now = [0.0]
    g = gw(content, reply(GOOD), clock=lambda: now[0])
    lines = [g.generate(req(content, n=i)) for i in range(21)]
    assert [x.source for x in lines[:20]] == ["llm"] * 20 and lines[20].reason == "quota"
    assert g.generate(req(content, user_key="other")).source == "llm"
    now[0] += 61
    assert g.generate(req(content)).source == "llm"


def test_TEAM1_fallback_pool_ge_3_per_teammate_event(content):
    assert set(content.teammates) == {"po", "dev1", "dev2"}
    for t in content.teammates.values():
        for et in EVENT_TYPES:
            assert len(set(t["fallback_lines"][et])) >= 3, (t["id"], et)
            for ln in t["fallback_lines"][et]:
                assert len(ln.split()) <= 40


def test_TEAM1_fallback_choice_seeded_replayable(content):
    a, b = Gateway(content, None), Gateway(content, None)
    assert [a.generate(req(content, n=i)).text for i in range(10)] == [b.generate(req(content, n=i)).text for i in range(10)]


def test_TEAM1_input_has_no_student_text(content):
    g = gw(content, reply(GOOD))
    msgs = g.build_messages(req(content, facts={"ticket_title": "T", "stage": "BUILD"}))
    blob = json.dumps(msgs)
    assert "Never state the correct code fix" in blob and "Definition of Done" in blob
    # the request type has no free-text field a student could fill
    assert set(Request.__dataclass_fields__) == {"event_type", "teammate_id", "facts", "memory", "stage", "seed", "n", "user_key", "forbidden"}
    assert "return price * 0.9" not in blob  # the correct patch is never sent to the model


def test_TEAM1_prompt_hides_other_secrets_instruction(content):
    msgs = gw(content, reply(GOOD)).build_messages(req(content, teammate_id="po"))
    assert content.teammates["dev1"]["secret"] in msgs[0]["content"]  # listed as forbidden, never as own knowledge
    assert content.teammates["po"]["secret"] not in msgs[0]["content"]


def test_MEM1_e1_segments_within_budget_3000_cap_4000(content):
    segs = [{"id": f"s{i}", "text": "y" * 800, "seq": i} for i in range(100)]
    out = e1.select_segments(segs, "BUILD")
    assert sum(e1.tokens(s["text"]) for s in out) <= 3000
    assert sum(e1.tokens(s["text"]) for s in e1.select_segments(segs, "BUILD", budget=99999)) <= 4000


def test_MEM1_pinned_persona_and_dod_always_included(content):
    g = gw(content, reply(GOOD))
    big = [{"id": f"s{i}", "text": "z" * 900, "seq": i + 1} for i in range(200)]
    msgs = g.build_messages(req(content, memory=big))
    assert "Definition of Done" in msgs[0]["content"] and "Marlo" not in msgs[0]["content"] and "Ines" in msgs[0]["content"]


def test_MEM1_contradiction_prompt_uses_stored_answer(content):
    from fixit.rules import reducer
    s, _ = reducer.start_run(1, content)
    s["standups"].append({"n": 1, "ticket": "final_price", "answer": "accurate", "contradicted": False})
    segs = gctx.memory_segments(s, content)
    msgs = gw(content, reply(GOOD)).build_messages(req(content, memory=segs))
    assert "accurate answer about" in msgs[1]["content"]


def test_TEAM1_log_fields_and_status(content):
    g = gw(content, reply(GOOD))
    assert g.status()["last_latency_ms"] is None
    line = g.generate(req(content))
    st = g.status()
    assert st["last_latency_ms"] == line.latency_ms and st["model"] == "mock-model" and st["enabled"]


# ---------------------------------------------------------------- end to end through the API
def _play(tmp_path, content, gateway, name):
    e = Env(tmp_path, content, gateway=gateway, name=name)
    c = e.signup("a@x.io")
    rid = new_run(c)
    Driver(c, rid).replay_bot(bot.play(11, content, "coach_delegate"))
    s = c.get(f"/api/v1/runs/{rid}/state").json()
    return e, c, rid, s


def test_TEAM1_full_sprint_model_on_and_off_same_state(tmp_path, content):
    e1_, c1, r1, on = _play(tmp_path, content, gw(content, reply(GOOD)), "on.db")
    e2_, c2, r2, off = _play(tmp_path, content, gw(content, dead), "off.db")
    e3_, c3, r3, none = _play(tmp_path, content, None, "none.db")
    assert on["state"] == off["state"] == none["state"] and on["state"]["status"] == "ended"
    evs = lambda s: [{k: v for k, v in e.items() if k != "seq"} for e in s["events"]]  # noqa: E731
    assert evs(on) == evs(off) == evs(none)  # the model never changes game events
    assert {ln["id"] for ln in on["lines"]} and len(on["lines"]) == len(off["lines"]) > 0
    assert none["lines"] == []


def test_TEAM1_transcript_records_source(tmp_path, content):
    e, c, rid, _ = _play(tmp_path, content, gw(content, dead), "x.db")
    srcs = {r[0] for r in sqlite3.connect(e.db).execute("select source from transcript_lines")}
    assert srcs == {"fallback"}
    e, c, rid, _ = _play(tmp_path, content, gw(content, reply(GOOD)), "y.db")
    assert {r[0] for r in sqlite3.connect(e.db).execute("select source from transcript_lines")} == {"llm"}


def test_TEAM1_dialogue_off_command_path(tmp_path, content):
    e = Env(tmp_path, content, gateway=gw(content, reply(GOOD, delay=0.4)))
    e.settings.dialogue_inline = False  # production mode: lines arrive asynchronously
    c = e.signup("a@x.io")
    rid = new_run(c)
    t0 = time.perf_counter()
    assert Driver(c, rid).cmd("advance_stage", to="STANDUP").status_code == 200
    assert time.perf_counter() - t0 < 0.3
    for _ in range(40):
        if c.get(f"/api/v1/runs/{rid}/state").json()["lines"]:
            break
        time.sleep(0.05)
    assert c.get(f"/api/v1/runs/{rid}/state").json()["lines"]


def test_model_status_endpoint(tmp_path, content):
    e = Env(tmp_path, content, gateway=gw(content, reply(GOOD)))
    c = e.signup("a@x.io")
    assert c.get("/api/v1/model/status").json()["enabled"] is True
