import logging
import sqlite3
import time

import pytest

from api_helpers import PW, Driver, Env, new_run
from fixit import bot
from fixit.api.app import create_app
from fixit.rules import reducer


@pytest.fixture
def env(tmp_path, content):
    return Env(tmp_path, content)


# ---------------------------------------------------------------- AUTH-1
def test_AUTH1_password_never_in_db_or_logs(env, tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    secret = "S3cret-Passw0rd-unique!"
    c = env.client()
    c.post("/api/v1/auth/register", json={"email": "a@x.io", "password": secret, "display_name": "A"})
    c.post("/api/v1/auth/login", json={"email": "a@x.io", "password": secret})
    c.post("/api/v1/auth/login", json={"email": "a@x.io", "password": secret + "x"})
    blob = b"".join(p.read_bytes() for p in tmp_path.glob("app.db*"))
    assert secret.encode() not in blob and secret not in caplog.text


def test_AUTH1_argon2id_params(env):
    env.client().post("/api/v1/auth/register", json={"email": "a@x.io", "password": PW, "display_name": "A"})
    h = sqlite3.connect(env.db).execute("select password_hash from users").fetchone()[0]
    assert h.startswith("$argon2id$v=19$m=19456,t=2,p=1$")


def test_AUTH1_generic_error_wrong_pw_vs_unknown_email(env):
    env.signup("a@x.io")
    c = env.client()
    r1 = c.post("/api/v1/auth/login", json={"email": "a@x.io", "password": "wrong-password-1"})
    r2 = c.post("/api/v1/auth/login", json={"email": "nobody@x.io", "password": "wrong-password-1"})
    assert r1.status_code == r2.status_code == 401 and r1.json() == r2.json()
    assert r1.headers["content-type"].startswith("application/problem+json") and r1.json()["code"] == "INVALID_CREDENTIALS"


def test_AUTH1_short_password_and_duplicate_email(env):
    c = env.client()
    assert c.post("/api/v1/auth/register", json={"email": "a@x.io", "password": "short", "display_name": "A"}).status_code == 422
    env.signup("a@x.io")
    r = c.post("/api/v1/auth/register", json={"email": "A@x.io", "password": PW, "display_name": "A"})
    assert r.status_code == 409


def test_AUTH1_instructor_signup_needs_code(env):
    r = env.client().post("/api/v1/auth/register", json={"email": "i@x.io", "password": PW, "display_name": "I", "role": "instructor"})
    assert r.status_code == 403


# ---------------------------------------------------------------- AUTH-2 / security
def test_AUTH2_cross_user_403(env):
    a, b = env.signup("a@x.io"), env.signup("b@x.io")
    rid = new_run(a)
    assert b.get(f"/api/v1/runs/{rid}/state").status_code == 403
    assert Driver(b, rid).cmd("advance_stage", to="STANDUP").status_code == 403
    assert b.get(f"/api/v1/runs/{rid}/debrief").status_code == 403
    assert a.get(f"/api/v1/runs/{rid}/state").status_code == 200


def test_AUTH2_unauthenticated_401(env):
    assert env.client().get("/api/v1/me").status_code == 401


def test_AUTH2_idle_and_absolute_timeout(env):
    c = env.signup("a@x.io")
    env.clock[0] += 29 * 60
    assert c.get("/api/v1/me").status_code == 200
    env.clock[0] += 31 * 60
    assert c.get("/api/v1/me").status_code == 401
    c = env.signup("b@x.io")
    for _ in range(9):  # keep active but hit the 8 h absolute limit
        env.clock[0] += 25 * 60
        if env.clock[0] > 1_000_000.0 + 8 * 3600 + 3000:
            break
        c.get("/api/v1/me")
    env.clock[0] += 8 * 3600
    assert c.get("/api/v1/me").status_code == 401


def test_AUTH2_logout_invalidates_server_side(env):
    c = env.signup("a@x.io")
    token = c.cookies.get("sid")
    assert c.post("/api/v1/auth/logout").status_code == 200
    c2 = env.client()
    c2.cookies.set("sid", token)
    assert c2.get("/api/v1/me").status_code == 401


def test_SEC_cookie_flags(env):
    env.client().post("/api/v1/auth/register", json={"email": "a@x.io", "password": PW, "display_name": "A"})
    r = env.client().post("/api/v1/auth/login", json={"email": "a@x.io", "password": PW})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie


def test_SEC_csrf_required_on_state_change(env):
    c = env.signup("a@x.io")
    rid = new_run(c)
    token = c.headers.pop("X-CSRF-Token")
    r = c.post(f"/api/v1/runs/{rid}/commands", json={"client_seq": 1, "type": "advance_stage", "payload": {"to": "STANDUP"}})
    assert r.status_code == 403 and r.json()["code"] == "CSRF_FAILED"
    c.headers["X-CSRF-Token"] = "wrong"
    assert c.post("/api/v1/runs").status_code == 403
    c.headers["X-CSRF-Token"] = token
    assert c.post("/api/v1/runs").status_code == 201


def test_SEC_bruteforce_lockout(tmp_path, content):
    e = Env(tmp_path, content, login_per_minute=5)
    e.client().post("/api/v1/auth/register", json={"email": "a@x.io", "password": PW, "display_name": "A"})
    c = e.client()
    codes = [c.post("/api/v1/auth/login", json={"email": "a@x.io", "password": "bad-password-0"}).status_code for _ in range(7)]
    assert codes[:5] == [401] * 5 and codes[5:] == [429, 429]
    assert c.post("/api/v1/auth/login", json={"email": "a@x.io", "password": PW}).status_code == 429  # even the right one
    e.clock[0] += 61
    assert c.post("/api/v1/auth/login", json={"email": "a@x.io", "password": PW}).status_code == 200


def test_SEC_xss_in_display_name_is_data_not_markup(env):
    c = env.signup("a@x.io", name="<script>alert(1)</script>")
    r = c.get("/api/v1/me")
    assert r.headers["content-type"] == "application/json" and r.json()["display_name"] == "<script>alert(1)</script>"
    assert "script-src 'self'" in r.headers["content-security-policy"] and r.headers["x-content-type-options"] == "nosniff"


def test_PRIV_consent_required_before_run(env):
    c = env.signup("a@x.io", consent=False)
    r = c.post("/api/v1/runs")
    assert r.status_code == 403 and r.json()["code"] == "CONSENT_REQUIRED"
    c.post("/api/v1/consent")
    assert c.post("/api/v1/runs").status_code == 201


# ---------------------------------------------------------------- commands and contract
def test_PILE2_illegal_command_http_and_no_events(env):
    c = env.signup("a@x.io")
    rid = new_run(c)
    n0 = sqlite3.connect(env.db).execute("select count(*) from run_events").fetchone()[0]
    r = Driver(c, rid).cmd("push")
    assert r.status_code == 409 and r.json()["code"] == "ILLEGAL_COMMAND"
    assert sqlite3.connect(env.db).execute("select count(*) from run_events").fetchone()[0] == n0


def test_SPRINT1_illegal_transition_http(env):
    c = env.signup("a@x.io")
    rid = new_run(c)
    r = Driver(c, rid).cmd("advance_stage", to="REVIEW")
    assert r.status_code == 409 and r.json()["code"] == "ILLEGAL_TRANSITION"


def test_cmd_idempotent_client_seq(env):
    c = env.signup("a@x.io")
    rid = new_run(c)
    d = Driver(c, rid)
    body = {"client_seq": 1, "type": "advance_stage", "payload": {"to": "STANDUP"}}
    r1 = c.post(f"/api/v1/runs/{rid}/commands", json=body)
    r2 = c.post(f"/api/v1/runs/{rid}/commands", json=body)
    assert r1.status_code == r2.status_code == 200 and r2.json()["replayed"] and r2.json()["seq"] == r1.json()["seq"]
    assert [e["type"] for e in r1.json()["events"]] == [e["type"] for e in r2.json()["events"]]
    bad = c.post(f"/api/v1/runs/{rid}/commands", json={**body, "type": "reply_standup", "payload": {"answer": "vague"}})
    assert bad.status_code == 409 and bad.json()["code"] == "DUPLICATE_SEQ_MISMATCH"


def test_validation_error_problem(env):
    c = env.signup("a@x.io")
    rid = new_run(c)
    r = c.post(f"/api/v1/runs/{rid}/commands", json={"type": "push"})
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"


def test_state_replay_rebuild_after_restart(tmp_path, content):
    e = Env(tmp_path, content)
    c = e.signup("a@x.io")
    rid = new_run(c)
    b = bot.play(11, content)
    Driver(c, rid).replay_bot(b)
    before = c.get(f"/api/v1/runs/{rid}/state").json()["state"]
    e2 = Env.__new__(Env)
    e2.__dict__.update(e.__dict__)
    e2.app = create_app(e.db, content, settings=e.settings, now=lambda: e.clock[0])  # fresh process, empty cache
    c2 = e2.client()
    c2.login("a@x.io")
    assert c2.get(f"/api/v1/runs/{rid}/state").json()["state"] == before


def test_run_events_append_only(env):
    c = env.signup("a@x.io")
    new_run(c)
    con = sqlite3.connect(env.db)
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("update run_events set type='x'")
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("delete from run_events")


def test_tick_clamped_and_scaled_http(env):
    c = env.signup("a@x.io")
    rid = new_run(c)
    d = Driver(c, rid)
    for cmd, p in (("advance_stage", {"to": "STANDUP"}), ("reply_standup", {"answer": "vague"}), ("advance_stage", {"to": "BUILD"})):
        assert d.cmd(cmd, **p).status_code == 200
    t0 = c.get(f"/api/v1/runs/{rid}/state").json()["state"]["clock_min"]
    c.post(f"/api/v1/runs/{rid}/tick", json={"real_ms": 10 ** 8})
    t1 = c.get(f"/api/v1/runs/{rid}/state").json()["state"]["clock_min"]
    assert round(t1 - t0, 1) == round(5 * 160 / 60, 1)


def test_state_since_and_no_answer_keys(env):
    c = env.signup("a@x.io")
    rid = new_run(c)
    d = Driver(c, rid)
    d.cmd("advance_stage", to="STANDUP")
    full = c.get(f"/api/v1/runs/{rid}/state").json()
    later = c.get(f"/api/v1/runs/{rid}/state", params={"since": full["seq"]}).json()
    assert full["events"] and later["events"] == []
    for key in ("hidden_bug", "correct_small_flaw", "security_hole", "bug_type"):
        assert key not in c.get(f"/api/v1/runs/{rid}/state").text


def test_public_events_hide_shipped_hole(env, content):
    c = env.signup("a@x.io")
    rid = new_run(c)
    b = bot.play(11, content, "reckless")
    Driver(c, rid).replay_bot(b)
    pushed = [e for e in c.get(f"/api/v1/runs/{rid}/state").json()["events"] if e["type"] == "pushed"]
    assert pushed and all(e["result"] == "pending" for e in pushed)


def test_bot_vs_api_same_final_meters(env, content):
    c = env.signup("a@x.io")
    rid = new_run(c)
    b = bot.play(11, content, "coach_delegate")  # same seed as the server picked
    Driver(c, rid).replay_bot(b)
    s = c.get(f"/api/v1/runs/{rid}/state").json()["state"]
    assert s["meters"] == b.s["meters"] and s["status"] == "ended"
    deb = c.get(f"/api/v1/runs/{rid}/debrief").json()
    assert deb["process_score"] == reducer.process_score(b.s, content) and deb["ending"] == b.s["ending"]


def test_END1_debrief_all_four_endings_http(env, content):
    c = env.signup("a@x.io")
    rid = new_run(c)
    assert c.get(f"/api/v1/runs/{rid}/debrief").status_code == 409
    Driver(c, rid).replay_bot(bot.play(11, content, "reckless"))
    d = c.get(f"/api/v1/runs/{rid}/debrief").json()
    assert d["ending"].startswith("lose") and {"rating", "cover", "process_score", "gap"} <= set(d)


def test_instructor_cannot_play(env):
    i = env.signup("i@x.io", role="instructor")
    assert i.post("/api/v1/runs").status_code == 403


# ---------------------------------------------------------------- ASSESS-1 and INSTR-1
def test_ASSESS1_pre_post_submit_and_gain(env, content):
    c = env.signup("a@x.io")
    qs = c.get("/api/v1/assessments/questions").json()["questions"]
    assert len(qs) == 10 and all("answer" not in q for q in qs)
    key = {q["id"]: q["answer"] for q in content.assessment["questions"]}
    r = c.post("/api/v1/assessments/pre", json={"answers": {k: 0 for k in key}})
    assert r.status_code == 200
    r2 = c.post("/api/v1/assessments/post", json={"answers": key})
    assert r2.json()["score"] == 10
    assert c.post("/api/v1/assessments/pre", json={"answers": key}).status_code == 409
    assert c.post("/api/v1/assessments/mid", json={"answers": key}).status_code == 404


def _cohort(env, name_i, emails):
    i = env.signup(f"{name_i}@x.io", role="instructor", name=name_i)
    code, cid = i.info["join_code"], i.info["cohort_id"]
    return i, cid, [env.signup(e, cohort_code=code, name=e.split("@")[0]) for e in emails]


def test_INSTR1_cohort_isolation(env):
    i1, c1, (s1,) = _cohort(env, "inst1", ["s1@x.io"])
    i2, c2, (s2,) = _cohort(env, "inst2", ["s2@x.io"])
    r1, r2 = new_run(s1), new_run(s2)
    assert i1.get(f"/api/v1/instructor/cohorts/{c1}/runs").status_code == 200
    assert i1.get(f"/api/v1/instructor/cohorts/{c2}/runs").status_code == 403
    assert i1.get(f"/api/v1/instructor/runs/{r2}/transcript").status_code == 403
    assert s1.get(f"/api/v1/instructor/cohorts/{c1}/runs").status_code == 403
    assert i1.get("/api/v1/instructor/runs/9999/transcript").status_code == 403


def test_INSTR1_transcript_list_and_open(env, content):
    i, cid, (s,) = _cohort(env, "inst1", ["s1@x.io"])
    rid = new_run(s)
    Driver(s, rid).replay_bot(bot.play(11, content, "coach_delegate"))
    key = {q["id"]: q["answer"] for q in content.assessment["questions"]}
    s.post("/api/v1/assessments/pre", json={"answers": {k: 0 for k in key}})
    s.post("/api/v1/assessments/post", json={"answers": key})
    rows = i.get(f"/api/v1/instructor/cohorts/{cid}/runs").json()["runs"]
    pre = sum(1 for v in key.values() if v == 0) / len(key)   # the pre-test answers 0 everywhere; the post-test has the key
    assert len(rows) == 1 and rows[0]["process_score"] > 0 and abs(rows[0]["gain"] - (1.0 - pre)) < 1e-9
    t = i.get(f"/api/v1/instructor/runs/{rid}/transcript").json()
    assert any(e["type"] == "pushed" for e in t["events"])
    assert any(e["type"] == "pushed" and e["result"] in ("clean", "acceptable", "buggy", "security_hole") for e in t["events"])


def test_perf_api_p95_150ms_no_model(env):
    c = env.signup("a@x.io")
    rid = new_run(c)
    times = []
    for _ in range(100):
        t0 = time.perf_counter()
        assert c.get(f"/api/v1/runs/{rid}/state").status_code == 200
        times.append(time.perf_counter() - t0)
    assert sorted(times)[94] < 0.15


def test_healthz_and_model_status(env):
    c = env.signup("a@x.io")
    assert env.client().get("/healthz").json() == {"ok": True}
    assert c.get("/api/v1/model/status").json()["enabled"] is False


def test_contract_openapi_matches_code():
    import sys
    from pathlib import Path
    import yaml
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tools"))
    from dump_openapi import spec
    committed = yaml.safe_load((root / "openapi.yaml").read_text(encoding="utf-8"))
    assert committed == yaml.safe_load(yaml.safe_dump(spec(), sort_keys=True)), "run: python tools/dump_openapi.py"
    for p in ("/api/v1/auth/register", "/api/v1/auth/login", "/api/v1/runs", "/api/v1/runs/{run_id}/commands",
              "/api/v1/runs/{run_id}/tick", "/api/v1/runs/{run_id}/debrief", "/api/v1/instructor/runs/{run_id}/transcript", "/healthz"):
        assert p in committed["paths"], p
