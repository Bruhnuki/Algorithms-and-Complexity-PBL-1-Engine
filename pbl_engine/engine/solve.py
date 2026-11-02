"""Single entry point mirroring POST /api/v1/algorithm/solve.

One endpoint, two engines, selected by the `algorithm` discriminator field.
"""
import time

from .context_chaining import (IllegalTransitionError, InfeasibleError, Segment,
                               advance, select_context)
from .learning_gain import cohort_summary, process_summary

ENGINE_VERSION = "1.1.0"
LIMITS = {
    "max_segments": 2000,
    "max_budget": 32000,
    "max_students": 10000,
    "min_bootstrap": 100,
    "max_bootstrap": 10000,
    "max_bootstrap_draws": 20_000_000,
    "max_events": 100000,
    "max_categories": 32,
}


class LimitExceeded(ValueError):
    """Request is well-formed but larger than the engine's resource limits."""


def _check(cond, msg):
    if not cond:
        raise LimitExceeded(msg)


def _run_context_chaining(data):
    raw = data["segments"]
    _check(len(raw) <= LIMITS["max_segments"], "too many segments")
    _check(data["token_budget"] <= LIMITS["max_budget"], "token_budget too large")
    stage = data["current_stage"]
    if data.get("advance_to") is not None:
        stage = advance(stage, data["advance_to"])
    segs = [Segment(id=s["id"], tokens=s["tokens"], relevance=s["relevance"],
                    stage=s["stage"], pinned=s.get("pinned", False)) for s in raw]
    result = select_context(segs, data["token_budget"], stage, mode=data.get("mode", "auto"))
    result["stage"] = stage
    return result, {"dp_cells": result["dp_cells"]}


def _run_learning_gain(data):
    students = data["students"]
    B = data.get("bootstrap_B", 1000)
    _check(len(students) <= LIMITS["max_students"], "too many students")
    _check(LIMITS["min_bootstrap"] <= B <= LIMITS["max_bootstrap"], "bootstrap_B out of range")
    _check(B * len(students) <= LIMITS["max_bootstrap_draws"],
           "bootstrap_B * n_students exceeds the synchronous draw limit")
    result = {"cohort": cohort_summary(students, data["max_score"], B, seed=data.get("seed", 0))}
    metrics = {"bootstrap_draws": B * max(1, len(students))}
    pe = data.get("process_events")
    if pe is not None:
        _check(len(pe["categories"]) <= LIMITS["max_categories"], "too many categories")
        _check(len(pe["events"]) <= LIMITS["max_events"], "too many events")
        result["process"] = process_summary(pe["categories"], pe["events"])
        metrics["events_processed"] = len(pe["events"])
    return result, metrics


def solve(request: dict) -> dict:
    start = time.perf_counter()
    out = {"job_id": None, "algorithm": None, "engine_version": ENGINE_VERSION}
    metrics = {}
    try:
        if not isinstance(request, dict):
            raise TypeError("request must be a JSON object")
        out["job_id"] = request.get("job_id")
        out["algorithm"] = request.get("algorithm")
        algo, data = request["algorithm"], request["input"]
        if not isinstance(data, dict):
            raise TypeError("input must be an object")
        if algo == "context_chaining":
            result, metrics = _run_context_chaining(data)
        elif algo == "learning_gain":
            result, metrics = _run_learning_gain(data)
        else:
            raise KeyError("__unknown_algorithm__")
        out.update(status="ok", result=result)
    except KeyError as e:
        if "__unknown_algorithm__" in str(e):
            out.update(status="error", error={"code": "UNKNOWN_ALGORITHM",
                                              "message": f"unknown algorithm: {out['algorithm']!r}"})
        else:
            out.update(status="error", error={"code": "MALFORMED_REQUEST",
                                              "message": f"missing field {e}"})
    except TypeError as e:
        out.update(status="error", error={"code": "MALFORMED_REQUEST", "message": str(e)})
    except LimitExceeded as e:
        out.update(status="error", error={"code": "LIMIT_EXCEEDED", "message": str(e)})
    except InfeasibleError as e:
        out.update(status="error", error={"code": "INFEASIBLE", "message": str(e)})
    except IllegalTransitionError as e:
        out.update(status="error", error={"code": "ILLEGAL_TRANSITION", "message": str(e)})
    except ValueError as e:
        out.update(status="error", error={"code": "VALIDATION_ERROR", "message": str(e)})
    except Exception:  # never leak a stack trace or crash the host service
        out.update(status="error", error={"code": "INTERNAL_ERROR",
                                          "message": "internal error; see server logs"})
    metrics["runtime_ms"] = round((time.perf_counter() - start) * 1000, 3)
    out["metrics"] = metrics
    return out
