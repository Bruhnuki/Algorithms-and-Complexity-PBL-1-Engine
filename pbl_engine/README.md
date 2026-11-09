# Fix it with Scrum: algorithm engine prototype (PBL Milestone 1)

Two engines behind one endpoint, `POST /api/v1/algorithm/solve`, selected by the `algorithm` field.

| Engine | `algorithm` value | Module |
|---|---|---|
| E1 Context window chaining: stage state machine + knapsack DP, with a bounded greedy fallback | `context_chaining` | `engine/context_chaining.py` |
| E2 Normalized learning gain (improvement + loss rules), bootstrap interval, saturating process score | `learning_gain` | `engine/learning_gain.py` |

Dispatcher, limits and error codes: `engine/solve.py`. Contracts: `schemas/*.schema.json` (JSON Schema 2020-12).

**E1 modes** (`input.mode`): `auto` (default) runs the exact DP when the estimated DP cells are <= 2,000,000, otherwise greedy;
`exact` and `greedy` force a mode. Greedy certificates carry `abs_gap_bound` with `OPT - V <= abs_gap_bound`.

## Run
```
python run_tests.py                          # dependency-free runner (19 tests); or: pip install pytest && pytest
python benchmark.py                          # Task 3 / Task 5 measurements (machine-dependent: re-run on your hardware)
python -m experiments.baseline_comparison    # DP vs recent-first vs density-greedy
python -m experiments.regime_sweep           # when does greedy stop being good enough? (item size vs budget)
```

## HTTP wrapper (sketch, not yet run in CI)
```python
# pip install fastapi uvicorn      ->  uvicorn app:app
from fastapi import FastAPI
from engine.solve import solve
app = FastAPI()

@app.post("/api/v1/algorithm/solve")
def solve_endpoint(request: dict):
    return solve(request)
```

## Notes
* `tests/mini_jsonschema.py` is a tiny offline validator so tests run without network access. In CI, use the `jsonschema` package.
* Timings in the report came from one development machine and vary by up to ~1.6x between runs; thresholds include headroom. Re-measure before submitting.
