import copy
import dataclasses

import pytest

from fixit.rules import content as content_mod, reducer


def mvp_content():
    """The original MVP game: experimental mechanics switched off. The M1-M5 tests check it is unchanged."""
    c = content_mod.get()
    bal = copy.deepcopy(c.balance)
    bal["experimental"]["enabled"] = False
    return dataclasses.replace(c, balance=bal)


@pytest.fixture(scope="session")
def content():
    return mvp_content()


@pytest.fixture(scope="session")
def xcontent():
    """Experimental branch content: every engagement mechanic on."""
    return content_mod.get()


def to_build(content, seed=1):
    """Fresh run advanced to BUILD (day 1) with a vague standup answer."""
    s, _ = reducer.start_run(seed, content)
    for typ, payload in (("advance_stage", {"to": "STANDUP"}), ("reply_standup", {"answer": "vague"}),
                         ("advance_stage", {"to": "BUILD"})):
        s, _ = reducer.apply(s, {"type": typ, "payload": payload}, content)
    return s


def add_card(s, ticket, content, cid=None, deadline_min=10_000):
    cid = cid or f"x{s['next_card']}"
    s["next_card"] += 1
    s["pile"].append({"id": cid, "type": "fix", "sender": "po", "ticket": ticket, "deadline_s": deadline_min * 60.0,
                      "escalation": 0, "state": "pile", "payoff": {}, "penalty": {}, "work": None,
                      "hidden_bug": False, "returns_s": None})
    return cid


def run(s, content, typ, **payload):
    return reducer.apply(s, {"type": typ, "payload": payload}, content)


def ship(s, content, cid, effect="correct", dod=True, honest=True):
    """Open card, patch with the option of `effect`, optionally tick DoD, push. Returns (state, events)."""
    t = content.tickets[next(c["ticket"] for c in s["pile"] if c["id"] == cid)]
    opt = next(o for o in t["options"] if o["effect"] == effect)
    s, _ = run(s, content, "open_card", card_id=cid)
    if t["kind"] == "fix":
        s, _ = run(s, content, "flag_line", line_no=t["buggy_line"])
    s, _ = run(s, content, "select_patch", option_id=opt["id"])
    if honest:
        s, _ = run(s, content, "run_script")
    if dod:
        for b in reducer.DOD:
            s, _ = run(s, content, "toggle_dod", box=b)
    return run(s, content, "push")
