"""Content pack loader: JSON/YAML files validated by JSON Schema. Content is data."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema
import yaml

from . import interp

ROOT = Path(__file__).resolve().parents[3] / "content"
EFFECTS = ("correct", "correct_small_flaw", "crashes", "wrong_hidden", "security_hole")


@dataclass(frozen=True)
class Content:
    balance: dict
    tickets: dict
    tutorials: dict
    teammates: dict
    assessment: dict
    version: str = "content-1"
    guide: dict = field(default_factory=dict)   # guided Scrum scenes (content/scrum_guide.json)

    @property
    def allowed(self) -> set[str]:
        return set(self.balance["allowed_keywords"])


def _json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def source_with(ticket: dict, option: dict | None) -> str:
    """Ticket source with the option's line substituted at the buggy/blank line."""
    lines = list(ticket["source"])
    idx = ticket.get("buggy_line") or ticket.get("blank_line")
    if option is not None:
        lines[idx - 1] = option["text"]
    return "\n".join(lines)


def run_ticket(ticket: dict, option: dict | None, content: Content) -> list[dict]:
    return interp.run_examples(source_with(ticket, option), ticket["examples"], ticket["params"],
                               allowed=content.allowed, step_limit=content.balance["interpreter"]["step_limit"])


def load(root: Path = ROOT) -> Content:
    schemas = {k: _json(root / "schemas" / f"{k}.schema.json") for k in ("ticket", "tutorial", "teammate")}
    def many(folder, schema):
        out = {}
        for p in sorted((root / folder).glob("*.json")):
            d = _json(p)
            jsonschema.validate(d, schemas[schema])
            out[d["id"]] = d
        return out
    guide = {}
    if (root / "scrum_guide.json").exists():
        guide = _json(root / "scrum_guide.json")
        jsonschema.validate(guide, _json(root / "schemas" / "guide.schema.json"))
    return Content(
        balance=yaml.safe_load((root / "balance.yaml").read_text(encoding="utf-8")),
        tickets=many("tickets", "ticket"), tutorials=many("tutorials", "tutorial"),
        teammates=many("teammates", "teammate"), assessment=_json(root / "assessment.json"), guide=guide)


_cache: Content | None = None


def get() -> Content:
    global _cache
    if _cache is None:
        _cache = load()
    return _cache
