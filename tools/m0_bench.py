"""M0 model benchmark against a running llama-server. Not run in CI (needs the GPU box).

  python tools/m0_bench.py --url http://127.0.0.1:8080 --model gpt-oss-20b --n 200 --conc 1 4 8

Prints tokens-agnostic latency p50/p95, JSON-valid rate and asserts the M0 gate (p50 < 3 s, p95 < 8 s, 100% valid).
Record VRAM free separately with `nvidia-smi` while this runs (gate: >= 1 GB free).
"""
import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fixit.gateway.gateway import Gateway, HttpModelClient, Request  # noqa: E402
from fixit.rules import content as cm  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--model", default="model")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--conc", type=int, nargs="+", default=[1, 4, 8])
    a = ap.parse_args()
    c = cm.get()
    gw = Gateway(c, HttpModelClient(a.url, a.model), slots=4, quota_per_min=10 ** 6)
    memory = [{"id": f"m{i}", "text": "The player gave a vague answer about a ticket. " * 8, "seq": i} for i in range(60)]
    ok_all = True
    for conc in a.conc:
        def one(i):
            line = gw.generate(Request("standup_question", ["po", "dev1", "dev2"][i % 3], {"ticket_title": "Coupon discount is wrong"}, memory, "BUILD", 1, i, f"u{i % conc}"))
            return line
        t0 = time.time()
        with ThreadPoolExecutor(conc) as ex:
            lines = list(ex.map(one, range(a.n)))
        lat = sorted(l.latency_ms for l in lines if l.source == "llm")
        valid = sum(l.source == "llm" for l in lines) / len(lines)
        p = lambda q: lat[int(len(lat) * q) - 1] if lat else None  # noqa: E731
        print(json.dumps({"conc": conc, "n": a.n, "valid_rate": valid, "p50_ms": p(0.5), "p95_ms": p(0.95),
                          "mean_ms": statistics.fmean(lat) if lat else None, "wall_s": round(time.time() - t0, 1)}))
        ok = valid == 1.0 and lat and p(0.5) < 3000 and p(0.95) < 8000
        ok_all &= bool(ok)
    print("M0 GATE", "PASS" if ok_all else "FAIL")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
