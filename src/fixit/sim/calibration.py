"""Measure THIS deployment so the simulation can model the real hosted setup, not only the paper's assumptions.

Authentication time: a real Argon2id verification of the app's own hasher. Sandbox time: the real ScrumScript interpreter running real tickets.
LLM time and slots: real calls to the AI server (when one is connected) and its real concurrency. Anything that cannot be measured keeps the
paper's value and is reported as such.
"""
from __future__ import annotations

import statistics
import time

from ..rules import content as content_mod
from .model import PAPER_DISTS, SimParams


def _tri(samples: list[float], floor: float = 1e-4) -> tuple[float, float, float]:
    """A triangular distribution from measurements: min, median as the mode, max (widened a little when they are equal)."""
    lo, mid, hi = min(samples), statistics.median(samples), max(samples)
    lo, hi = max(floor, lo), max(hi, mid * 1.05, lo + floor)
    return (round(lo, 6), round(min(max(mid, lo), hi), 6), round(hi, 6))


def measure_auth(hasher, n: int = 5) -> list[float]:
    h = hasher.hash("calibration-password-123")
    out = []
    for _ in range(n):
        t = time.perf_counter()
        hasher.verify(h, "calibration-password-123")
        out.append(time.perf_counter() - t)
    return out


def measure_sandbox(content, n: int = 40) -> list[float]:
    tickets = [t for t in content.tickets.values() if t.get("options")][:8]
    out = []
    for i in range(n):
        t = tickets[i % len(tickets)]
        start = time.perf_counter()
        content_mod.run_ticket(t, t["options"][0], content)
        out.append(time.perf_counter() - start)
    return out


def measure_llm(ai, n: int = 4) -> tuple[list[float], int] | None:
    """(call times in seconds, concurrency) from real calls to the AI server, or None when it is not connected."""
    if ai is None:
        return None
    try:
        st = ai.status()
        if not st.get("reachable"):
            return None
        conc = int((st.get("queue") or {}).get("concurrency", 1))
        schema = {"type": "object", "additionalProperties": False, "required": ["answer"], "properties": {"answer": {"type": "string"}}}
        times = []
        for _ in range(n):
            t = time.perf_counter()
            ai.generate([{"role": "system", "content": "Answer in one short sentence."}, {"role": "user", "content": "What is a Sprint in Scrum?"}], schema,
                        priority="interactive", max_tokens=60, temperature=0.4)
            times.append(time.perf_counter() - t)
        return times, conc
    except Exception:   # noqa: BLE001  (an unreachable AI just means the paper's LLM numbers stay)
        return None


def measure_deployment(content, hasher, ai) -> dict:
    """The "This deployment (measured)" preset: paper parameters with the measured service times and capacities put in."""
    dists = {k: tuple(v) for k, v in PAPER_DISTS.items()}
    measured, kept = {}, []
    a = measure_auth(hasher)
    dists["login_auth"] = _tri(a)
    measured["auth_verify_ms"] = {"min": round(min(a) * 1000, 1), "median": round(statistics.median(a) * 1000, 1), "max": round(max(a) * 1000, 1), "samples": len(a)}
    s = measure_sandbox(content)
    dists["sandbox"] = _tri(s, floor=1e-5)
    measured["sandbox_run_ms"] = {"min": round(min(s) * 1000, 3), "median": round(statistics.median(s) * 1000, 3), "max": round(max(s) * 1000, 3), "samples": len(s)}
    llm_slots = SimParams().llm_slots
    got = measure_llm(ai)
    if got:
        times, llm_slots = got
        dists["llm"] = _tri(times)
        dists["llm_e1"] = _tri([t * 0.8 for t in times])   # the paper's E1 effect: calls about 20% shorter
        measured["llm_call_s"] = {"min": round(min(times), 2), "median": round(statistics.median(times), 2), "max": round(max(times), 2), "samples": len(times), "concurrency": llm_slots}
    else:
        kept.append("llm")
    return {"id": "deployment", "name": "This deployment (measured)", "params": {"llm_slots": llm_slots, "sandbox_workers": 1, "auth_workers": 1,
            "dists": {k: list(v) for k, v in dists.items()}}, "measured": measured, "kept_from_paper": kept,
            "note": "Argon2id and the interpreter were timed here; the LLM was timed on the connected AI server" + ("" if got else " (none connected: the paper's LLM time is kept)")}
