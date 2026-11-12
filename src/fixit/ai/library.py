"""The on-disk library of validated, AI-written items. Append-only, so a run that froze a list of ids can always be replayed."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from ..rules.content import Content, ROOT


def default_dir() -> Path:
    return Path(os.environ.get("FIXIT_GENERATED_DIR") or ROOT / "generated")


class Library:
    def __init__(self, directory: Path | None = None):
        self.dir = Path(directory) if directory else default_dir()
        self._lock = threading.Lock()

    def _files(self, sub: str):
        return sorted((self.dir / sub).glob("*.json")) if (self.dir / sub).exists() else []

    def help_items(self) -> list[dict]:
        return [json.loads(p.read_text(encoding="utf-8")) for p in self._files("help")]

    def count(self) -> dict[str, int]:
        c = {"scenario": 0, "challenge": 0}
        for h in self.help_items():
            c[h["type"]] += 1
        return c

    def texts(self) -> dict[str, list[str]]:
        """Titles and text of what exists (authored included), so the generator can avoid repeating itself."""
        out = {"scenario": [], "challenge": [], "quiz": [b["scene"] + " " + b["question"] + " " + " ".join(c["text"] for c in b["choices"]) for b in self.beat_items()]}
        for h in self.help_items():
            out[h["type"]].append(" ".join([h["title"], *(h.get("prompts") or {}).values(), *(a["text"] for a in h.get("answers", []))]) if h["type"] == "scenario" else h["title"])
        return out

    def _write(self, sub: str, d: dict) -> None:
        (self.dir / sub).mkdir(parents=True, exist_ok=True)
        tmp = self.dir / sub / f"{d['id']}.tmp"
        tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
        tmp.replace(self.dir / sub / f"{d['id']}.json")   # atomic: a reader never sees half an item

    def add(self, help_def: dict | None, ticket: dict | None = None) -> None:
        with self._lock:
            for sub, d in (("tickets", ticket), ("help", help_def)):   # the ticket first, so a help request never points at nothing
                if d:
                    self._write(sub, d)

    def add_beat(self, beat: dict) -> None:
        with self._lock:
            self._write("beats", beat)

    def add_pack(self, pack: dict, tickets: list[dict]) -> None:
        """A whole AI-written project. Its tickets go first, so the pack never points at something that is not there yet."""
        with self._lock:
            for t in tickets:
                self._write("tickets", {**t, "pack_only": True})
            self._write("projects", pack)

    def beat_items(self) -> list[dict]:
        return [json.loads(p.read_text(encoding="utf-8")) for p in self._files("beats")]

    def pack_items(self) -> list[dict]:
        return [json.loads(p.read_text(encoding="utf-8")) for p in self._files("projects")]

    def audit(self, kind: str, reason: str, raw: dict | None) -> None:
        """Rejected output goes to a small log for review (never into the game). Rotated so it cannot grow without bound."""
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            f = self.dir / "rejected.jsonl"
            if f.exists() and f.stat().st_size > 1_000_000:
                f.replace(self.dir / "rejected.old.jsonl")
            with self._lock, f.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"t": round(time.time()), "kind": kind, "reason": reason, "raw": raw}, ensure_ascii=True) + chr(10))
        except OSError:
            pass   # the audit log must never break generation

    def merge_into(self, content: Content) -> int:
        """Add anything new to the in-memory content (dicts only grow). Returns how many items were added."""
        n = 0
        with self._lock:
            for p in self._files("tickets"):
                t = json.loads(p.read_text(encoding="utf-8"))
                content.tickets.setdefault(t["id"], t)
            for p in self._files("help"):
                h = json.loads(p.read_text(encoding="utf-8"))
                if h["id"] not in content.help and (h["type"] == "scenario" or h["ticket"] in content.tickets):
                    content.help[h["id"]] = h
                    n += 1
            for p in self._files("beats"):
                b = json.loads(p.read_text(encoding="utf-8"))
                if b["id"] not in content.beats:
                    content.beats[b["id"]] = b
                    n += 1
            from .pack import merge_guide
            for p in self._files("projects"):
                pk = json.loads(p.read_text(encoding="utf-8"))
                needed = [t for sp in pk["sprints"].values() for t in sp["tickets"]] + pk["hard_pool"]
                if pk["id"] not in content.packs and all(t in content.tickets for t in needed):
                    content.packs[pk["id"]] = merge_guide(content.guide, pk)
                    n += 1
        return n

    def ids(self, content: Content) -> list[str]:
        """What a new run may be dealt: every generated help request currently in the content."""
        return sorted([h for h, d in content.help.items() if d.get("generated")] + [b for b in content.beats]
                      + [t for t, d in content.tickets.items() if d.get("generated") and not d.get("pack_only")])
