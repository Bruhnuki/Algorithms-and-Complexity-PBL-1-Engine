"""CI content gate: schema validation plus golden outputs. python tools/validate_content.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fixit.rules import content  # noqa: E402

c = content.load()
for t in c.tickets.values():
    assert [o["effect"] for o in t["options"]].count("correct") == 1, t["id"]
    for o in t["options"]:
        runs = content.run_ticket(t, o, c)
        got = "error" if any(r["error"] for r in runs) else "pass" if all(r["pass"] for r in runs) else "fail"
        assert got == o["run_outcome"], (t["id"], o["id"], got)
print("content ok:", len(c.tickets), "tickets,", len(c.tutorials), "tutorials,", len(c.teammates), "teammates")
