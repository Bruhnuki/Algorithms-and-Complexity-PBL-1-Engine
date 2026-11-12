"""The AlgoCom engines (the `pbl_engine` package, from Algorithms-and-Complexity-PBL-1-Engine) wired into the game, unchanged.

`pbl_engine` sits at the repository root. This module only makes it importable wherever the server starts from and keeps a short
log of the real engine calls the running game makes, so the admin Engines tab can show them live.
"""
from __future__ import annotations

import sys
import threading
import time
from collections import deque
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.append(str(_ROOT))

from pbl_engine.engine import context_chaining as cc   # noqa: E402  (E1)
from pbl_engine.engine import learning_gain as lg      # noqa: E402  (E2)
from pbl_engine.engine import solve as solver          # noqa: E402  (POST /api/v1/algorithm/solve)

_LOG: deque = deque(maxlen=300)
_LOCK = threading.Lock()
_COUNT = [0]


def record(engine: str, op: str, started: float, ms: float | None = None, **info) -> dict:
    """Note one engine call (started = time.perf_counter() before it ran, or pass the measured `ms`). Returns the entry."""
    with _LOCK:
        _COUNT[0] += 1
        entry = {"n": _COUNT[0], "t": time.time(), "engine": engine, "op": op, "ms": round(ms if ms is not None else (time.perf_counter() - started) * 1000, 3), **info}
        _LOG.append(entry)
    return entry


def feed(since: int = 0) -> dict:
    """Calls after number `since`, plus totals per engine over what the log still holds."""
    with _LOCK:
        calls, total = [c for c in _LOG if c["n"] > since], _COUNT[0]
        held = list(_LOG)
    summary = {}
    for e in ("E1", "E2"):
        ms = [c["ms"] for c in held if c["engine"] == e]
        summary[e] = {"calls": len(ms), "avg_ms": round(sum(ms) / len(ms), 3) if ms else None, "max_ms": max(ms) if ms else None}
    return {"calls": calls[-100:], "total": total, "summary": summary}
