"""Run reducer: apply(state, command, content) -> (state', events). Pure: no I/O, no wall clock.

Time enters only through `tick` commands and action costs. Randomness is a pure function of
(seed, purpose, per-purpose counter), so adding a draw in one purpose never shifts another.
Illegal commands raise GameError and leave the input state untouched.
"""
from __future__ import annotations

import copy
import random

from ..engines import e1, e2
from .content import Content, run_ticket

COMMANDS = ("open_card", "flag_line", "select_patch", "run_script", "toggle_dod", "push", "hold", "triage_reorder",
            "delegate", "coach", "defer", "reply_standup", "answer_call", "watch_tutorial", "buy_perk",
            "use_assistant", "advance_stage", "tick")
RESULT_OF = {"correct": "clean", "correct_small_flaw": "acceptable", "wrong_hidden": "buggy", "security_hole": "security_hole"}
RESULT_LABEL = {"clean": "Clean", "acceptable": "Acceptable", "runtime_error": "Runtime error",
                "buggy": "Functional but buggy", "security_hole": "Security hole"}
ENDINGS = ("win", "lose_rating", "lose_cover", "lose_warnings")
DOD = ("tests", "matches_doc", "no_security")


class GameError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def _illegal(detail: str):
    raise GameError("ILLEGAL_COMMAND", detail)


# ---------------------------------------------------------------- randomness
def draw(s: dict, purpose: str) -> float:
    n = s["draws"].get(purpose, 0)
    s["draws"][purpose] = n + 1
    return random.Random(f"{s['seed']}:{purpose}:{n}").random()


# ---------------------------------------------------------------- creation
def _schedule(content: Content) -> list[tuple[int, str, int]]:
    sch = content.balance["schedule"]
    items = [(c["at"], "card", i) for i, c in enumerate(sch["cards"])]
    items += [(c["at"], "call", i) for i, c in enumerate(sch["calls"])]
    items += [(c["at"], "ping", i) for i, c in enumerate(sch["pings"])]
    return sorted(items, key=lambda x: (x[0], {"card": 0, "ping": 1, "call": 2}[x[1]], x[2]))


def start_run(seed: int, content: Content) -> tuple[dict, list[dict]]:
    b = content.balance
    s = {"seed": seed, "status": "active", "ending": None, "sprint": 1, "stage": "PLANNING", "day": 1,
         "clock_s": 0.0, "day_start_s": 0.0, "meters": dict(b["start"]), "pile": [], "open_card": None,
         "unlocked": [], "perks": [], "shipped": [], "repeat_counts": {}, "call_misses": 0, "warnings": 0,
         "standups": [], "pending_standup": None, "call": None, "coach_credit": 0, "draws": {},
         "process_log": [], "sched_pos": 0, "next_card": 1, "attacked": [], "resolved_ships": 0,
         "content_version": content.version, "balance_version": b["version"]}
    ev: list[dict] = []
    _emit(s, ev, "run_started", seed=seed, content_version=content.version, balance_version=b["version"])
    _fire_schedule(s, ev, content)
    return s, ev


# ---------------------------------------------------------------- helpers
def _emit(s: dict, ev: list, typ: str, **payload) -> None:
    ev.append({"type": typ, "t": s["clock_s"], **payload})


def _card(s: dict, cid: str) -> dict:
    for c in s["pile"]:
        if c["id"] == cid:
            return c
    raise GameError("ILLEGAL_COMMAND", f"no such card {cid}")


def _live(s: dict) -> list[dict]:
    return [c for c in s["pile"] if c["state"] in ("pile", "open", "returned")]


def _cost(s: dict, content: Content, key: str) -> float:
    t = content.balance["time"]
    m = content.balance["costs_min"][key]
    return m * (t["focus_low_cost_multiplier"] if s["meters"]["focus"] < t["focus_low_threshold"] else 1)


def _day_used_min(s: dict) -> float:
    return (s["clock_s"] - s["day_start_s"]) / 60


def _meter(s: dict, key: str, delta: float, content: Content) -> None:
    lim = content.balance["limits"]
    v = s["meters"][key] + delta
    if key == "rating":
        v = round(max(lim["rating_min"], min(lim["rating_max"], v)), 4)
    elif key == "focus":
        v = max(0, min(100, v))
    elif key == "cover":
        v = max(0, v)
    s["meters"][key] = v


def _log(s: dict, what: str) -> None:
    s["process_log"].append(what)


def _ticket(content: Content, tid: str) -> dict:
    return content.tickets[tid]


def _option(ticket: dict, oid: str) -> dict:
    for o in ticket["options"]:
        if o["id"] == oid:
            return o
    raise GameError("ILLEGAL_COMMAND", f"no such option {oid}")


def _bad_option(ticket: dict) -> dict:
    for eff in ("wrong_hidden", "security_hole", "crashes"):
        for o in ticket["options"]:
            if o["effect"] == eff:
                return o
    return ticket["options"][0]


def _spend(s: dict, ev: list, content: Content, key: str) -> None:
    mins = _cost(s, content, key)
    if mins and _day_used_min(s) + mins > content.balance["time"]["day_minutes"] + 1e-9:
        raise GameError("DAY_FULL", "Not enough working hours left today; move on")
    _advance(s, ev, content, mins * 60, day_capped=False)


# ---------------------------------------------------------------- time and scheduler
def _advance(s: dict, ev: list, content: Content, seconds: float, day_capped: bool = True) -> None:
    if seconds <= 0:
        return
    limit = s["day_start_s"] + content.balance["time"]["day_minutes"] * 60
    new = s["clock_s"] + seconds
    if day_capped:
        new = min(new, limit)
    s["clock_s"] = new
    _fire_schedule(s, ev, content)
    _tick_world(s, ev, content)


def _spawn_card(s: dict, ev: list, content: Content, spec: dict) -> None:
    cid = f"c{s['next_card']}"
    s["next_card"] += 1
    card = {"id": cid, "type": spec["type"], "sender": spec["sender"], "ticket": spec.get("ticket"),
            "deadline_s": spec["deadline"] * 60.0, "escalation": 0, "state": "pile",
            "payoff": spec.get("payoff", {}), "penalty": spec.get("penalty", {}), "work": None,
            "hidden_bug": False, "returns_s": None}
    s["pile"].append(card)
    _emit(s, ev, "card_spawned", card_id=cid, card_type=card["type"], sender=card["sender"], ticket=card["ticket"])


def _fire_schedule(s: dict, ev: list, content: Content) -> None:
    sch, b = _schedule(content), content.balance
    spec = b["schedule"]
    while s["sched_pos"] < len(sch) and sch[s["sched_pos"]][0] * 60 <= s["clock_s"]:
        _, kind, idx = sch[s["sched_pos"]]
        s["sched_pos"] += 1
        if kind == "card":
            _spawn_card(s, ev, content, spec["cards"][idx])
        elif kind == "ping":
            w = spec["ping_weights"]
            r, acc, pick = draw(s, "ping_type"), 0.0, "ping_noise"
            for name, p in w.items():
                acc += p
                if r < acc:
                    pick = name
                    break
            _emit(s, ev, "ping_sent", kind=pick, sender=spec["pings"][idx]["sender"])
        else:
            if s["call"] is not None:
                _miss_call(s, ev, content)
            if s["coach_credit"] > 0:
                s["coach_credit"] -= 1
                _emit(s, ev, "call_skipped", sender=spec["calls"][idx]["sender"])
            else:
                s["call"] = {"sender": spec["calls"][idx]["sender"], "expires_s": s["clock_s"] + b["calls"]["window_min"] * 60}
                _emit(s, ev, "call_rang", sender=s["call"]["sender"], expires_s=s["call"]["expires_s"])


def _miss_call(s: dict, ev: list, content: Content) -> None:
    c = content.balance["calls"]
    s["call"] = None
    s["call_misses"] += 1
    _meter(s, "focus", -c["focus_missed_penalty"], content)
    _emit(s, ev, "call_missed", misses=s["call_misses"])
    if s["call_misses"] == 3:
        _meter(s, "cover", c["third_miss_cover"], content)
        _emit(s, ev, "meters_changed", cover=c["third_miss_cover"], reason="third_missed_call")


def _tick_world(s: dict, ev: list, content: Content) -> None:
    esc = content.balance["escalation"]
    if s["call"] and s["clock_s"] >= s["call"]["expires_s"]:
        _miss_call(s, ev, content)
    for c in s["pile"]:
        if c["state"] in ("pile", "open", "returned") and c["deadline_s"] is not None:
            while c["deadline_s"] is not None and c["deadline_s"] <= s["clock_s"]:
                _escalate(s, ev, content, c)
                if c["escalation"] >= esc["max_level"]:
                    c["deadline_s"] = None
                else:
                    c["deadline_s"] += esc["interval_min"] * 60
        if c["state"] == "delegated" and c["returns_s"] is not None and c["returns_s"] <= s["clock_s"]:
            _return_delegation(s, ev, content, c)


def _escalate(s: dict, ev: list, content: Content, c: dict) -> None:
    c["escalation"] = min(content.balance["escalation"]["max_level"], c["escalation"] + 1)
    for k, v in c["penalty"].items():
        _meter(s, k, v, content)
    _emit(s, ev, "card_escalated", card_id=c["id"], level=c["escalation"], penalty=c["penalty"])


def _return_delegation(s: dict, ev: list, content: Content, c: dict) -> None:
    c["returns_s"] = None
    if c["ticket"]:
        c["state"] = "returned"
        _emit(s, ev, "delegation_returned", card_id=c["id"], needs_review=True)
    else:
        c["state"] = "done"
        _apply_payoff(s, c, content)
        _emit(s, ev, "delegation_returned", card_id=c["id"], needs_review=False)


def _apply_payoff(s: dict, c: dict, content: Content) -> None:
    for k, v in c["payoff"].items():
        _meter(s, k, v, content)


# ---------------------------------------------------------------- lose / end
def _check_end(s: dict, ev: list, content: Content) -> None:
    if s["status"] != "active":
        return
    lim = content.balance["limits"]
    ending = None
    if s["meters"]["cover"] >= lim["cover_lose_at"]:
        ending = "lose_cover"
    elif s["meters"]["rating"] < lim["rating_lose_below"]:
        ending = "lose_rating"
    elif s["warnings"] >= lim["warnings_lose_at"]:
        ending = "lose_warnings"
    if ending:
        s["status"], s["ending"] = "ended", ending
        _emit(s, ev, "run_ended", ending=ending)


# ---------------------------------------------------------------- standups and memory
def _check_contradictions(s: dict, ev: list, content: Content) -> None:
    for st in s["standups"]:
        if st["answer"] == "accurate" and not st["contradicted"]:
            bad = [x for x in s["shipped"] if x["ticket"] == st["ticket"] and x["result"] in ("buggy", "security_hole")]
            if bad:
                st["contradicted"] = True
                _meter(s, "cover", content.balance["contradiction_cover"], content)
                _emit(s, ev, "contradiction_detected", standup=st["n"], ticket=st["ticket"],
                      cover=content.balance["contradiction_cover"])


def _begin_standup(s: dict, ev: list, content: Content) -> None:
    _check_contradictions(s, ev, content)
    n = len(s["standups"]) + 1
    last = s["shipped"][-1]["ticket"] if s["shipped"] else None
    if last is None:
        cands = [c["ticket"] for c in s["pile"] if c["ticket"] and c["state"] != "done"]
        last = cands[0] if cands else next(iter(content.tickets))
    s["pending_standup"] = {"n": n, "ticket": last, "concept": content.tickets[last]["concept"],
                            "teammate": "dev1" if n % 2 else "dev2"}
    _meter(s, "focus", content.balance["focus_day_recovery"], content)
    _emit(s, ev, "standup_asked", n=n, ticket=last, concept=s["pending_standup"]["concept"], teammate=s["pending_standup"]["teammate"])


# ---------------------------------------------------------------- review
def _resolve_review(s: dict, ev: list, content: Content) -> None:
    b = content.balance
    _check_contradictions(s, ev, content)
    reviews, rating = [], 0.0
    for sh in s["shipped"][s["resolved_ships"]:]:
        if sh["result"] in ("clean", "acceptable"):
            rating += sh["rating"]
            reviews.append({"ticket": sh["ticket"], "delta": sh["rating"]})
        elif sh["result"] == "buggy":
            d = -b["push"]["wrong_hidden_review_penalty"] * b["push"]["wrong_hidden_reviews"]
            rating += d
            reviews.append({"ticket": sh["ticket"], "delta": d})
    _emit(s, ev, "review_resolved", reviews=reviews)
    posts = []
    for sh in s["shipped"][s["resolved_ships"]:]:
        if sh["result"] == "buggy" and draw(s, "viral") < b["push"]["viral_chance"]:
            lo, hi = b["push"]["viral_range"]
            d = -(lo + draw(s, "viral") * (hi - lo))
            rating += d
            posts.append({"ticket": sh["ticket"], "delta": round(d, 4)})
    _emit(s, ev, "posts_resolved", posts=posts)
    s["resolved_ships"] = len(s["shipped"])
    _meter(s, "rating", rating, content)
    _emit(s, ev, "rating_resolved", delta=round(rating, 4), rating=s["meters"]["rating"])
    for sh in s["shipped"]:
        if sh["result"] == "security_hole" and sh["ticket"] not in s["attacked"]:
            s["attacked"].append(sh["ticket"])
            _meter(s, "rating", b["attack_check"]["rating"], content)
            _meter(s, "points", b["attack_check"]["points"], content)
            _emit(s, ev, "attack_check_resolved", ticket=sh["ticket"], rating=b["attack_check"]["rating"],
                  points=b["attack_check"]["points"])
    if s["meters"]["rating"] < b["limits"]["rating_warn_below"]:
        s["warnings"] += 1
        _emit(s, ev, "warning_issued", warnings=s["warnings"])
    _check_end(s, ev, content)
    if s["status"] == "active" and s["sprint"] >= b["sprints_total"]:
        s["status"], s["ending"] = "ended", "win"
        _emit(s, ev, "run_ended", ending="win")
    elif s["status"] == "active":
        s.update(sprint=s["sprint"] + 1, stage="PLANNING", day=1, standups=[], pending_standup=None,
                 repeat_counts={}, day_start_s=s["clock_s"])
        _emit(s, ev, "stage_advanced", stage="PLANNING", sprint=s["sprint"])


# ---------------------------------------------------------------- handlers
def _need_stage(s: dict, *stages: str) -> None:
    if s["stage"] not in stages:
        _illegal(f"not allowed in stage {s['stage']}")


def _work_of(s: dict) -> tuple[dict, dict]:
    if s["open_card"] is None:
        _illegal("no card is open")
    c = _card(s, s["open_card"])
    return c, c["work"]


def _h_open_card(s, ev, content, p):
    _need_stage(s, "BUILD")
    if s["open_card"] is not None:
        _illegal("a card is already open; hold it first")
    c = _card(s, p["card_id"])
    if c["state"] not in ("pile", "returned"):
        _illegal("card cannot be opened")
    if c["ticket"]:
        t = _ticket(content, c["ticket"])
        work = {"ticket": t["id"], "flagged": None, "selected": None, "last_run": None, "assistant": None,
                "dod": {k: False for k in DOD}, "reviewed": False, "from_delegate": c["state"] == "returned"}
        if c["state"] == "returned":
            work["selected"] = (_bad_option(t) if c["hidden_bug"] else
                                next(o for o in t["options"] if o["effect"] == "correct"))["id"]
            work["flagged"] = t.get("buggy_line")
        c["work"] = c["work"] or work
    c["state"] = "open"
    s["open_card"] = c["id"]
    _spend(s, ev, content, "read" if c["ticket"] else "open_other")
    _emit(s, ev, "card_opened", card_id=c["id"])


def _h_hold(s, ev, content, p):
    if s["open_card"] is None:
        _illegal("no card is open")
    c = _card(s, s["open_card"])
    c["state"] = "returned" if c["work"] and c["work"]["from_delegate"] else "pile"
    s["open_card"] = None
    _emit(s, ev, "card_held", card_id=c["id"])


def _code_work(s) -> tuple[dict, dict]:
    c, w = _work_of(s)
    if w is None:
        _illegal("this card has no code")
    return c, w


def _h_flag_line(s, ev, content, p):
    c, w = _code_work(s)
    t = _ticket(content, w["ticket"])
    if t["kind"] != "fix":
        _illegal("build tickets have no line to flag")
    n = p["line_no"]
    if not 1 <= n <= len(t["source"]):
        _illegal("line out of range")
    w["flagged"] = n
    if w["from_delegate"]:
        w["reviewed"] = True
    _emit(s, ev, "line_flagged", card_id=c["id"], line_no=n, correct=(n == t["buggy_line"]))


def _h_select_patch(s, ev, content, p):
    c, w = _code_work(s)
    t = _ticket(content, w["ticket"])
    o = _option(t, p["option_id"])
    if t["kind"] == "fix" and w["flagged"] != t["buggy_line"]:
        _illegal("flag the line that is wrong first")
    w["selected"], w["last_run"], w["assistant"] = o["id"], None, None
    if w["from_delegate"]:
        w["reviewed"] = True
    _spend(s, ev, content, "patch")
    _emit(s, ev, "patch_selected", card_id=c["id"], option_id=o["id"])


def _h_run_script(s, ev, content, p):
    c, w = _code_work(s)
    t = _ticket(content, w["ticket"])
    opt = _option(t, w["selected"]) if w["selected"] else None
    runs = run_ticket(t, opt, content)
    w["last_run"] = {"all_pass": all(r["pass"] for r in runs), "errors": any(r["error"] for r in runs)}
    if w["from_delegate"]:
        w["reviewed"] = True
    _spend(s, ev, content, "test")
    _emit(s, ev, "script_run", card_id=c["id"], runs=runs, all_pass=w["last_run"]["all_pass"])


def _h_toggle_dod(s, ev, content, p):
    c, w = _code_work(s)
    if p["box"] not in DOD:
        _illegal("unknown checklist box")
    w["dod"][p["box"]] = not w["dod"][p["box"]]
    _emit(s, ev, "dod_toggled", card_id=c["id"], box=p["box"], value=w["dod"][p["box"]])


def _h_push(s, ev, content, p):
    _need_stage(s, "BUILD")
    if s["open_card"] is None:
        _illegal("no card is open")
    c = _card(s, s["open_card"])
    w = c["work"]
    b = content.balance
    if w is None:  # non-code card: send the reply
        c["state"] = "done"
        s["open_card"] = None
        _apply_payoff(s, c, content)
        _spend(s, ev, content, "push")
        _emit(s, ev, "card_answered", card_id=c["id"])
        return
    t = _ticket(content, w["ticket"])
    if not w["selected"]:
        _illegal("choose a patch before pushing")
    o = _option(t, w["selected"])
    if o["effect"] == "crashes":
        _meter(s, "points", b["push"]["points"]["runtime_error"], content)
        _spend(s, ev, content, "push")
        _emit(s, ev, "push_blocked", card_id=c["id"], result="runtime_error", points=b["push"]["points"]["runtime_error"])
        return
    result = RESULT_OF[o["effect"]]
    k = s["repeat_counts"].get(result, 0) if result in ("clean", "acceptable") else 0
    factor = b["push"]["repeat_decay"] ** k
    diff = t["difficulty"]
    pts = b["push"]["points"][result] * (diff if result in ("clean", "acceptable") else 1) * factor
    pts = round(pts)
    rating = round(b["push"]["rating"].get(result, 0) * (factor if result == "clean" else 1), 6)
    if result in ("clean", "acceptable"):
        s["repeat_counts"][result] = k + 1
    cover = 0
    if not all(w["dod"].values()):
        cover = b["push"]["dod_unticked_cover"]
        _meter(s, "cover", cover, content)
        _log(s, "dod_skipped")
    elif w["last_run"] and w["last_run"]["all_pass"]:
        _log(s, "dod_honest")
    else:
        _log(s, "dod_dishonest")
    if w["from_delegate"] and w["reviewed"]:
        _log(s, "review_before_push")
    _meter(s, "points", pts, content)
    s["shipped"].append({"ticket": t["id"], "result": result, "effect": o["effect"], "sprint": s["sprint"], "rating": rating})
    c["state"] = "done"
    s["open_card"] = None
    _spend(s, ev, content, "push")
    _emit(s, ev, "pushed", card_id=c["id"], ticket=t["id"], result=result, label=RESULT_LABEL[result], points=pts, cover=cover)


def _h_delegate(s, ev, content, p):
    _need_stage(s, "BUILD")
    c = _card(s, p["card_id"])
    if c["state"] not in ("pile", "open"):
        _illegal("card cannot be delegated")
    if s["open_card"] == c["id"]:
        s["open_card"] = None
    c["state"], c["work"] = "delegated", None
    c["hidden_bug"] = bool(c["ticket"]) and draw(s, "delegation_bug") < content.balance["delegation"]["hidden_bug_chance"]
    c["returns_s"] = s["clock_s"] + content.balance["delegation"]["return_after_min"] * 60
    _log(s, "delegated")
    _spend(s, ev, content, "delegate")
    _emit(s, ev, "card_delegated", card_id=c["id"], returns_s=c["returns_s"])


def _h_coach(s, ev, content, p):
    _need_stage(s, "BUILD")
    c = _card(s, p["card_id"])
    if c["type"] != "help_call" or c["state"] not in ("pile", "open"):
        _illegal("only a help call can be coached")
    if s["open_card"] == c["id"]:
        s["open_card"] = None
    c["state"] = "done"
    s["coach_credit"] += 1
    _log(s, "coach")
    _log(s, "blocker_cleared")
    _spend(s, ev, content, "coach")
    _emit(s, ev, "card_coached", card_id=c["id"])


def _h_defer(s, ev, content, p):
    _need_stage(s, "BUILD")
    c = _card(s, p["card_id"])
    if c["state"] not in ("pile", "open"):
        _illegal("card cannot be deferred")
    if s["open_card"] == c["id"]:
        s["open_card"] = None
    c["state"] = "pile"
    _escalate(s, ev, content, c)
    c["deadline_s"] = s["clock_s"] + content.balance["escalation"]["interval_min"] * 60
    _spend(s, ev, content, "defer")
    _emit(s, ev, "card_deferred", card_id=c["id"])


def _h_triage_reorder(s, ev, content, p):
    _need_stage(s, "BUILD")
    live = [c["id"] for c in _live(s)]
    if sorted(p["order"]) != sorted(live):
        _illegal("order must list every live card exactly once")
    by = {c["id"]: c for c in s["pile"]}
    rest = [c for c in s["pile"] if c["id"] not in live]
    s["pile"] = [by[i] for i in p["order"]] + rest
    _spend(s, ev, content, "triage")
    _emit(s, ev, "pile_reordered", order=p["order"])


def _h_reply_standup(s, ev, content, p):
    st = s["pending_standup"]
    if not st:
        _illegal("no standup question pending")
    ans = p["answer"]
    if ans not in content.balance["standup_cover"]:
        _illegal("unknown answer")
    if ans == "accurate" and st["concept"] not in s["unlocked"]:
        _illegal("accurate answer is not available until the concept is unlocked")
    delta = content.balance["standup_cover"][ans]
    _meter(s, "cover", delta, content)
    s["standups"].append({"n": st["n"], "ticket": st["ticket"], "answer": ans, "contradicted": False})
    s["pending_standup"] = None
    _log(s, "standup_held")
    _emit(s, ev, "standup_answered", n=st["n"], answer=ans, cover=delta, ticket=st["ticket"])


def _h_answer_call(s, ev, content, p):
    if not s["call"]:
        _illegal("no call is ringing")
    sender, busy = s["call"]["sender"], s["open_card"] is not None
    s["call"] = None
    if busy:
        _meter(s, "focus", -content.balance["calls"]["focus_busy_penalty"], content)
    clue = draw(s, "call_clue") < content.balance["calls"]["clue_chance"]
    _log(s, "blocker_cleared")
    _spend(s, ev, content, "answer_call")
    _emit(s, ev, "call_answered", sender=sender, clue=clue)


def _h_watch_tutorial(s, ev, content, p):
    tut = content.tutorials.get(p["tutorial_id"])
    if not tut:
        _illegal("no such tutorial")
    if tut["concept"] in s["unlocked"]:
        _illegal("already unlocked")
    s["unlocked"].append(tut["concept"])
    _spend(s, ev, content, "tutorial")
    _emit(s, ev, "tutorial_watched", tutorial_id=tut["id"])
    _emit(s, ev, "concept_unlocked", concept=tut["concept"])


def _h_buy_perk(s, ev, content, p):
    perk = content.balance["perks"].get(p["perk_id"])
    if not perk:
        _illegal("no such perk")
    if p["perk_id"] in s["perks"]:
        _illegal("already owned")
    if s["meters"]["points"] < perk["price"]:
        _illegal("not enough points")
    _meter(s, "points", -perk["price"], content)
    s["perks"].append(p["perk_id"])
    _emit(s, ev, "perk_bought", perk_id=p["perk_id"], price=perk["price"])


def _h_use_assistant(s, ev, content, p):
    if "ai_assistant" not in s["perks"]:
        _illegal("you do not own the AI Assistant")
    c, w = _code_work(s)
    t = _ticket(content, w["ticket"])
    right = next(o for o in t["options"] if o["effect"] == "correct")
    pick = right
    if content.balance["assistant_flaky"] and draw(s, "assistant_error") < content.balance["perks"]["ai_assistant"]["error_rate"]:
        wrong = [o for o in t["options"] if o["effect"] != "correct"]
        pick = wrong[int(draw(s, "assistant_error") * len(wrong)) % len(wrong)]
    w["assistant"] = pick["id"]
    _spend(s, ev, content, "assistant")
    _emit(s, ev, "assistant_used", card_id=c["id"], suggested=pick["id"])


def _h_advance_stage(s, ev, content, p):
    to = p.get("to")
    if to not in e1.STAGES or not e1.can_transition(s["stage"], to):
        raise GameError("ILLEGAL_TRANSITION", f"{s['stage']} -> {to}")
    if s["open_card"] is not None:
        _illegal("hold the open card first")
    if s["pending_standup"]:
        _illegal("answer the standup question first")
    two = 2
    if s["stage"] == "BUILD" and to == "STANDUP" and s["day"] >= two:
        _illegal("a sprint has only two standups")
    if s["stage"] == "BUILD" and to == "REVIEW" and s["day"] < two:
        _illegal("finish day 2 before the review")
    if s["stage"] == "BUILD" and to == "STANDUP":
        s["clock_s"] = s["day_start_s"] + content.balance["time"]["day_minutes"] * 60
        s["day"] += 1
        s["day_start_s"] = s["clock_s"]
        _fire_schedule(s, ev, content)
        _tick_world(s, ev, content)
    s["stage"] = to
    _emit(s, ev, "stage_advanced", stage=to, sprint=s["sprint"], day=s["day"])
    if to == "STANDUP":
        _begin_standup(s, ev, content)
    elif to == "REVIEW":
        _resolve_review(s, ev, content)


def _h_tick(s, ev, content, p):
    if s["stage"] != "BUILD":
        return
    t = content.balance["time"]
    ms = max(0, min(int(p["real_ms"]), t["tick_max_real_ms"]))
    _advance(s, ev, content, ms / 1000 * t["real_to_game"])
    _emit(s, ev, "tick_applied", real_ms=ms)


HANDLERS = {"open_card": _h_open_card, "flag_line": _h_flag_line, "select_patch": _h_select_patch,
            "run_script": _h_run_script, "toggle_dod": _h_toggle_dod, "push": _h_push, "hold": _h_hold,
            "triage_reorder": _h_triage_reorder, "delegate": _h_delegate, "coach": _h_coach, "defer": _h_defer,
            "reply_standup": _h_reply_standup, "answer_call": _h_answer_call, "watch_tutorial": _h_watch_tutorial,
            "buy_perk": _h_buy_perk, "use_assistant": _h_use_assistant, "advance_stage": _h_advance_stage,
            "tick": _h_tick}


def apply(state: dict, command: dict, content: Content) -> tuple[dict, list[dict]]:
    """command = {"type": str, "payload": dict}. Raises GameError; never mutates `state`."""
    if state["status"] != "active":
        raise GameError("ILLEGAL_COMMAND", "the run has ended")
    h = HANDLERS.get(command.get("type"))
    if h is None:
        raise GameError("ILLEGAL_COMMAND", f"unknown command {command.get('type')!r}")
    s, ev = copy.deepcopy(state), []
    try:
        h(s, ev, content, command.get("payload") or {})
    except KeyError as e:
        raise GameError("ILLEGAL_COMMAND", f"missing field {e}") from e
    _check_end(s, ev, content)
    return s, ev


# ---------------------------------------------------------------- views
def process_score(s: dict, content: Content) -> int:
    return e2.process_score(s["process_log"], content.balance["process_score"])


def debrief(s: dict, content: Content) -> dict:
    m = s["meters"]
    ps = process_score(s, content)
    rating_pct = round((m["rating"] - 1) / 4 * 100)
    return {"ending": s["ending"], "status": s["status"], "rating": m["rating"], "cover": m["cover"], "points": m["points"],
            "process_score": ps, "gap": rating_pct - ps, "shipped": [x["result"] for x in s["shipped"]]}


def public_state(s: dict, content: Content) -> dict:
    """State for the browser: no answer keys, no hidden-bug flags."""
    open_work = None
    if s["open_card"]:
        c = _card(s, s["open_card"])
        w = c["work"]
        if w:
            t = _ticket(content, w["ticket"])
            lines = list(t["source"])
            gl = {k: (v if t["concept"] in s["unlocked"] else "???") for k, v in t["glossary"].items()}
            open_work = {"ticket": t["id"], "title": t["title"], "doc": t["doc"], "kind": t["kind"], "lines": lines,
                         "options": [{"id": o["id"], "text": o["text"]} for o in t["options"]], "glossary": gl,
                         "concept": t["concept"], "flagged": w["flagged"], "selected": w["selected"], "dod": w["dod"],
                         "last_run": w["last_run"], "assistant": w["assistant"]}
    st = s["pending_standup"]
    standup = None
    if st:
        choices = ["vague", "wrong"] + (["accurate"] if st["concept"] in s["unlocked"] else [])
        standup = {"n": st["n"], "ticket": st["ticket"], "teammate": st["teammate"], "choices": choices}
    return {"status": s["status"], "ending": s["ending"], "sprint": s["sprint"], "stage": s["stage"], "day": s["day"],
            "clock_min": round(s["clock_s"] / 60, 1), "day_used_min": round(_day_used_min(s), 1),
            "meters": s["meters"], "warnings": s["warnings"], "open_card": s["open_card"], "work": open_work,
            "standup": standup, "call": s["call"], "unlocked": s["unlocked"], "perks": s["perks"],
            "pile": [{"id": c["id"], "type": c["type"], "sender": c["sender"], "ticket": c["ticket"],
                      "title": content.tickets[c["ticket"]]["title"] if c["ticket"] else None,
                      "state": c["state"], "escalation": c["escalation"], "payoff": c["payoff"], "penalty": c["penalty"],
                      "deadline_min": None if c["deadline_s"] is None else round(c["deadline_s"] / 60, 1)}
                     for c in s["pile"]]}
