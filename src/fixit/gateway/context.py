"""Turn reducer events into dialogue requests. Read-only: never feeds anything back into game state."""
from __future__ import annotations

from ..rules.content import Content
from .gateway import Request


def memory_segments(state: dict, content: Content) -> list[dict]:
    segs = []
    for i, st in enumerate(state["standups"]):
        t = content.tickets[st["ticket"]]
        segs.append({"id": f"standup{st['n']}", "seq": i + 1, "stages": ["STANDUP", "BUILD", "REVIEW"],
                     "text": f"At standup {st['n']} the player gave a {st['answer']} answer about '{t['title']}'."})
    for i, sh in enumerate(state["shipped"]):
        segs.append({"id": f"push{i}", "seq": 100 + i, "text": f"The player pushed '{sh['ticket']}'."})
    return segs


def requests_for(events: list[dict], state: dict, content: Content, user_key: str, counter: int) -> list[Request]:
    """One request per event that needs a teammate line (ping, call, standup, help call, status demand)."""
    out = []
    for e in events:
        et = tid = None
        if e["type"] == "ping_sent":
            et, tid = e["kind"], e["sender"]
        elif e["type"] == "call_rang":
            et, tid = "help_call", e["sender"]
        elif e["type"] == "standup_asked":
            et, tid = "standup_question", e["teammate"]
        elif e["type"] == "card_spawned" and e["card_type"] in ("help_call", "status_demand"):
            et, tid = e["card_type"], e["sender"]
        if not et or tid not in content.teammates:
            continue
        facts, forbidden = {"stage": state["stage"], "sprint": state["sprint"]}, []
        tk = e.get("ticket")
        if e["type"] == "standup_asked":
            tk = e["ticket"]
        if tk:
            t = content.tickets[tk]
            facts.update(ticket_title=t["title"], concept=t["concept"])
            forbidden = [o["text"] for o in t["options"] if o["effect"] == "correct"]
        counter += 1
        out.append(Request(event_type=et, teammate_id=tid, facts=facts, memory=memory_segments(state, content),
                           stage=state["stage"], seed=state["seed"], n=counter, user_key=user_key, forbidden=forbidden))
    return out
