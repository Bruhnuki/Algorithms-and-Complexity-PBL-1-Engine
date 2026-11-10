"""Turn reducer events into dialogue requests. Read-only: never feeds anything back into game state."""
from __future__ import annotations

from ..rules import reducer
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


def _title(content: Content, tid: str | None) -> str:
    return content.tickets[tid]["title"] if tid in content.tickets else "that item"


def _trust(state: dict, tid: str) -> int | None:
    t = ((state.get("x") or {}).get("team_trust")) or {}
    if tid in t:
        return t[tid]
    return round(sum(t.values()) / len(t)) if t else None   # the Product Owner goes by the team's average trust


def _reaction(e: dict, events: list[dict], state: dict, content: Content) -> tuple | None:
    """(teammate, event_type, facts, ticket) for the things the player does that the team should react to, else None."""
    typ = e["type"]
    sprint = state["sprint"]
    if typ == "standup_answered":
        et = {"accurate": "react_standup_honest", "vague": "react_standup_vague", "wrong": "react_standup_lie"}[e["answer"]]
        return e["dev"], et, {"item": _title(content, e.get("ticket"))}, e.get("ticket")
    if typ == "offload_result":
        return e["dev"], "react_offload_ok" if e["ok"] else "react_offload_fail", {"item": e["title"]}, None
    if typ == "card_coached":
        card = next((c for c in state["pile"] if c["id"] == e["card_id"]), None)
        return (card["sender"], "react_coached", {}, None) if card and card["sender"] in ("dev1", "dev2") else None
    if typ == "help_answered" and e["delta"] >= 0 or typ == "help_solved":
        return e["dev"], "react_coached", {}, None
    if typ == "pushed":
        return "po", "react_push", {"item": _title(content, e.get("ticket"))}, e.get("ticket")   # never says whether it was good: that is revealed at the Review
    if typ == "rating_resolved" and state.get("guide") is not None:
        f = reducer._g_sprint_facts(state, content)
        hidden = next((h for h in events if h["type"] == "hidden_problem" and h.get("harder")), None)
        facts = {"done": f["done"], "total": f["total"], "next": sprint + 1, "n_hidden": hidden["items"] if hidden else 0}
        return "po", "react_review_hidden" if hidden else "react_review", facts, None
    if typ == "sprint_dealt" and state.get("guide") is not None:
        g = reducer._gsprint(content, sprint) or {}
        return "po", "sprint_open", {"goal": g.get("goal", "ship the checkout fixes"), "n_hidden": len(state["guide"].get("hard_ids", []))}, None
    return None


def requests_for(events: list[dict], state: dict, content: Content, user_key: str, counter: int) -> list[Request]:
    """One request per event that needs a teammate line (ping, call, standup, help call, status demand, or a reaction to what the player did)."""
    out = []
    tutorial = bool((state.get("x") or {}).get("tutorial"))
    for e in events:
        r = None if tutorial else _reaction(e, events, state, content)
        if r:
            tid, et, extra, tk = r
            facts = {"stage": state["stage"], "sprint": state["sprint"], "rating": round(state["meters"]["rating"], 1), **extra}
            trust = _trust(state, tid)
            if trust is not None:
                facts["trust"] = trust
                facts["mood"] = "warm" if trust >= 80 else "neutral" if trust >= 60 else "cold"
            forbidden = [o["text"] for o in content.tickets[tk]["options"] if o["effect"] == "correct"] if tk in content.tickets else []
            counter += 1
            out.append(Request(event_type=et, teammate_id=tid, facts=facts, memory=memory_segments(state, content),
                               stage=state["stage"], seed=state["seed"], n=counter, user_key=user_key, forbidden=forbidden))
            continue
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
