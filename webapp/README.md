# AI-Scrum web app (Phase 1)

A FastAPI wrapper around the existing `solve()` function in `pbl_engine/engine/solve.py`.
`pbl_engine/` is not modified; `main.py` adds that folder to `sys.path` and imports `engine.solve`.

## Start the app
Run these from the repository root (the folder that contains `pbl_engine/` and `webapp/`):

```bash
python -m venv .venv
# Windows (PowerShell):  .venv\Scripts\Activate.ps1
# macOS / Linux:         source .venv/bin/activate
pip install -r webapp/requirements.txt
uvicorn main:app --app-dir webapp --reload
```

Open http://127.0.0.1:8000 in a browser. Interactive API docs: http://127.0.0.1:8000/docs

## API
`POST /api/v1/algorithm/solve` accepts the same JSON request as `solve()` and returns its response unchanged.
Only the HTTP status code is added:

| `status` / `error.code` | HTTP status |
|---|---|
| `ok` | 200 |
| `MALFORMED_REQUEST`, `UNKNOWN_ALGORITHM` | 400 |
| `VALIDATION_ERROR`, `INFEASIBLE` | 422 |
| `ILLEGAL_TRANSITION` | 409 |
| `LIMIT_EXCEEDED` | 413 |
| `INTERNAL_ERROR` | 500 |

A body that is not valid JSON (including `NaN`/`Infinity`) never reaches `solve()` and returns 400 with `{"detail": "..."}`.

## Tests
```bash
python -m pytest webapp/tests          # API tests (from the repository root)
cd pbl_engine && python run_tests.py   # existing 19 algorithm tests
```
