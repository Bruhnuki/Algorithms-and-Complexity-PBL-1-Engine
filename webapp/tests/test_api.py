import copy

import pytest
from fastapi.testclient import TestClient

from main import app  # importing main puts pbl_engine on sys.path
import engine.solve as engine_solve  # noqa: E402  (must come after main)

client = TestClient(app)
URL = "/api/v1/algorithm/solve"

# Same request shapes as the demo scripts in README-pbl-engine.md.
CWC_FSM = {
    "job_id": "context-demo-01",
    "algorithm": "context_chaining",
    "input": {
        "current_stage": "BUILD",
        "token_budget": 1000,
        "mode": "auto",
        "segments": [
            {"id": "planning-goal", "tokens": 180, "relevance": 0.95, "stage": "PLANNING", "pinned": True},
            {"id": "standup-update", "tokens": 220, "relevance": 0.75, "stage": "STANDUP"},
            {"id": "build-decision", "tokens": 300, "relevance": 0.90, "stage": "BUILD"},
            {"id": "old-planning-note", "tokens": 250, "relevance": 0.40, "stage": "PLANNING"},
            {"id": "review-feedback", "tokens": 200, "relevance": 0.85, "stage": "REVIEW"},
        ],
    },
}
NLG_SPA = {
    "job_id": "cohort-demo-10",
    "algorithm": "learning_gain",
    "input": {
        "max_score": 100,
        "students": [
            {"id": "S01", "pre": 45, "post": 75}, {"id": "S02", "pre": 50, "post": 80},
            {"id": "S03", "pre": 60, "post": 85}, {"id": "S04", "pre": 40, "post": 70},
            {"id": "S05", "pre": 55, "post": 78}, {"id": "S06", "pre": 35, "post": 65},
            {"id": "S07", "pre": 70, "post": 90}, {"id": "S08", "pre": 48, "post": 76},
            {"id": "S09", "pre": 52, "post": 82}, {"id": "S10", "pre": 42, "post": 72},
        ],
        "bootstrap_B": 1000,
        "seed": 7,
    },
}


def without_runtime(resp):
    resp = copy.deepcopy(resp)
    resp["metrics"].pop("runtime_ms")
    return resp


def test_index_page_is_served():
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "CWC-FSM" in r.text and "NLG-SPA" in r.text
    assert client.get("/static/app.js").status_code == 200


def test_cwc_fsm_path_returns_solve_output():
    r = client.post(URL, json=CWC_FSM)
    body = r.json()
    assert r.status_code == 200 and body["status"] == "ok"
    assert body["algorithm"] == "context_chaining" and body["job_id"] == "context-demo-01"
    assert "planning-goal" in body["result"]["selected_segment_ids"]          # pinned
    assert "review-feedback" not in body["result"]["selected_segment_ids"]    # future stage
    assert body["result"]["tokens_used"] <= 1000
    assert without_runtime(body) == without_runtime(engine_solve.solve(copy.deepcopy(CWC_FSM)))


def test_nlg_spa_path_returns_solve_output():
    r = client.post(URL, json=NLG_SPA)
    body = r.json()
    assert r.status_code == 200 and body["status"] == "ok"
    assert body["algorithm"] == "learning_gain" and body["job_id"] == "cohort-demo-10"
    assert body["result"]["cohort"]["n_students"] == 10
    assert without_runtime(body) == without_runtime(engine_solve.solve(copy.deepcopy(NLG_SPA)))


def with_input(base, **changes):
    req = copy.deepcopy(base)
    req["input"].update(changes)
    return req


@pytest.mark.parametrize("request_body, code, http_status", [
    ({"job_id": "x", "algorithm": "nope", "input": {}}, "UNKNOWN_ALGORITHM", 400),
    ({"job_id": "x", "algorithm": "context_chaining"}, "MALFORMED_REQUEST", 400),
    (["not", "an", "object"], "MALFORMED_REQUEST", 400),
    (with_input(CWC_FSM, current_stage="NOPE"), "VALIDATION_ERROR", 422),
    (with_input(NLG_SPA, max_score=10), "VALIDATION_ERROR", 422),
    (with_input(CWC_FSM, token_budget=100), "INFEASIBLE", 422),
    (with_input(CWC_FSM, advance_to="PLANNING"), "ILLEGAL_TRANSITION", 409),
    (with_input(CWC_FSM, token_budget=10**6), "LIMIT_EXCEEDED", 413),
    (with_input(NLG_SPA, bootstrap_B=10), "LIMIT_EXCEEDED", 413),
])
def test_engine_errors_map_to_http_status(request_body, code, http_status):
    r = client.post(URL, json=request_body)
    assert r.status_code == http_status
    assert r.json()["status"] == "error" and r.json()["error"]["code"] == code


def test_internal_error_maps_to_500(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("boom")
    monkeypatch.setattr(engine_solve, "select_context", boom)
    r = client.post(URL, json=CWC_FSM)
    assert r.status_code == 500 and r.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "boom" not in r.text


def test_non_finite_result_returns_json_500():
    req = copy.deepcopy(CWC_FSM)
    for seg in req["input"]["segments"]:
        seg["relevance"] = 1e308   # finite input, but the selected sum overflows to Infinity
    r = client.post(URL, json=req)
    assert r.status_code == 500
    body = r.json()
    assert body["status"] == "error" and body["error"]["code"] == "INTERNAL_ERROR"
    assert body["job_id"] == "context-demo-01" and "runtime_ms" in body["metrics"]


@pytest.mark.parametrize("raw", ["{not json", '{"job_id": NaN}', ""])
def test_invalid_json_body_returns_400(raw):
    r = client.post(URL, content=raw, headers={"Content-Type": "application/json"})
    assert r.status_code == 400 and "detail" in r.json()
