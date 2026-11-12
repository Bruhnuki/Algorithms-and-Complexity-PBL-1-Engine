"""Measure a model on the game's real generation tasks, through the real AI server.

  set AI_TOKEN / FIXIT_AI_TOKEN, start `python -m ai_server`, then:
  python tools/ai_bench.py --model qwen3.5:9b --scenarios 20 --challenges 20 --out bench_9b.json

Reports load time, VRAM, RAM, CPU/GPU use, latency, tokens/s, JSON validity, how many items passed the game's own validators (and why the rest
did not), plus the HTTP round trip to the server (run it from the game PC over Tailscale to get the network latency).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import psutil

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "src")]
from fixit.ai.client import AiClient   # noqa: E402
from fixit.ai.generator import Generator   # noqa: E402
from fixit.ai.library import Library   # noqa: E402
from fixit.rules import content as content_mod   # noqa: E402


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))] if xs else None


class Sampler(threading.Thread):
    """Every half second: GPU use and VRAM (nvidia-smi), CPU use, and the memory the model engine holds in RAM."""

    def __init__(self):
        super().__init__(daemon=True)
        self.stop_ev, self.gpu, self.vram, self.cpu, self.ram = threading.Event(), [], [], [], []

    def run(self):
        psutil.cpu_percent(None)
        while not self.stop_ev.wait(0.5):
            try:
                o = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5).stdout.split(",")
                self.gpu.append(float(o[0]))
                self.vram.append(float(o[1]))
            except Exception:   # noqa: BLE001
                pass
            self.cpu.append(psutil.cpu_percent(None))
            self.ram.append(sum(p.info["memory_info"].rss for p in psutil.process_iter(["name", "memory_info"]) if "ollama" in (p.info["name"] or "").lower()) / 2**20)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("FIXIT_AI_URL", "http://127.0.0.1:8765"))
    ap.add_argument("--token", default=os.environ.get("FIXIT_AI_TOKEN") or os.environ.get("AI_TOKEN", ""))
    ap.add_argument("--engine", default="http://127.0.0.1:11434", help="Ollama on this machine, for the cold-load and unload measurements")
    ap.add_argument("--model", default="qwen3.5:9b")
    ap.add_argument("--scenarios", type=int, default=20)
    ap.add_argument("--challenges", type=int, default=20)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    eng = httpx.Client(base_url=a.engine, timeout=300)
    for m in eng.get("/api/ps").json().get("models", []):   # only one primary model at a time
        eng.post("/api/generate", json={"model": m["name"], "keep_alive": 0})
    time.sleep(2)
    base_vram = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout.strip()
    base_ram = psutil.virtual_memory().used / 2**20
    t0 = time.time()
    r = eng.post("/api/generate", json={"model": a.model, "prompt": "ok", "stream": False, "keep_alive": "10m", "options": {"num_ctx": 4096, "num_predict": 1}, "think": False}).json()
    cold_s = time.time() - t0
    ps = next((m for m in eng.get("/api/ps").json()["models"] if m["name"] == a.model), {})
    result = {"model": a.model, "cold_load_s": round(cold_s, 2), "engine_load_ms": round(r.get("load_duration", 0) / 1e6), "vram_model_mb": round(ps.get("size_vram", 0) / 2**20),
              "vram_gpu_before_mb": float(base_vram), "ram_system_before_mb": round(base_ram)}
    client = AiClient(a.url, a.token, timeout_s=240, check_address=False)   # an operator tool: it may be pointed at this PC to measure
    rtt = []
    for _ in range(20):
        t = time.perf_counter()
        client.http.get("/healthz")
        rtt.append((time.perf_counter() - t) * 1000)
    result["http_rtt_ms"] = {"p50": round(statistics.median(rtt), 1), "p95": round(pct(rtt, 0.95), 1)}
    content = content_mod.load()
    gen = Generator(client, content, Library(Path(os.environ.get("TEMP", ".")) / "ai_bench_lib"), model=a.model)
    sampler = Sampler()
    sampler.start()
    samples, per_kind = [], {}
    t_all = time.time()
    for kind, n in (("scenario", a.scenarios), ("challenge", a.challenges)):
        before = (gen.stats["attempts"], gen.stats["accepted"], gen.stats["json_invalid"], gen.stats["errors"], dict(gen.stats["rejected"]), len(gen.stats["latency_ms"]))
        times, ok = [], 0
        for i in range(n):
            t = time.perf_counter()
            item, why = gen.make(kind, seed=1000 + i, save=False)
            times.append(time.perf_counter() - t)
            ok += item is not None
            if item and len(samples) < 40:
                samples.append(item)
        rej = {k: v - before[4].get(k, 0) for k, v in gen.stats["rejected"].items() if v - before[4].get(k, 0)}
        per_kind[kind] = {"requests": n, "accepted": ok, "accept_rate": round(ok / n, 3) if n else None, "json_invalid": gen.stats["json_invalid"] - before[2],
                          "server_errors": gen.stats["errors"] - before[3], "rejected_by": rej, "item_time_s": {"median": round(statistics.median(times), 2), "p95": round(pct(times, 0.95), 2)} if times else None}
    sampler.stop_ev.set()
    sampler.join()
    lat, tps, toks = gen.stats["latency_ms"], [x for x in gen.stats["tokens_per_s"] if x], gen.stats["completion_tokens"]
    avg = lambda xs: round(statistics.mean(xs), 1) if xs else None   # noqa: E731
    result.update({"wall_s": round(time.time() - t_all, 1), "model_calls": len(lat), "per_kind": per_kind,
                   "call_latency_ms": {"median": round(statistics.median(lat)), "p95": round(pct(lat, 0.95))} if lat else None,
                   "tokens_per_s": {"median": round(statistics.median(tps), 1), "min": round(min(tps), 1)} if tps else None, "tokens_per_call_avg": avg(toks),
                   "vram_used_mb": {"max": max(sampler.vram) if sampler.vram else None}, "gpu_util_pct": {"mean": avg(sampler.gpu), "max": max(sampler.gpu) if sampler.gpu else None},
                   "cpu_util_pct": {"mean": avg(sampler.cpu), "max": max(sampler.cpu) if sampler.cpu else None},
                   "engine_ram_mb": {"max": round(max(sampler.ram)) if sampler.ram else None}, "system_ram_after_mb": round(psutil.virtual_memory().used / 2**20),
                   "accepted_total": sum(k["accepted"] for k in per_kind.values()), "requests_total": sum(k["requests"] for k in per_kind.values())})
    out = {"summary": result, "samples": samples}
    print(json.dumps(result, indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
