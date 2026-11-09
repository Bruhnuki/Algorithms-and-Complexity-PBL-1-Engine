"""Shared helpers for API tests: app factory, user sign-up/login, and driving a run over HTTP."""
import httpx
from fastapi.testclient import TestClient

from fixit.api.app import Settings, create_app

PW = "correct-horse-battery"


class Env:
    def __init__(self, tmp_path, content, gateway=None, name="app.db", seed=11, **settings):
        self.clock = [1_000_000.0]
        self.db = str(tmp_path / name)
        opts = {"instructor_code": "inst-code", "login_per_minute": 100, "dialogue_inline": True, **settings}
        self.settings = Settings(**opts)
        self.app = create_app(self.db, content, gateway=gateway, settings=self.settings, now=lambda: self.clock[0],
                              seed_fn=lambda: seed)

    def client(self):
        c = TestClient(self.app, base_url="https://testserver")
        return c

    def signup(self, email, role="student", cohort_code=None, name="Stu", consent=True):
        c = self.client()
        body = {"email": email, "password": PW, "display_name": name, "role": role}
        if role == "instructor":
            body["instructor_code"] = "inst-code"
        if cohort_code:
            body["cohort_code"] = cohort_code
        r = c.post("/api/v1/auth/register", json=body)
        assert r.status_code == 201, r.text
        info = r.json()
        c.login(email)
        if consent and role == "student":
            assert c.post("/api/v1/consent").status_code == 200
        c.info = info
        return c


def _login(self, email, password=PW):
    r = self.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    self.headers["X-CSRF-Token"] = r.json()["csrf"]
    return r


TestClient.login = _login


def new_run(c):
    r = c.post("/api/v1/runs")
    assert r.status_code == 201, r.text
    return r.json()["id"]


class Driver:
    def __init__(self, c, run_id):
        self.c, self.run, self.seq = c, run_id, 0

    def cmd(self, typ, **payload):
        self.seq += 1
        return self.c.post(f"/api/v1/runs/{self.run}/commands", json={"client_seq": self.seq, "type": typ, "payload": payload})

    def replay_bot(self, bot):
        for cmd in bot.log:
            r = self.cmd(cmd["type"], **cmd["payload"])
            assert r.status_code == 200, (cmd, r.text)
        return r


def mock_client(handler):
    from fixit.gateway.gateway import HttpModelClient
    return HttpModelClient("http://mock", "mock-model", transport=httpx.MockTransport(handler))
