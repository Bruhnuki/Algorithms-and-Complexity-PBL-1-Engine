"""FastAPI web layer for the AI-Scrum algorithm engines.

Wraps the existing `solve()` dispatcher from pbl_engine/engine/solve.py without changing it.
"""
import json
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

WEBAPP_DIR = Path(__file__).resolve().parent
ENGINE_DIR = WEBAPP_DIR.parent / "pbl_engine"
STATIC_DIR = WEBAPP_DIR / "static"

# pbl_engine uses top-level imports (`engine.solve`), so its folder must be on sys.path.
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from engine.solve import solve  # noqa: E402

ERROR_STATUS = {
    "MALFORMED_REQUEST": 400,
    "UNKNOWN_ALGORITHM": 400,
    "VALIDATION_ERROR": 422,
    "INFEASIBLE": 422,
    "ILLEGAL_TRANSITION": 409,
    "LIMIT_EXCEEDED": 413,
    "INTERNAL_ERROR": 500,
}

app = FastAPI(title="AI-Scrum Algorithm Engine")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _reject_constant(name):
    raise ValueError(f"{name} is not valid JSON")


def ensure_json_encodable(response: dict) -> dict:
    """Turn a result with Infinity/NaN (e.g. huge relevance sums) into a JSON-safe INTERNAL_ERROR."""
    try:
        json.dumps(response, allow_nan=False)
        return response
    except ValueError:
        return {
            "job_id": response.get("job_id"),
            "algorithm": response.get("algorithm"),
            "engine_version": response.get("engine_version"),
            "status": "error",
            "error": {"code": "INTERNAL_ERROR",
                      "message": "engine result contains non-finite numbers that cannot be encoded as JSON"},
            "metrics": response.get("metrics", {}),
        }


def http_status_for(response: dict) -> int:
    if response.get("status") == "ok":
        return 200
    return ERROR_STATUS.get(response.get("error", {}).get("code"), 500)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/v1/algorithm/solve")
async def solve_endpoint(request: Request):
    body = await request.body()
    try:
        payload = json.loads(body, parse_constant=_reject_constant)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"detail": f"Request body is not valid JSON: {e}"})
    # solve() is CPU-bound; run it off the event loop so other requests are not blocked.
    response = ensure_json_encodable(await run_in_threadpool(solve, payload))
    return JSONResponse(status_code=http_status_for(response), content=response)
