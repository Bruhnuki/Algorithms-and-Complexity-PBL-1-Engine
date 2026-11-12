"""Fill the AI library ahead of time (before a class), so the game never waits on the model.

  set FIXIT_AI_URL=http://<ai-pc-tailscale-name>:8765   set FIXIT_AI_TOKEN=<token>
  python tools/ai_generate.py --scenarios 30 --challenges 15
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "src")]
from fixit.ai.client import AiClient   # noqa: E402
from fixit.ai.generator import Generator   # noqa: E402
from fixit.ai.library import Library   # noqa: E402
from fixit.rules import content as content_mod   # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=int, default=30, help="target number of AI scenarios in the library")
    ap.add_argument("--challenges", type=int, default=15, help="target number of AI coding challenges in the library")
    ap.add_argument("--quizzes", type=int, default=0, help="target number of AI-written Scrum quiz questions in the library")
    ap.add_argument("--projects", type=int, default=0, help="how many complete AI-written projects to have per level (2 and 3); each takes about 3 minutes")
    ap.add_argument("--max-attempts", type=int, default=200)
    a = ap.parse_args()
    client = AiClient.from_env()
    if client is None:
        print("Set FIXIT_AI_URL and FIXIT_AI_TOKEN first.")
        return 2
    lib, content = Library(), content_mod.load()
    lib.merge_into(content)
    gen = Generator(client, content, lib)
    targets = {"scenario": a.scenarios, "challenge": a.challenges, **({"quiz": a.quizzes} if a.quizzes else {})}
    for _ in range(a.max_attempts):
        have = {**lib.count(), "quiz": len(lib.beat_items())}
        need = [k for k in targets if have[k] < targets[k]]
        if not need:
            break
        kind = min(need, key=lambda k: have[k] / targets[k])
        item, why = gen.make(kind)
        print(f"{kind:9} {'+ ' + item['title'] if item else '- ' + why}   [{lib.count()['scenario']} scenarios, {lib.count()['challenge']} challenges, {len(lib.beat_items())} questions]")
        if why.startswith("ai_"):
            print("The AI server is not available; stopping. Items already made are kept.")
            return 1
    if a.projects:
        from fixit.ai.pack import PackBuilder
        builder = PackBuilder(gen, lib, content)
        for n in (2, 3):
            while sum(1 for g in content.packs.values() if g["project_n"] == n) < a.projects:
                pack, why = builder.build(n, seed=int(__import__("time").time()) % 2**20, progress=lambda m, t, st: print(f"  project {n}: {m}/{t} {st}", end=chr(13)))
                print(f"project {n}: " + (f"+ {pack['title']}" if pack else f"- {why}"))
                if not pack:
                    return 1
    print(dict(gen.stats["rejected"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
