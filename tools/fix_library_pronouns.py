"""One-off cleanup: rewrite pronouns in AI-written library items written before the rule "Marlo he, Ines she, Tobi he".
Only text changes (never ids or numbers), so runs that already used an item replay exactly the same.   python tools/fix_library_pronouns.py [--dry]"""
import json
import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "src")]
from fixit.ai.guardrails import fix_pronouns, wrong_pronouns   # noqa: E402
from fixit.ai.library import default_dir   # noqa: E402


def walk(x, hits):
    if isinstance(x, str):
        if wrong_pronouns(x):
            hits.append(x)
            return fix_pronouns(x)
        return x
    if isinstance(x, list):
        return [walk(v, hits) for v in x]
    if isinstance(x, dict):
        return {k: walk(v, hits) for k, v in x.items()}
    return x


def main() -> int:
    dry, files, fixed = "--dry" in sys.argv, 0, 0
    for p in sorted(default_dir().glob("*/*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        hits: list[str] = []
        new = walk(d, hits)
        if hits:
            files += 1
            fixed += len(hits)
            print(f"{p.parent.name}/{p.name}: {len(hits)} text(s)")
            if not dry:
                p.write_text(json.dumps(new, indent=1), encoding="utf-8")
    print(f"{fixed} texts in {files} files " + ("would be fixed (dry run)" if dry else "fixed"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
