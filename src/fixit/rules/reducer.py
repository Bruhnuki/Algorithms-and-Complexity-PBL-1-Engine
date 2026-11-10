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
            "use_assistant", "advance_stage", "tick",
            # experimental branch only (rejected when balance.experimental.enabled is false)
            "configure", "buy_practice", "reroll_shop", "lock_offer", "retro", "use_ultimate")
SERVER_ONLY = ("configure",)   # issued by the API at run creation; never accepted from a browser
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
    if _exp(content):
        _x_start(s, ev, content)
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
    low = t["focus_low_threshold"]
    if _exp(content):
        m *= _x_cost_mult(s, content, key)
        if _has(s, "sustainable_pace"):
            low = _fx(s, content, "sustainable_pace", "low_threshold")
    return m * (t["focus_low_cost_multiplier"] if s["meters"]["focus"] < low else 1)


def _day_minutes(s: dict, content: Content) -> float:
    if not _exp(content):
        return content.balance["time"]["day_minutes"]
    return _x_day_minutes(s, content)


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
    if key == "cover" and s.get("x"):
        s["x"]["max_cover"] = max(s["x"]["max_cover"], v)


def _log(s: dict, what: str) -> None:
    s["process_log"].append(what)
    if s.get("x"):
        _xlog(s, what)


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
    if mins and _day_used_min(s) + mins > _day_minutes(s, content) + 1e-9:
        raise GameError("DAY_FULL", "Not enough working hours left today; move on")
    _advance(s, ev, content, mins * 60, day_capped=False)


# ---------------------------------------------------------------- time and scheduler
def _advance(s: dict, ev: list, content: Content, seconds: float, day_capped: bool = True) -> None:
    if seconds <= 0:
        return
    limit = s["day_start_s"] + _day_minutes(s, content) * 60
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
    if s.get("x"):
        _x_card_spawned(s, content, card, spec)
    s["pile"].append(card)
    _emit(s, ev, "card_spawned", card_id=cid, card_type=card["type"], sender=card["sender"], ticket=card["ticket"])


def _fire_schedule(s: dict, ev: list, content: Content) -> None:
    if s.get("x"):
        return _x_fire_schedule(s, ev, content)
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
            _ring(s, ev, content, spec["calls"][idx]["sender"])


def _pick_ping(s: dict, content: Content) -> str:
    r, acc = draw(s, "ping_type"), 0.0
    for name, p in content.balance["schedule"]["ping_weights"].items():
        acc += p
        if r < acc:
            return name
    return "ping_noise"


def _ring(s: dict, ev: list, content: Content, sender: str) -> None:
    if s["call"] is not None:
        _miss_call(s, ev, content)
    if s["coach_credit"] > 0:
        s["coach_credit"] -= 1
        _emit(s, ev, "call_skipped", sender=sender)
    else:
        s["call"] = {"sender": sender, "expires_s": s["clock_s"] + content.balance["calls"]["window_min"] * 60}
        _emit(s, ev, "call_rang", sender=sender, expires_s=s["call"]["expires_s"])


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
    if s.get("x"):
        _x_tick_world(s, ev, content)


def _escalate(s: dict, ev: list, content: Content, c: dict) -> None:
    if s.get("x") and not _x_may_escalate(s, c):
        return
    c["escalation"] = min(content.balance["escalation"]["max_level"], c["escalation"] + 1)
    for k, v in c["penalty"].items():
        _meter(s, k, v, content)
    _emit(s, ev, "card_escalated", card_id=c["id"], level=c["escalation"], penalty=c["penalty"])
    if s.get("x"):
        _break_combo(s, ev, content, "a request got louder")
        wv = s["x"].get("wave")
        if wv and c.get("wave") and not wv["failed"]:
            wv["failed"] = True
            _emit(s, ev, "wave_failed", left=wv["left"])
        if c.get("outage") and not c.get("outage_missed"):
            E = _O(content, "events")
            c["outage_missed"] = True
            _meter(s, "rating", E["outage_miss_rating"], content)
            _meter(s, "cover", E["outage_miss_cover"], content)
            _emit(s, ev, "outage_missed", card_id=c["id"], rating=E["outage_miss_rating"], cover=E["outage_miss_cover"])


def _return_delegation(s: dict, ev: list, content: Content, c: dict) -> None:
    c["returns_s"] = None
    if c["ticket"]:
        c["state"] = "returned"
        if _orig(content, "change_review"):
            _make_review(s, content, c)
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
    elif s["warnings"] >= (_x_warnings_lose_at(s, content) if s.get("x") else lim["warnings_lose_at"]):
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
    if _on(s, content, "action_hand"):
        _new_hand(s, ev, content)
    for dev in ("dev1", "dev2"):
        _trust_gain(s, ev, content, dev, "trust_daily_recovery", "standup")
    if s.get("x"):
        f = content.balance["experimental"]["focus"]["day_refill"]
        if "focus_mode" in s["perks"]:
            f += content.balance["perks"]["focus_mode"]["morning_focus"]
        if _has(s, "sustainable_pace"):
            f += _fx(s, content, "sustainable_pace", "extra_refill")
        _meter(s, "focus", f, content)
    else:
        _meter(s, "focus", content.balance["focus_day_recovery"], content)
    _emit(s, ev, "standup_asked", n=n, ticket=last, concept=s["pending_standup"]["concept"], teammate=s["pending_standup"]["teammate"])


# ---------------------------------------------------------------- review
def _resolve_review(s: dict, ev: list, content: Content) -> None:
    b = content.balance
    if s.get("x"):
        _x_auto_ship(s, ev, content)
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
        if sh["result"] == "buggy" and draw(s, "viral") < (_x_viral_chance(s, content) if s.get("x") else b["push"]["viral_chance"]):
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
    if s.get("x"):
        _x_goal_check(s, ev, content)
    if s["meters"]["rating"] < b["limits"]["rating_warn_below"]:
        s["warnings"] += 1
        _emit(s, ev, "warning_issued", warnings=s["warnings"])
    _check_end(s, ev, content)
    total = b["experimental"]["sprints_total"] if s.get("x") else b["sprints_total"]
    if s.get("x"):
        _x_end_sprint(s, ev, content)
    if s["status"] == "active" and s["sprint"] >= total:
        s["status"], s["ending"] = "ended", "win"
        _emit(s, ev, "run_ended", ending="win")
    elif s["status"] == "active":
        s.update(sprint=s["sprint"] + 1, stage="PLANNING", day=1, standups=[], pending_standup=None,
                 repeat_counts={}, day_start_s=s["clock_s"])
        _emit(s, ev, "stage_advanced", stage="PLANNING", sprint=s["sprint"])
        if s.get("x"):
            _x_begin_sprint(s, ev, content)


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
    if c["state"] == "returned" and c.get("review"):
        _illegal("returned work is reviewed change by change")
    _play(s, ev, content, "work")
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
    if s.get("x"):
        _x_context_switch(s, ev, content, c)
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
    right = n == t["buggy_line"]
    if not right and s.get("x"):
        w["misses"] = w.get("misses", 0) + 1
        _break_combo(s, ev, content, "wrong line")
    _emit(s, ev, "line_flagged", card_id=c["id"], line_no=n, correct=right)


def _h_select_patch(s, ev, content, p):
    c, w = _code_work(s)
    t = _ticket(content, w["ticket"])
    o = _option(t, p["option_id"])
    if t["kind"] == "fix" and w["flagged"] != t["buggy_line"]:
        _illegal("line %s is not the broken one. Read the description again and click the line that doesn't match it" % w["flagged"]
                 if w["flagged"] else "click the line that is wrong first")
    w["selected"], w["last_run"], w["assistant"] = o["id"], None, None
    if w["from_delegate"]:
        w["reviewed"] = True
    _spend(s, ev, content, "patch")
    _emit(s, ev, "patch_selected", card_id=c["id"], option_id=o["id"])


def _h_run_script(s, ev, content, p):
    c, w = _code_work(s)
    _play(s, ev, content, "test")
    t = _ticket(content, w["ticket"])
    opt = _option(t, w["selected"]) if w["selected"] else None
    runs = run_ticket(t, opt, content)
    w["last_run"] = {"all_pass": all(r["pass"] for r in runs), "errors": any(r["error"] for r in runs)}
    if w["from_delegate"]:
        w["reviewed"] = True
    if s.get("x") and _x_free_run(s, ev, content, w):
        pass
    else:
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
    if s.get("x") and _x_boss_now(s) == "friday_deploy" and not all(w["dod"].values()):
        _illegal("Friday Deploy: every Definition of Done box must be ticked before a push")
    _release_room(s, content)
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
    ps_before = process_score(s, content)
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
    honest = all(w["dod"].values()) and bool(w["last_run"] and w["last_run"]["all_pass"])
    pts, extra = _award(s, ev, content, pts, result, t["id"], honest, ps_before)
    s["shipped"].append({"ticket": t["id"], "result": result, "effect": o["effect"], "sprint": s["sprint"], "rating": rating})
    c["state"] = "done"
    s["open_card"] = None
    _spend(s, ev, content, "push")
    _emit(s, ev, "pushed", card_id=c["id"], ticket=t["id"], result=result, label=RESULT_LABEL[result], points=pts, cover=cover, **extra)
    _draw_after_push(s, ev, content)
    if s.get("x"):
        _x_after_push(s, ev, content, c, w, result)
        _finish_bonus(s, ev, content, c, result)


def _h_delegate(s, ev, content, p):
    _need_stage(s, "BUILD")
    c = _card(s, p["card_id"])
    if c["state"] not in ("pile", "open"):
        _illegal("card cannot be delegated")
    if s.get("x") and not _feat(s, "delegate"):
        _illegal("asking the team unlocks in sprint 2")
    _play(s, ev, content, "delegate")
    if s["open_card"] == c["id"]:
        s["open_card"] = None
    team = _orig(content, "team_board")
    if team:
        dev = _pick_dev(s, p.get("to"))
    c["state"], c["work"] = "delegated", None
    c["assignee"] = dev if team else (c["sender"] if c["sender"] in ("dev1", "dev2") else ("dev1", "dev2")[s["next_card"] % 2])
    base = (_O(content, "team_board")["bug_chance"][dev] * (_fx(s, content, "pair_programming", "bug_chance_mult") if _has(s, "pair_programming") else 1)
            * (content.balance["perks"]["team_training"]["bug_mult"] if "team_training" in s["perks"] else 1)) if team else _bug_chance(s, content)
    c["hidden_bug"] = bool(c["ticket"]) and draw(s, "delegation_bug") < base + _trust_penalty(s, content, c["assignee"])
    if s.get("x") and _has(s, "pair_programming") and c["ticket"]:
        _use_practice(s, ev, content, "pair_programming")
    back = _O(content, "change_review")["return_after_min"] if _orig(content, "change_review") else content.balance["delegation"]["return_after_min"]
    c["returns_s"] = None if team else s["clock_s"] + back * 60
    if team:
        _assign(s, ev, content, dev, c)
    if _on(s, content, "action_hand"):
        got = _draw_cards(s, _O(content, "action_hand")["draw_after_delegate"])
        if got:
            _emit(s, ev, "cards_drawn", cards=got)
    _log(s, "delegated")
    _spend(s, ev, content, "delegate")
    _emit(s, ev, "card_delegated", card_id=c["id"], returns_s=c["returns_s"])


def _h_coach(s, ev, content, p):
    _need_stage(s, "BUILD")
    c = _card(s, p["card_id"])
    if c["type"] != "help_call" or c["state"] not in ("pile", "open"):
        _illegal("only a help call can be coached")
    _play(s, ev, content, "coach")
    if s["open_card"] == c["id"]:
        s["open_card"] = None
    c["state"] = "done"
    s["coach_credit"] += 1
    if s.get("x") and _has(s, "swarming"):
        s["coach_credit"] += _fx(s, content, "swarming", "extra_skips")
        _use_practice(s, ev, content, "swarming")
    _log(s, "coach")
    _log(s, "blocker_cleared")
    _trust_gain(s, ev, content, c["sender"], "trust_per_coach", "coached")
    _spend(s, ev, content, "coach")
    _emit(s, ev, "card_coached", card_id=c["id"])


def _h_defer(s, ev, content, p):
    _need_stage(s, "BUILD")
    c = _card(s, p["card_id"])
    if c["state"] not in ("pile", "open"):
        _illegal("card cannot be deferred")
    _play(s, ev, content, "defer")
    if s["open_card"] == c["id"]:
        s["open_card"] = None
    c["state"] = "pile"
    if s.get("x") and _has(s, "backlog_refinement"):
        _use_practice(s, ev, content, "backlog_refinement")
    else:
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
    if ans == "accurate" and not _accurate_ok(s, st):
        _illegal("accurate answer is not available until the concept is unlocked")
    delta = content.balance["standup_cover"][ans]
    if s.get("x"):
        delta = _x_standup_delta(s, ev, content, ans, delta)
    _meter(s, "cover", delta, content)
    s["standups"].append({"n": st["n"], "ticket": st["ticket"], "answer": ans, "contradicted": False})
    s["pending_standup"] = None
    _log(s, "standup_held")
    _emit(s, ev, "standup_answered", n=st["n"], answer=ans, cover=delta, ticket=st["ticket"])


def _h_answer_call(s, ev, content, p):
    if not s["call"]:
        _illegal("no call is ringing")
    _play(s, ev, content, "call")
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
    _play(s, ev, content, "learn")
    s["unlocked"].append(tut["concept"])
    _spend(s, ev, content, "tutorial")
    _emit(s, ev, "tutorial_watched", tutorial_id=tut["id"])
    _emit(s, ev, "concept_unlocked", concept=tut["concept"])
    if s.get("x"):
        _x_tutorial_unlock(s, ev, content, tut["id"])


def _h_buy_perk(s, ev, content, p):
    perk = content.balance["perks"].get(p["perk_id"])
    if not perk:
        _illegal("no such perk")
    if p["perk_id"] in s["perks"]:
        _illegal("already owned")
    if p["perk_id"] != "ai_assistant" and not s.get("x"):
        _illegal("that skill is not sold in this version")
    if s.get("x") and "no_assistant" in s["x"]["heat"] and p["perk_id"] == "ai_assistant":
        _illegal("Heat: the AI Assistant is switched off in this run")
    if s["meters"]["points"] < perk["price"]:
        _illegal("not enough points")
    _meter(s, "points", -perk["price"], content)
    s["perks"].append(p["perk_id"])
    _emit(s, ev, "perk_bought", perk_id=p["perk_id"], price=perk["price"])


def _h_use_assistant(s, ev, content, p):
    if "ai_assistant" not in s["perks"]:
        _illegal("you do not own the AI Assistant")
    c, w = _code_work(s)
    _play(s, ev, content, "assist")
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
        s["clock_s"] = s["day_start_s"] + _day_minutes(s, content) * 60
        s["day"] += 1
        s["day_start_s"] = s["clock_s"]
        _fire_schedule(s, ev, content)
        _tick_world(s, ev, content)
    s["stage"] = to
    if s.get("x") and s["x"]["shop"] and to != "PLANNING":
        s["x"]["shop"] = None   # the shop closes when planning ends
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
    if s.get("x") and not _x_clock_running(s, content):
        if s["open_card"]:   # the world waits while you read, but your fix is being timed
            w = _card(s, s["open_card"])["work"]
            if w is not None:
                w["ms"] = w.get("ms", 0) + ms
        return   # hybrid clock: paused while you read a card or answer a standup
    _advance(s, ev, content, ms / 1000 * t["real_to_game"])
    _emit(s, ev, "tick_applied", real_ms=ms)


# ================================================================ EXPERIMENTAL engagement mechanics
# Everything below runs only when balance.experimental.enabled is true. State lives in s["x"]
# (None in the original game), all numbers come from balance.yaml, and every random draw uses its own
# named purpose so the run stays deterministic for a seed + command list.

def _exp(content: Content) -> bool:
    return bool(content.balance.get("experimental", {}).get("enabled"))


def _X(content: Content) -> dict:
    return content.balance["experimental"]


def _has(s: dict, pid: str) -> bool:
    return bool(s.get("x")) and pid in s["x"]["practices"]


def _fx(s: dict, content: Content, pid: str, key: str):
    """A practice's effect value, using the `_lv2` variant once the practice has evolved."""
    eff = _X(content)["practices"]["effects"][pid]
    if s["x"]["practices"].get(pid, {}).get("level", 1) >= 2 and f"{key}_lv2" in eff:
        return eff[f"{key}_lv2"]
    return eff[key]


def _use_practice(s: dict, ev: list, content: Content, pid: str) -> None:
    p = s["x"]["practices"].get(pid)
    if not p:
        return
    p["uses"] += 1
    if p["level"] == 1 and p["uses"] >= _X(content)["practices"]["evolve_at"]:
        p["level"] = 2
        _emit(s, ev, "practice_evolved", practice=pid)


def _bug_chance(s: dict, content: Content) -> float:
    ch = content.balance["delegation"]["hidden_bug_chance"]
    if _has(s, "pair_programming"):
        ch *= _fx(s, content, "pair_programming", "bug_chance_mult")
    if "team_training" in s["perks"]:
        ch *= content.balance["perks"]["team_training"]["bug_mult"]
    return ch


def _accurate_ok(s: dict, st: dict) -> bool:
    return st["concept"] in s["unlocked"] or _has(s, "psychological_safety")


def _rand_between(s: dict, purpose: str, lo: float, hi: float) -> float:
    return lo + draw(s, purpose) * (hi - lo)


def _xlog(s: dict, what: str) -> None:
    """Style tally (display only) and momentum. Never touches the process log or Points."""
    x = s["x"]
    x["style_log"].append(what)
    gain = x["momentum_gain"].get(what, 0) if "momentum" in x.get("features", FEATURES) else 0
    if gain:
        x["momentum"] = min(x["momentum_full"], x["momentum"] + gain)


FEATURES = ("delegate", "practices", "intents", "lanes", "style", "director", "hand", "release", "multiplier", "momentum")


def _features_for(sprint: int, content: Content) -> list[str]:
    ob = content.balance.get("onboarding", {})
    if not ob.get("enabled"):
        return list(FEATURES)
    return [f for f in FEATURES if sprint >= ob["unlock_sprint"].get(f, 1)]


def _feat(s: dict, name: str) -> bool:
    """Onboarding: is this mechanic switched on yet in this run?"""
    return bool(s.get("x")) and name in s["x"].get("features", FEATURES)


def _refresh_features(s: dict, ev: list, content: Content) -> None:
    old = set(s["x"].get("features", []))
    s["x"]["features"] = _features_for(s["sprint"], content)
    new = [f for f in s["x"]["features"] if f not in old]
    if new and old:
        _emit(s, ev, "features_unlocked", features=new, sprint=s["sprint"])


def _x_start(s: dict, ev: list, content: Content) -> None:
    X = _X(content)
    s["meters"]["focus"] = X["focus"]["start"]
    s["x"] = {"sched": [], "used_tickets": [], "practices": {}, "shop": None, "heat": [], "unlocks": [],
              "configured": False, "boss": None, "max_cover": 0, "last_stand": False, "clutches": 0,
              "style_log": [], "style_history": [], "momentum": 0, "momentum_full": X["momentum"]["full"],
              "momentum_gain": dict(X["momentum"]["gain"]), "protect_until_s": 0.0, "retro_uses": 0,
              "last_card": None, "next_spot_s": 0.0, "next_director_s": X["director"]["every_min"] * 60.0,
              "relief_used": False, "bounty_card": None, "achievements": [], "free_runs": {},
              "sprint_start_s": 0.0, "bluffed_this_sprint": False, "flags": [], "goals": []}
    _refresh_features(s, ev, content)
    _o_start(s, ev, content)
    bosses = sorted(X["bosses"])
    s["x"]["boss"] = bosses[int(draw(s, "boss") * len(bosses)) % len(bosses)]
    _x_deal_sprint(s, ev, content)
    if X["shop"]["free_pick_at_start"] and _feat(s, "practices"):
        _x_open_shop(s, ev, content, free=True)


def _x_pool(s: dict, content: Content) -> list[str]:
    P = _X(content)["practices"]
    pool = list(P["base_pool"])
    for tid, pid in P["unlocked_by_tutorial"].items():
        if tid in content.tutorials and content.tutorials[tid]["concept"] in s["unlocked"] and pid not in pool:
            pool.append(pid)
    pool += [u for u in s["x"]["unlocks"] if u in P["effects"] and u not in pool]
    return [p for p in pool if p not in s["x"]["practices"]]


def _x_offers(s: dict, content: Content, keep: list[dict]) -> list[dict]:
    X = _X(content)
    have = {o["id"] for o in keep}
    pool = [p for p in _x_pool(s, content) if p not in have]
    out = list(keep)
    lo, hi = X["practices"]["price"]
    while len(out) < X["shop"]["offers"] and pool:
        pid = pool.pop(int(draw(s, "shop") * len(pool)) % len(pool))
        out.append({"id": pid, "price": int(round(_rand_between(s, "shop_price", lo, hi) / 5) * 5), "locked": False})
    return out


def _x_open_shop(s: dict, ev: list, content: Content, free: bool = False) -> None:
    keep = [o for o in (s["x"].get("kept_offers") or []) if o["id"] not in s["x"]["practices"]]
    s["x"]["shop"] = {"free": free, "rerolls": 0, "offers": _x_offers(s, content, keep)}
    s["x"]["kept_offers"] = []
    _emit(s, ev, "shop_opened", free=free, offers=[o["id"] for o in s["x"]["shop"]["offers"]])


def _x_deal_sprint(s: dict, ev: list, content: Content) -> None:
    """M5 seeded runs: draw this sprint's cards, calls and pings from the seed."""
    X, k = _X(content), s["sprint"]
    d = X["sprint_deal"]
    i = min(k - 1, len(d["code_cards"]) - 1)
    t0 = s["clock_s"]
    s["x"]["sprint_start_s"] = t0
    pur = f"deal{k}"
    unused = [t for t in sorted(content.tickets) if t not in s["x"]["used_tickets"]]
    easy = [t for t in unused if content.tickets[t]["difficulty"] <= d["max_difficulty"][i]]
    picks = []
    for _ in range(d["code_cards"][i]):
        src = easy or unused or sorted(content.tickets)
        t = src.pop(int(draw(s, pur) * len(src)) % len(src))
        for lst in (easy, unused):
            if t in lst:
                lst.remove(t)
        picks.append(t)
        s["x"]["used_tickets"].append(t)
    items = []
    lo, hi = d["spread_min"]
    dlo, dhi = d["deadline_min"]

    def card(spec_type, sender, ticket, payoff, penalty, first=False):
        at = 0 if first else _rand_between(s, pur, lo, hi)   # the first tickets are waiting when the sprint starts
        return {"at_s": t0 + at * 60, "kind": "card", "spec": {"type": spec_type, "sender": sender, "ticket": ticket,
                "deadline": (t0 / 60) + at + _rand_between(s, pur, dlo, dhi), "payoff": payoff, "penalty": penalty}}
    for n, t in enumerate(picks):
        kind = content.tickets[t]["kind"]
        items.append(card("build" if kind == "build" else "fix", "po" if kind == "build" else ("dev1", "dev2")[n % 2],
                          t, dict(d["code_payoff"]), dict(d["code_penalty"]), first=(n < d.get("start_cards", 1))))
    for n in range(d["help_calls"][i]):
        items.append(card("help_call", ("dev2", "dev1")[n % 2], None, {}, dict(d["other_penalty"])))
    for _ in range(d["status_demands"][i]):
        items.append(card("status_demand", "po", None, {}, dict(d["other_penalty"])))
    clo, chi = d["call_spread_min"]
    for n in range(d["calls"][i]):
        items.append({"at_s": t0 + _rand_between(s, pur, clo, chi) * 60, "kind": "call", "sender": ("dev2", "po", "dev1")[n % 3]})
    plo, phi = d["ping_spread_min"]
    for n in range(d["pings"][i]):
        items.append({"at_s": t0 + _rand_between(s, pur, plo, phi) * 60, "kind": "ping", "sender": ("dev1", "dev2")[n % 2]})
    if _orig(content, "events"):
        E = _O(content, "events")
        for day in (0, 1):
            for ev_name, key in (("outage", "outage_chance_per_day"), ("wave", "wave_chance_per_day"), ("urgent", "urgent_chance_per_day")):
                if draw(s, pur + ev_name) < E[key]:
                    at = day * 480 + _rand_between(s, pur + ev_name, 90, 380)
                    items.append({"at_s": t0 + at * 60, "kind": "event", "event": ev_name})
    if _x_boss_sprint(s, content) and s["x"]["boss"] == "scope_creep":
        every = X["bosses"]["scope_creep"]["every_min"]
        for m in range(every, 900, every):
            items.append({"at_s": t0 + m * 60, "kind": "card", "spec": {"type": "status_demand", "sender": "po", "ticket": None,
                          "deadline": t0 / 60 + m + dlo, "payoff": {}, "penalty": dict(d["other_penalty"]), "scope": True}})
    if "po_pressure" in s["x"]["heat"]:
        for m in (200, 680):
            items.append({"at_s": t0 + m * 60, "kind": "card", "spec": {"type": "status_demand", "sender": "po", "ticket": None,
                          "deadline": t0 / 60 + m + dlo, "payoff": {}, "penalty": dict(d["other_penalty"])}})
    order = {"card": 0, "event": 1, "ping": 2, "call": 3}
    s["x"]["sched"] = sorted(items, key=lambda x: (x["at_s"], order[x["kind"]]))
    s["x"]["boss_live"] = _x_boss_sprint(s, content)
    s["sched_pos"] = 0
    if s["x"]["bounty_card"] == "pending":
        first = next((x for x in s["x"]["sched"] if x["kind"] == "card" and x["spec"]["ticket"]), None)
        if first:
            first["spec"]["bounty"] = True
        s["x"]["bounty_card"] = None
    _emit(s, ev, "sprint_dealt", sprint=k, tickets=picks, boss=s["x"]["boss"] if _x_boss_sprint(s, content) else None)


def _x_fire_schedule(s: dict, ev: list, content: Content) -> None:
    sch = s["x"]["sched"]
    while s["sched_pos"] < len(sch) and sch[s["sched_pos"]]["at_s"] <= s["clock_s"]:
        item = sch[s["sched_pos"]]
        s["sched_pos"] += 1
        if item["kind"] == "event":
            _fire_event(s, ev, content, item["event"])
        elif item["kind"] == "card":
            _spawn_card(s, ev, content, item["spec"])
        elif item["kind"] == "ping":
            _emit(s, ev, "ping_sent", kind=_pick_ping(s, content), sender=item["sender"])
        else:
            _ring(s, ev, content, item["sender"])


def _x_card_spawned(s: dict, content: Content, card: dict, spec: dict) -> None:
    card["bounty"] = bool(spec.get("bounty"))
    card["spot"] = bool(spec.get("spot"))
    if _has(s, "timeboxing"):
        card["deadline_s"] += _fx(s, content, "timeboxing", "deadline_bonus_min") * 60
    if s["clock_s"] < s["x"]["protect_until_s"]:
        card["deadline_s"] = max(card["deadline_s"], s["x"]["protect_until_s"] + 30 * 60)


def _x_boss_sprint(s: dict, content: Content) -> bool:
    return s["sprint"] == _X(content)["boss_sprint"]


def _x_boss_now(s: dict) -> str | None:
    return s["x"]["boss"] if s["x"].get("boss_live") else None


def _x_day_minutes(s: dict, content: Content) -> float:
    m = content.balance["time"]["day_minutes"]
    if "short_days" in s["x"]["heat"]:
        m = _X(content)["heat"]["modifiers"]["short_days"]["day_minutes"]
    if _x_boss_now(s) == "friday_deploy" and s["day"] >= 2:
        m = min(m, _X(content)["bosses"]["friday_deploy"]["day2_minutes"])
    return m


def _x_warnings_lose_at(s: dict, content: Content) -> int:
    if "one_warning" in s["x"]["heat"]:
        return _X(content)["heat"]["modifiers"]["one_warning"]["warnings_lose_at"]
    return content.balance["limits"]["warnings_lose_at"]


def _x_viral_chance(s: dict, content: Content) -> float:
    if "harsh_reviews" in s["x"]["heat"]:
        return _X(content)["heat"]["modifiers"]["harsh_reviews"]["viral_chance"]
    return content.balance["push"]["viral_chance"]


def _x_cost_mult(s: dict, content: Content, key: str) -> float:
    m = 1.0
    if key in ("read", "open_other") and _has(s, "wip_limit"):
        if len(_live(s)) <= _X(content)["practices"]["effects"]["wip_limit"]["max_live"]:
            m *= _fx(s, content, "wip_limit", "open_cost_mult")
    if key == "tutorial" and _has(s, "spike"):
        m *= _fx(s, content, "spike", "tutorial_cost_mult")
    pk = content.balance["perks"]
    if key in ("read", "patch") and "keyboard_warrior" in s["perks"]:
        m *= pk["keyboard_warrior"]["time_mult"]
    if key == "test" and "debug_master" in s["perks"]:
        m *= pk["debug_master"]["test_time_mult"]
    return m


def _x_clock_running(s: dict, content: Content) -> bool:
    c = _X(content)["clock"]
    if c["pause_while_card_open"] and s["open_card"] is not None:
        return False
    if c["pause_while_standup"] and s["pending_standup"]:
        return False
    return True


def _x_context_switch(s: dict, ev: list, content: Content, c: dict) -> None:
    """Q2: Focus is a daily budget; jumping between cards spends it."""
    last = s["x"]["last_card"]
    if last is not None and last != c["id"]:
        cost = _X(content)["focus"]["switch_cost"]
        _meter(s, "focus", -cost, content)
        _emit(s, ev, "focus_switch", card_id=c["id"], focus=-cost)
    s["x"]["last_card"] = c["id"]
    if _has(s, "wip_limit") and len(_live(s)) <= _X(content)["practices"]["effects"]["wip_limit"]["max_live"]:
        _use_practice(s, ev, content, "wip_limit")


def _x_free_run(s: dict, ev: list, content: Content, w: dict) -> bool:
    if _has(s, "tdd_pair"):
        return True
    if not _has(s, "definition_of_done_p"):
        return False
    used = s["x"]["free_runs"].get(w["ticket"], 0)
    if used < _fx(s, content, "definition_of_done_p", "free_runs"):
        s["x"]["free_runs"][w["ticket"]] = used + 1
        _use_practice(s, ev, content, "definition_of_done_p")
        return True
    return False


def _x_may_escalate(s: dict, c: dict) -> bool:
    if s["clock_s"] < s["x"]["protect_until_s"]:
        return False
    if _has(s, "steady_flow") and c["escalation"] >= 1:
        return False
    return True


def _x_tick_world(s: dict, ev: list, content: Content) -> None:
    if _orig(content, "team_board"):
        _team_tick(s, ev, content)
    if s["stage"] != "BUILD":
        return
    X = _X(content)
    sus = X["suspicion"]
    cover = s["meters"]["cover"]
    s["x"]["max_cover"] = max(s["x"]["max_cover"], cover)
    # M11 spot checks while Cover is high
    if cover >= sus["spot_check_from"] and s["clock_s"] >= s["x"]["next_spot_s"] and s["clock_s"] >= s["x"]["protect_until_s"]:
        s["x"]["next_spot_s"] = s["clock_s"] + sus["spot_check_every_min"] * 60
        _spawn_card(s, ev, content, {"type": "status_demand", "sender": "po", "ticket": None, "spot": True,
                                     "deadline": s["clock_s"] / 60 + sus["spot_check_deadline_min"],
                                     "payoff": dict(sus["spot_check_payoff"]), "penalty": dict(sus["spot_check_penalty"])})
        _emit(s, ev, "spot_check", cover=cover)
    if cover >= sus["last_stand_from"] and not s["x"]["last_stand"]:
        s["x"]["last_stand"] = True
        _emit(s, ev, "last_stand", cover=cover)
    # M13 director
    D = X["director"]
    while _feat(s, "director") and s["clock_s"] >= s["x"]["next_director_s"]:
        s["x"]["next_director_s"] += D["every_min"] * 60
        live = len(_live(s))
        if live <= D["quiet_live_max"] and cover < D["quiet_cover_below"]:
            unused = [t for t in sorted(content.tickets) if t not in s["x"]["used_tickets"]]
            d = X["sprint_deal"]
            if unused and draw(s, "director") < 0.5:
                t = unused[int(draw(s, "director") * len(unused)) % len(unused)]
                s["x"]["used_tickets"].append(t)
                spec = {"type": "build" if content.tickets[t]["kind"] == "build" else "fix", "sender": "po", "ticket": t,
                        "deadline": s["clock_s"] / 60 + d["deadline_min"][0], "payoff": dict(d["code_payoff"]), "penalty": dict(d["code_penalty"])}
            else:
                spec = {"type": "status_demand", "sender": "po", "ticket": None,
                        "deadline": s["clock_s"] / 60 + d["deadline_min"][0], "payoff": {}, "penalty": dict(d["other_penalty"])}
            _spawn_card(s, ev, content, spec)
            _emit(s, ev, "director", action="added_work")
        elif live >= D["busy_live_min"] and not s["x"]["relief_used"]:
            s["x"]["relief_used"] = True
            for c in _live(s):
                if c["deadline_s"] is not None:
                    c["deadline_s"] += D["relief_min"] * 60
            _emit(s, ev, "director", action="relief", minutes=D["relief_min"])


def _x_after_push(s: dict, ev: list, content: Content, c: dict, w: dict, result: str) -> None:
    X = _X(content)
    honest = all(w["dod"].values()) and bool(w["last_run"] and w["last_run"]["all_pass"])
    if result == "clean":
        _xlog(s, "clean_push")
        if c.get("bounty"):
            _meter(s, "points", X["comeback"]["bounty_bonus"], content)
            _emit(s, ev, "bounty_paid", card_id=c["id"], points=X["comeback"]["bounty_bonus"])
    if s["x"]["last_stand"] and honest and result in ("clean", "acceptable"):
        drop = X["suspicion"]["clutch_cover_drop"]
        _meter(s, "cover", -drop, content)
        s["x"]["last_stand"] = False
        s["x"]["clutches"] += 1
        _emit(s, ev, "clutch", cover=-drop)
    if result == "security_hole" and _x_boss_now(s) == "auditor" and w["ticket"] not in s["attacked"]:
        b = content.balance
        s["attacked"].append(w["ticket"])
        _meter(s, "rating", b["attack_check"]["rating"], content)
        _meter(s, "points", b["attack_check"]["points"], content)
        _meter(s, "cover", X["bosses"]["auditor"]["attack_cover"], content)
        _emit(s, ev, "attack_check_resolved", ticket=w["ticket"], rating=b["attack_check"]["rating"],
              points=b["attack_check"]["points"], boss="auditor")


def _x_standup_delta(s: dict, ev: list, content: Content, ans: str, delta: float) -> float:
    if ans == "accurate":
        _xlog(s, "accurate_standup")
        if _has(s, "psychological_safety"):
            _use_practice(s, ev, content, "psychological_safety")
    else:
        _xlog(s, "bluff")
        s["x"]["bluffed_this_sprint"] = True
    if ans == "vague" and _x_boss_now(s) == "demo_day":
        delta *= _X(content)["bosses"]["demo_day"]["vague_multiplier"]
    return delta


def _x_tutorial_unlock(s: dict, ev: list, content: Content, tid: str) -> None:
    pid = _X(content)["practices"]["unlocked_by_tutorial"].get(tid)
    if pid:
        _emit(s, ev, "practice_unlocked", practice=pid)


def _x_auto_ship(s: dict, ev: list, content: Content) -> None:
    """M7 (spec-fit version): calling Review while work is still out ships it unreviewed."""
    b = content.balance
    if s["x"].get("release"):
        _ship_release(s, ev, content, auto=True)
    for c in s["pile"]:
        if c["state"] not in ("delegated", "returned"):
            continue
        if c.get("review"):   # O2: a change-by-change submission ships as it stands
            _review_ship(s, ev, content, c, auto=True)
            continue
        if not c["ticket"]:
            c["state"], c["returns_s"] = "done", None
            _apply_payoff(s, c, content)
            continue
        t = _ticket(content, c["ticket"])
        o = _bad_option(t) if c["hidden_bug"] else next(x for x in t["options"] if x["effect"] == "correct_small_flaw")
        if o["effect"] == "crashes":
            continue
        result = RESULT_OF[o["effect"]]
        pts = round(b["push"]["points"][result] * (t["difficulty"] if result in ("clean", "acceptable") else 1))
        _meter(s, "points", pts, content)
        rating = b["push"]["rating"].get(result, 0)
        s["shipped"].append({"ticket": t["id"], "result": result, "effect": o["effect"], "sprint": s["sprint"], "rating": rating,
                             "unreviewed": True})
        c["state"], c["returns_s"] = "done", None
        _emit(s, ev, "pushed", card_id=c["id"], ticket=t["id"], result=result, label=RESULT_LABEL[result], points=pts,
              cover=0, unreviewed=True)


def _x_style_rank(log: list[str], content: Content) -> dict:
    st = _X(content)["style"]
    score = sum(min(log.count(k), 2) for k in st["good"]) - 2 * sum(log.count(k) for k in st["bad"])
    rank = st["ranks"][0][1]
    for at, name in st["ranks"]:
        if score >= at:
            rank = name
    return {"rank": rank, "score": score, "variety": sum(1 for k in st["good"] if k in log)}


def _x_goal(s: dict, content: Content) -> dict:
    G = _X(content)["sprint_goal"]
    target = G["ship_min"][min(s["sprint"] - 1, len(G["ship_min"]) - 1)]
    done = sum(1 for sh in s["shipped"] if sh["sprint"] == s["sprint"] and sh["result"] in ("clean", "acceptable")
               and not sh.get("unreviewed"))
    return {"target": target, "shipped": done, "met": done >= target}


def _x_goal_check(s: dict, ev: list, content: Content) -> None:
    """Sprint goal: ship real work this sprint, or take a demotion warning."""
    G, g = _X(content)["sprint_goal"], _x_goal(s, content)
    s["x"]["goals"].append(g)
    if g["met"]:
        _meter(s, "points", G["hit_points"], content)
        _emit(s, ev, "sprint_goal", met=True, shipped=g["shipped"], target=g["target"], points=G["hit_points"])
    else:
        _meter(s, "cover", G["miss_cover"], content)
        _emit(s, ev, "sprint_goal", met=False, shipped=g["shipped"], target=g["target"], cover=G["miss_cover"])
        s["warnings"] += G["miss_warning"]
        _emit(s, ev, "warning_issued", warnings=s["warnings"], reason="sprint_goal_missed")


def _x_end_sprint(s: dict, ev: list, content: Content) -> None:
    X = _X(content)
    x = s["x"]
    style = _x_style_rank(x["style_log"], content)
    x["style_history"].append(style)
    x["style_log"] = []
    _emit(s, ev, "style_ranked", sprint=s["sprint"], **style)
    if not x["bluffed_this_sprint"] and "no_bluff_sprint" not in x["achievements"]:
        x["achievements"].append("no_bluff_sprint")
        _emit(s, ev, "achievement", name="no_bluff_sprint")
    x["bluffed_this_sprint"] = False
    x["boss_live"] = False
    if s["status"] == "active" and s["meters"]["points"] > 0:
        gain = min(X["shop"]["interest_cap"], int(s["meters"]["points"] * X["shop"]["interest_rate"]))
        if gain:
            _meter(s, "points", gain, content)
            _emit(s, ev, "interest_paid", points=gain)
    if s["status"] == "active" and s["sprint"] >= X["sprints_total"]:
        x["achievements"].append("won")


def _x_begin_sprint(s: dict, ev: list, content: Content) -> None:
    X = _X(content)
    x = s["x"]
    had_practices = _feat(s, "practices")
    _refresh_features(s, ev, content)
    x["retro_uses"], x["relief_used"] = 0, False
    x["next_director_s"] = s["clock_s"] + X["director"]["every_min"] * 60
    C = X["comeback"]
    if s["meters"]["rating"] < C["behind_rating_below"] or s["warnings"] > 0:
        x["bounty_card"] = "pending"
        _meter(s, "focus", C["loss_bonus_focus"], content)
        _emit(s, ev, "comeback_offered", focus=C["loss_bonus_focus"], bounty=C["bounty_bonus"])
    _x_deal_sprint(s, ev, content)
    _x_fire_schedule(s, ev, content)
    if _feat(s, "practices"):
        _x_open_shop(s, ev, content, free=not had_practices)   # the first shop gives one practice free


def _h_configure(s, ev, content, p):
    """Server-only: meta unlocks and the chosen Heat modifiers, before anything happens in the run."""
    if not _exp(content):
        _illegal("experimental mechanics are off")
    if s["x"]["configured"] or s["clock_s"] > 0 or s["stage"] != "PLANNING" or s["sprint"] != 1:
        _illegal("a run can only be configured before it starts")
    X = _X(content)
    unlocks = [u for u in p.get("unlocks", []) if isinstance(u, str)]
    heat = list(dict.fromkeys(p.get("heat", [])))
    if heat and "heat" not in unlocks:
        _illegal("Heat unlocks after your first win")
    for h in heat:
        if h not in X["heat"]["modifiers"]:
            _illegal(f"unknown heat modifier {h}")
    s["x"].update(configured=True, unlocks=unlocks, heat=heat)
    if s["x"]["shop"]:   # the free pick can now include practices unlocked in earlier runs
        s["x"]["shop"]["offers"] = _x_offers(s, content, [])
    _emit(s, ev, "run_configured", unlocks=unlocks, heat=heat)


def _need_planning_shop(s) -> dict:
    if s["stage"] != "PLANNING" or not s["x"]["shop"]:
        _illegal("the shop is only open during planning")
    return s["x"]["shop"]


def _h_buy_practice(s, ev, content, p):
    shop = _need_planning_shop(s)
    X = _X(content)
    off = next((o for o in shop["offers"] if o["id"] == p["practice_id"]), None)
    if not off:
        _illegal("that practice is not on offer")
    if len(s["x"]["practices"]) - sum(1 for d in X["practices"]["duos"] if d in s["x"]["practices"]) >= X["practices"]["slots"]:
        _illegal("all practice slots are full")
    price = 0 if shop["free"] else off["price"]
    if s["meters"]["points"] < price:
        _illegal("not enough points")
    if price:
        _meter(s, "points", -price, content)
    s["x"]["practices"][off["id"]] = {"level": 1, "uses": 0}
    shop["offers"] = [o for o in shop["offers"] if o["id"] != off["id"]]
    _emit(s, ev, "practice_gained", practice=off["id"], price=price)
    for duo, d in X["practices"]["duos"].items():
        if duo not in s["x"]["practices"] and all(n in s["x"]["practices"] for n in d["needs"]):
            s["x"]["practices"][duo] = {"level": 1, "uses": 0}
            _emit(s, ev, "practice_gained", practice=duo, price=0, duo=True)
    if shop["free"]:
        s["x"]["shop"] = None


def _h_reroll_shop(s, ev, content, p):
    shop = _need_planning_shop(s)
    prices = _X(content)["shop"]["reroll_price"]
    price = 0 if shop["free"] and shop["rerolls"] == 0 else prices[min(shop["rerolls"], len(prices) - 1)]
    if s["meters"]["points"] < price:
        _illegal("not enough points to reroll")
    if price:
        _meter(s, "points", -price, content)
    shop["rerolls"] += 1
    keep = [o for o in shop["offers"] if o["locked"]]
    shop["offers"] = _x_offers(s, content, keep)
    _emit(s, ev, "shop_rerolled", price=price, offers=[o["id"] for o in shop["offers"]])


def _h_lock_offer(s, ev, content, p):
    shop = _need_planning_shop(s)
    off = next((o for o in shop["offers"] if o["id"] == p["practice_id"]), None)
    if not off:
        _illegal("that practice is not on offer")
    off["locked"] = not off["locked"]
    s["x"]["kept_offers"] = [o for o in shop["offers"] if o["locked"]]
    _emit(s, ev, "offer_locked", practice=off["id"], locked=off["locked"])


def _h_retro(s, ev, content, p):
    _need_stage(s, "BUILD")
    if not _has(s, "retrospective"):
        _illegal("you do not have the Retrospective practice")
    if s["x"]["retro_uses"] >= _fx(s, content, "retrospective", "uses_per_sprint"):
        _illegal("Retrospective is used up for this sprint")
    c = _card(s, p["card_id"])
    if c["state"] not in ("pile", "returned", "open"):
        _illegal("card cannot be reset")
    s["x"]["retro_uses"] += 1
    c["escalation"] = 0
    c["deadline_s"] = s["clock_s"] + content.balance["escalation"]["interval_min"] * 60
    _use_practice(s, ev, content, "retrospective")
    _emit(s, ev, "card_reset", card_id=c["id"])


def _h_use_ultimate(s, ev, content, p):
    _need_stage(s, "BUILD")
    x, M = s["x"], _X(content)["momentum"]
    if not _feat(s, "momentum"):
        _illegal("special moves unlock later")
    if x["momentum"] < x["momentum_full"]:
        _illegal("momentum is not full yet")
    kind = p["kind"]
    if kind == "protect":
        x["protect_until_s"] = s["clock_s"] + M["protect_min"] * 60
    elif kind == "swarm":
        for c in s["pile"]:
            if c["state"] == "delegated":
                c["hidden_bug"] = False
                _return_delegation(s, ev, content, c)
    elif kind == "retro_now":
        for c in _live(s):
            c["escalation"] = max(0, c["escalation"] - 1)
            if c["deadline_s"] is not None:
                c["deadline_s"] += M["retro_deadline_min"] * 60
    else:
        _illegal("unknown ultimate")
    x["momentum"] = 0
    _emit(s, ev, "ultimate_used", kind=kind)


# ================================================================ ORIGINAL (spec-breaking) mechanics
# Branch experimental/original-mechanics. Each is switched in balance.yaml `originals.<name>.enabled` and
# only runs with the experimental block on. State lives in s["x"].

def _orig(content: Content, name: str) -> bool:
    o = content.balance.get("originals", {}).get(name, {})
    return _exp(content) and bool(o.get("enabled"))


_ORIG_FEATURE = {"action_hand": "hand", "release_train": "release", "score_multiplier": "multiplier"}


def _on(s: dict, content: Content, name: str) -> bool:
    """An original that is enabled AND already introduced to this player."""
    return _orig(content, name) and (name not in _ORIG_FEATURE or _feat(s, _ORIG_FEATURE[name]))


def _O(content: Content, name: str) -> dict:
    return content.balance["originals"][name]


def _o_start(s: dict, ev: list, content: Content) -> None:
    x = s["x"]
    x.update(hand=[], deck=[], discard=[], deck_list={}, release=[], honest_streak=0, trust={}, combo=0, team={}, team_t=s["clock_s"])
    if _orig(content, "team_board"):
        x["team"] = {d: {"task": None, "progress": 0.0, "stuck": False, "stuck_min": 0.0, "nagged": False} for d in ("dev1", "dev2")}
    if _orig(content, "action_hand"):
        x["deck_list"] = dict(_O(content, "action_hand")["starter_deck"])
        x["deck"] = _shuffled(s, [k for k, n in sorted(x["deck_list"].items()) for _ in range(n)])
        if _on(s, content, "action_hand"):
            _new_hand(s, ev, content)
    if _orig(content, "change_review"):
        x["trust"] = {d: _O(content, "change_review")["trust_start"] for d in ("dev1", "dev2")}


# ---- O1 action hand
def _shuffled(s: dict, cards: list) -> list:
    out = list(cards)
    for i in range(len(out) - 1, 0, -1):
        j = int(draw(s, "deck") * (i + 1)) % (i + 1)
        out[i], out[j] = out[j], out[i]
    return out


def _draw_cards(s: dict, n: int) -> list:
    x, got = s["x"], []
    for _ in range(n):
        if not x["deck"]:
            if not x["discard"]:
                break
            x["deck"], x["discard"] = _shuffled(s, x["discard"]), []
        got.append(x["deck"].pop())
    x["hand"] += got
    return got


def _new_hand(s: dict, ev: list, content: Content) -> None:
    x = s["x"]
    x["discard"] += x["hand"]
    x["hand"] = []
    got = _draw_cards(s, _O(content, "action_hand")["hand_size"])
    _emit(s, ev, "hand_drawn", cards=got)


def _play(s: dict, ev: list, content: Content, kind: str) -> None:
    """O1: a move needs a matching action card in your hand; playing it discards it."""
    if not _on(s, content, "action_hand"):
        return
    x = s["x"]
    if kind not in x["hand"]:
        raise GameError("NO_CARD", f"you need a {kind} card in your hand (regroup to draw a new hand)")
    x["hand"].remove(kind)
    x["discard"].append(kind)
    _emit(s, ev, "card_played", kind=kind)


def _draw_after_push(s: dict, ev: list, content: Content) -> None:
    if _on(s, content, "action_hand"):
        got = _draw_cards(s, _O(content, "action_hand")["draw_after_push"])
        if got:
            _emit(s, ev, "cards_drawn", cards=got)


def _spend_min(s: dict, ev: list, content: Content, minutes: float) -> None:
    if _day_used_min(s) + minutes > _day_minutes(s, content) + 1e-9:
        raise GameError("DAY_FULL", "Not enough working hours left today; move on")
    _advance(s, ev, content, minutes * 60, day_capped=False)


def _h_regroup(s, ev, content, p):
    if not _on(s, content, "action_hand"):
        _illegal("the action hand is off")
    _need_stage(s, "BUILD")
    _spend_min(s, ev, content, _O(content, "action_hand")["regroup_min"])
    _new_hand(s, ev, content)


def _deck_shop(s: dict, content: Content) -> None:
    if not _on(s, content, "action_hand"):
        _illegal("the action hand is off")
    shop = _need_planning_shop(s)
    if shop["free"]:
        _illegal("take your free practice first")


def _h_add_card(s, ev, content, p):
    _deck_shop(s, content)
    A, kind = _O(content, "action_hand"), p["kind"]
    if kind not in A["shop_cards"]:
        _illegal("that card is not sold")
    if s["meters"]["points"] < A["add_price"]:
        _illegal("not enough points")
    _meter(s, "points", -A["add_price"], content)
    s["x"]["deck_list"][kind] = s["x"]["deck_list"].get(kind, 0) + 1
    s["x"]["discard"].append(kind)
    _emit(s, ev, "deck_changed", added=kind, price=A["add_price"])


def _h_remove_card(s, ev, content, p):
    _deck_shop(s, content)
    A, kind, x = _O(content, "action_hand"), p["kind"], s["x"]
    if x["deck_list"].get(kind, 0) <= 0:
        _illegal("you have no such card")
    if sum(x["deck_list"].values()) <= A["hand_size"]:
        _illegal("your deck cannot be smaller than a hand")
    if s["meters"]["points"] < A["remove_price"]:
        _illegal("not enough points")
    _meter(s, "points", -A["remove_price"], content)
    x["deck_list"][kind] -= 1
    for pile in ("discard", "deck", "hand"):
        if kind in x[pile]:
            x[pile].remove(kind)
            break
    _emit(s, ev, "deck_changed", removed=kind, price=A["remove_price"])


# ---- O3 score multiplier and O4 release train
def _multiplier(s: dict, content: Content, honest: bool, ps: int | None = None) -> float:
    """Process score (as it stood before this push) plus the honest-push streak."""
    if not _on(s, content, "score_multiplier"):
        return 1.0
    M = _O(content, "score_multiplier")
    streak = s["x"]["honest_streak"] + 1 if honest else 0
    ps = process_score(s, content) if ps is None else ps
    return round(1 + ps * M["process_weight"] + min(M["honest_streak_cap"], streak * M["honest_streak_step"]), 3)


def _release_room(s: dict, content: Content) -> None:
    if _on(s, content, "release_train") and len(s["x"]["release"]) >= _O(content, "release_train")["max_items"]:
        _illegal("the release is full: ship it first")


def _award(s: dict, ev: list, content: Content, pts: int, result: str, ticket: str, honest: bool, ps: int | None = None) -> tuple[int, dict]:
    """Points for a push: O3 multiplies them, O4 holds them in the release until it ships."""
    extra = {}
    if s.get("x") and _on(s, content, "score_multiplier"):
        mult = _multiplier(s, content, honest, ps)
        s["x"]["honest_streak"] = s["x"]["honest_streak"] + 1 if honest else 0
        if pts > 0:
            pts = round(pts * mult)
        extra["mult"] = mult
    if s.get("x") and _on(s, content, "release_train"):
        s["x"]["release"].append({"ticket": ticket, "result": result, "points": pts})
        extra["held"] = True
    else:
        _meter(s, "points", pts, content)
    return pts, extra


def _release_mult(content: Content, n: int) -> float:
    return round(1 + _O(content, "release_train")["bonus_per_extra_item"] * max(0, n - 1), 3)


def _ship_release(s: dict, ev: list, content: Content, auto: bool = False) -> None:
    rel = s["x"]["release"]
    base = sum(i["points"] for i in rel)
    ok = all(i["result"] in ("clean", "acceptable") for i in rel)
    mult = _release_mult(content, len(rel)) if ok else 1.0
    total = round(base * mult) if base > 0 else base
    _meter(s, "points", total, content)
    s["x"]["release"] = []
    _emit(s, ev, "release_shipped", items=len(rel), base=base, mult=mult, points=total, failed=not ok, auto=auto)


def _h_ship_release(s, ev, content, p):
    if not _on(s, content, "release_train"):
        _illegal("the release train is off")
    _need_stage(s, "BUILD")
    if not s["x"]["release"]:
        _illegal("nothing is waiting in the release")
    _spend_min(s, ev, content, _O(content, "release_train")["ship_min"])
    _ship_release(s, ev, content)


# ---- O2 change-by-change review
def _trust_gain(s: dict, ev: list, content: Content, dev: str, key: str, why: str) -> None:
    if not (s.get("x") and _orig(content, "change_review")) or dev not in s["x"]["trust"]:
        return
    R = _O(content, "change_review")
    before = s["x"]["trust"][dev]
    s["x"]["trust"][dev] = min(R["trust_max"], before + R[key])
    if s["x"]["trust"][dev] != before:
        _emit(s, ev, "trust_changed", dev=dev, trust=s["x"]["trust"][dev], why=why)


def _trust_penalty(s: dict, content: Content, dev: str) -> float:
    if not (s.get("x") and _orig(content, "change_review")):
        return 0.0
    R = _O(content, "change_review")
    return (R["trust_max"] - s["x"]["trust"].get(dev, R["trust_max"])) * R["trust_bug_chance_per_point"]


def _make_review(s: dict, content: Content, c: dict) -> None:
    R = _O(content, "change_review")
    n = R["changes"]
    if c["hidden_bug"]:
        lo, hi = R["faulty_if_bugged"]
        k = lo + int(draw(s, "review") * (hi - lo + 1)) % (hi - lo + 1)
    else:
        k = 1 if draw(s, "review") < R["clean_chance_extra"] else 0
    idx = list(range(n))
    faulty = set()
    for _ in range(k):
        faulty.add(idx.pop(int(draw(s, "review") * len(idx)) % len(idx)))
    c["review"] = {"changes": [{"faulty": i in faulty, "shown": None, "fixed": False} for i in range(n)],
                   "faulty_count": k, "inspected": 0}
    c["deadline_s"] = s["clock_s"] + R["review_deadline_min"] * 60
    c["escalation"] = 0


def _review_public(c: dict) -> dict:
    r = c["review"]   # never sends which change is really faulty, only what the player has seen
    return {"faulty_count": r["faulty_count"], "inspected": r["inspected"], "assignee": c.get("assignee"),
            "changes": [{"shown": ch["shown"], "fixed": ch["fixed"], "sure": bool(ch.get("sure"))} for ch in r["changes"]]}


# ---- O6 live team board, O7 combo, O8 surprises
NAMES_PLAIN = {"dev1": "Ines", "dev2": "Tobi", "po": "Marlo"}


def _task_minutes(content: Content, dev: str, c: dict) -> float:
    T = _O(content, "team_board")
    base = T["task_minutes"][str(content.tickets[c["ticket"]]["difficulty"])] if c.get("ticket") else T["other_task_minutes"]
    return base * T["speed"][dev]


def _pick_dev(s: dict, to: str | None) -> str:
    team = s["x"]["team"]
    if to is not None:
        if to not in team:
            _illegal("no such teammate")
        if team[to]["task"]:
            _illegal(f"{NAMES_PLAIN[to]} is busy; wait until they finish")
        return to
    free = [d for d in ("dev1", "dev2") if not team[d]["task"]]
    if not free:
        _illegal("everyone on the team is busy")
    return free[0]


def _assign(s: dict, ev: list, content: Content, dev: str, c: dict) -> None:
    s["x"]["team"][dev].update(task=c["id"], progress=0.0, stuck=False, stuck_min=0.0, nagged=False)
    _emit(s, ev, "dev_started", dev=dev, card_id=c["id"])


def _team_tick(s: dict, ev: list, content: Content) -> None:
    """Teammates work while the game clock moves. They can get stuck; you unblock them."""
    x, T = s["x"], _O(content, "team_board")
    dt = (s["clock_s"] - x.get("team_t", s["clock_s"])) / 60
    x["team_t"] = s["clock_s"]
    if dt <= 0 or s["stage"] != "BUILD":
        return
    for dev, m in x["team"].items():
        if not m["task"]:
            continue
        c = next((k for k in s["pile"] if k["id"] == m["task"]), None)
        if c is None or c["state"] != "delegated":
            m.update(task=None, progress=0.0, stuck=False)
            continue
        if m["stuck"]:
            m["stuck_min"] += dt
            if m["stuck_min"] >= T["stuck_escalate_min"] and not m["nagged"]:
                m["nagged"] = True
                _emit(s, ev, "dev_still_stuck", dev=dev, card_id=c["id"])
                _escalate(s, ev, content, c)
            continue
        if draw(s, "stuck_" + dev) < T["stuck_chance_per_hour"][dev] * min(dt, 60) / 60:
            m.update(stuck=True, stuck_min=0.0, nagged=False)
            _emit(s, ev, "dev_stuck", dev=dev, card_id=c["id"])
            continue
        m["progress"] = min(1.0, m["progress"] + dt / _task_minutes(content, dev, c))
        if m["progress"] >= 1.0:
            m.update(task=None, progress=0.0)
            _emit(s, ev, "dev_done", dev=dev, card_id=c["id"])
            _return_delegation(s, ev, content, c)


def _h_unblock(s, ev, content, p):
    if not _orig(content, "team_board"):
        _illegal("the team board is off")
    _need_stage(s, "BUILD")
    dev = p.get("dev")
    m = s["x"]["team"].get(dev)
    if not m or not m["stuck"]:
        _illegal("they are not stuck")
    T = _O(content, "team_board")
    quick = m["stuck_min"] <= T["quick_unblock_min"]
    _spend_min(s, ev, content, T["unblock_min"])
    m.update(stuck=False, stuck_min=0.0)
    if quick:
        _meter(s, "points", T["quick_bonus_points"], content)
        _emit(s, ev, "quick_save", dev=dev, points=T["quick_bonus_points"])
    _log(s, "blocker_cleared")
    _trust_gain(s, ev, content, dev, "trust_per_coach", "unblocked")
    _emit(s, ev, "dev_unblocked", dev=dev)


def _break_combo(s: dict, ev: list, content: Content, why: str) -> None:
    if _orig(content, "combo") and s["x"].get("combo"):
        _emit(s, ev, "combo_broken", count=s["x"]["combo"], why=why)
        s["x"]["combo"] = 0


def _finish_bonus(s: dict, ev: list, content: Content, c: dict, result: str) -> None:
    """Combo for on-time finishes in a row, plus outage and urgent bonuses."""
    if result not in ("clean", "acceptable"):
        _break_combo(s, ev, content, "something broken reached users")
        return
    on_time = c.get("escalation", 0) == 0 and (c.get("deadline_s") is None or c["deadline_s"] >= s["clock_s"])
    bonus = 0
    if c.get("outage") and not c.get("outage_missed"):
        E = _O(content, "events")
        bonus += E["outage_bonus_points"]
        _meter(s, "rating", E["outage_rating"], content)
        _emit(s, ev, "outage_fixed", card_id=c["id"], points=E["outage_bonus_points"], rating=E["outage_rating"])
    if c.get("urgent") and on_time:
        bonus += _O(content, "events")["urgent_bonus_points"]
    bonus += _speed_bonus(s, ev, content, c)
    _wave_progress(s, ev, content, c, on_time)
    if _orig(content, "combo"):
        C = _O(content, "combo")
        if on_time:
            mult = 1 + min(C["cap"], C["step"] * s["x"]["combo"])
            base = 100 * (content.tickets[c["ticket"]]["difficulty"] if c.get("ticket") else 1)
            extra = round(base * (mult - 1))
            s["x"]["combo"] += 1
            bonus += extra
            _emit(s, ev, "combo", count=s["x"]["combo"], mult=round(mult, 2), points=extra)
        else:
            _break_combo(s, ev, content, "it was late")
    if bonus:
        rel = s["x"].get("release")
        if _on(s, content, "release_train") and rel:
            rel[-1]["points"] += bonus   # the bonus rides with that fix in the release
        else:
            _meter(s, "points", bonus, content)


def _speed_tier(content: Content, w: dict) -> tuple[str, float]:
    S = _O(content, "speed_fix")
    secs = w.get("ms", 0) / 1000 + w.get("misses", 0) * S["miss_penalty_s"]
    return ("perfect" if secs <= S["perfect_s"] else "good" if secs <= S["good_s"] else "slow"), secs


def _speed_bonus(s: dict, ev: list, content: Content, c: dict) -> int:
    """Fixing it yourself FAST pays extra. The timer runs only on real seconds spent with the card open."""
    w = c.get("work")
    if not (_orig(content, "speed_fix") and w and c.get("ticket")):
        return 0
    tier, secs = _speed_tier(content, w)
    S = _O(content, "speed_fix")
    frac = S["perfect_bonus"] if tier == "perfect" else S["good_bonus"] if tier == "good" else 0
    base = 100 * content.tickets[c["ticket"]]["difficulty"]
    pts = round(base * frac)
    _emit(s, ev, "speed_result", card_id=c["id"], tier=tier, seconds=round(secs), points=pts, misses=w.get("misses", 0))
    return pts


def _wave_progress(s: dict, ev: list, content: Content, c: dict, ok: bool) -> None:
    wave = s["x"].get("wave")
    if not wave or not c.get("wave") or wave["failed"]:
        return
    if not ok:
        wave["failed"] = True
        _emit(s, ev, "wave_failed", left=wave["left"])
        return
    wave["left"] -= 1
    if wave["left"] <= 0:
        pts = _O(content, "events")["wave_bonus_points"]
        _meter(s, "points", pts, content)
        s["x"]["wave"] = None
        _emit(s, ev, "wave_clear", points=pts)
    else:
        _emit(s, ev, "wave_progress", left=wave["left"])


def _fire_event(s: dict, ev: list, content: Content, name: str) -> None:
    E = _O(content, "events")
    if name == "wave":
        pool = [t for t in sorted(content.tickets) if t not in s["x"]["used_tickets"]]
        pool += [t for t in sorted(content.tickets) if t not in pool]   # reuse when the fresh ones run out
        ids = []
        for _ in range(E["wave_size"]):
            t = pool.pop(int(draw(s, "wave") * len(pool)) % len(pool))
            spec = {"type": "fix" if content.tickets[t]["kind"] == "fix" else "build", "sender": "po", "ticket": t,
                    "deadline": s["clock_s"] / 60 + E["wave_deadline_min"], "payoff": {"points": 100}, "penalty": {"cover": 3}}
            _spawn_card(s, ev, content, spec)
            s["pile"][-1]["wave"] = True
            ids.append(s["pile"][-1]["id"])
        s["x"]["wave"] = {"ids": ids, "left": len(ids), "failed": False}
        _emit(s, ev, "wave", ids=ids, minutes=E["wave_deadline_min"], points=E["wave_bonus_points"])
        return
    if name == "outage":
        unused = [t for t in sorted(content.tickets) if t not in s["x"]["used_tickets"]] or sorted(content.tickets)
        t = unused[int(draw(s, "outage") * len(unused)) % len(unused)]
        s["x"]["used_tickets"].append(t)
        spec = {"type": "fix", "sender": "po", "ticket": t, "deadline": s["clock_s"] / 60 + E["outage_deadline_min"],
                "payoff": {"points": 100}, "penalty": {"cover": 3}}
        _spawn_card(s, ev, content, spec)
        s["pile"][-1]["outage"] = True
        _emit(s, ev, "outage", card_id=s["pile"][-1]["id"], ticket=t, minutes=E["outage_deadline_min"])
    elif name == "urgent":
        cands = [c for c in _live(s) if c["state"] == "pile" and c["ticket"] and not c.get("urgent") and not c.get("outage")]
        if not cands:
            return
        c = cands[int(draw(s, "urgent") * len(cands)) % len(cands)]
        c["urgent"] = True
        c["deadline_s"] = min(c["deadline_s"] or 1e12, s["clock_s"] + E["urgent_deadline_min"] * 60)
        _emit(s, ev, "urgent", card_id=c["id"], minutes=E["urgent_deadline_min"], points=E["urgent_bonus_points"])


def _review_card(s: dict, content: Content, p: dict) -> tuple[dict, dict]:
    if not _orig(content, "change_review"):
        _illegal("change-by-change review is off")
    _need_stage(s, "BUILD")
    c = _card(s, p["card_id"])
    if c["state"] != "returned" or not c.get("review"):
        _illegal("this card has no submission to review")
    return c, c["review"]


def _h_review_inspect(s, ev, content, p):
    c, r = _review_card(s, content, p)
    R, i, tool = _O(content, "change_review"), p["index"], p["tool"]
    if not 0 <= i < len(r["changes"]):
        _illegal("no such change")
    ch = r["changes"][i]
    if ch.get("sure"):
        _illegal("you already know this change for certain")
    if tool == "test":
        _play(s, ev, content, "test")
        shown = "faulty" if ch["faulty"] else "ok"
        _spend_min(s, ev, content, R["inspect_min"])
    elif tool == "ask":
        dev = c.get("assignee", "dev1")
        if s["x"]["trust"].get(dev, 0) <= 0:
            _illegal("they will not answer more questions; trust is gone")
        shown = "faulty" if ch["faulty"] else "ok"
        s["x"]["trust"][dev] -= 1
        _spend_min(s, ev, content, R["ask_min"])
        _emit(s, ev, "trust_changed", dev=dev, trust=s["x"]["trust"][dev])
    elif tool == "assistant":
        if "ai_assistant" not in s["perks"]:
            _illegal("you do not own the AI Assistant")
        _play(s, ev, content, "assist")
        truth = ch["faulty"]
        if content.balance["assistant_flaky"] and draw(s, "assistant_error") < content.balance["perks"]["ai_assistant"]["error_rate"]:
            truth = not truth   # the assistant is wrong about 1 time in 5
        shown = "faulty" if truth else "ok"
        _spend(s, ev, content, "assistant")
    else:
        _illegal("unknown tool")
    ch["shown"] = shown
    ch["sure"] = tool != "assistant"   # tests and the author tell the truth; the assistant may not
    r["inspected"] += 1
    _emit(s, ev, "change_inspected", card_id=c["id"], index=i, tool=tool, shown=shown)


def _h_review_fix(s, ev, content, p):
    c, r = _review_card(s, content, p)
    i = p["index"]
    if not 0 <= i < len(r["changes"]) or r["changes"][i]["shown"] != "faulty" or r["changes"][i]["fixed"]:
        _illegal("only a change you found faulty can be fixed")
    _play(s, ev, content, "work")
    _spend_min(s, ev, content, _O(content, "change_review")["fix_min"])
    r["changes"][i]["fixed"] = True
    _emit(s, ev, "change_fixed", card_id=c["id"], index=i)


def _review_ship(s: dict, ev: list, content: Content, c: dict, auto: bool = False) -> None:
    b, t, r = content.balance, _ticket(content, c["ticket"]), c["review"]
    left = any(ch["faulty"] and not ch["fixed"] for ch in r["changes"])
    o = _bad_option(t) if left else next(x for x in t["options"] if x["effect"] == "correct")
    result = "runtime_error" if o["effect"] == "crashes" else RESULT_OF[o["effect"]]
    if result == "runtime_error":
        result = "buggy"
    # a submission known to have no faulty changes needs no further checks: shipping it is a review
    reviewed = not auto and (r["inspected"] > 0 or r["faulty_count"] == 0)
    k = s["repeat_counts"].get(result, 0) if result in ("clean", "acceptable") else 0
    factor = b["push"]["repeat_decay"] ** k
    pts = round(b["push"]["points"][result] * (t["difficulty"] if result in ("clean", "acceptable") else 1) * factor)
    if result in ("clean", "acceptable"):
        s["repeat_counts"][result] = k + 1
    ps_before = process_score(s, content)
    if reviewed:
        _log(s, "review_before_push")
    honest = reviewed and not left
    pts, extra = _award(s, ev, content, pts, result, t["id"], honest, ps_before)
    s["shipped"].append({"ticket": t["id"], "result": result, "effect": o["effect"], "sprint": s["sprint"],
                         "rating": b["push"]["rating"].get(result, 0), **({} if reviewed else {"unreviewed": True})})
    c["state"], c["returns_s"] = "done", None
    _emit(s, ev, "pushed", card_id=c["id"], ticket=t["id"], result=result, label=RESULT_LABEL[result], points=pts, cover=0,
          review=True, unreviewed=not reviewed, **extra)
    if s.get("x") and result == "clean":
        _xlog(s, "clean_push")
    if reviewed and not left and r["faulty_count"] > 0:
        _trust_gain(s, ev, content, c.get("assignee", "dev1"), "trust_per_clean_review", "fair_review")
    if not auto:
        _finish_bonus(s, ev, content, c, result)


def _h_review_ship(s, ev, content, p):
    c, r = _review_card(s, content, p)
    _release_room(s, content)
    _spend(s, ev, content, "push")
    _review_ship(s, ev, content, c)
    _draw_after_push(s, ev, content)


def _h_review_send_back(s, ev, content, p):
    c, r = _review_card(s, content, p)
    c.pop("review")
    c["state"] = "delegated"
    c["hidden_bug"] = draw(s, "delegation_bug") < _bug_chance(s, content) / 2
    c["returns_s"] = s["clock_s"] + content.balance["delegation"]["return_after_min"] * 30
    _spend_min(s, ev, content, _O(content, "change_review")["send_back_min"])
    _emit(s, ev, "card_sent_back", card_id=c["id"], returns_s=c["returns_s"])


def _o_public(s: dict, content: Content) -> dict:
    x, out = s["x"], {}
    if _on(s, content, "action_hand"):
        A = _O(content, "action_hand")
        out["hand"] = {"cards": x["hand"], "deck": len(x["deck"]), "discard": len(x["discard"]), "deck_list": x["deck_list"],
                       "regroup_min": A["regroup_min"], "shop_cards": A["shop_cards"], "add_price": A["add_price"], "remove_price": A["remove_price"]}
    if _on(s, content, "score_multiplier"):
        out["mult"] = {"next_honest": _multiplier(s, content, True), "next_other": _multiplier(s, content, False), "streak": x["honest_streak"]}
    if _on(s, content, "release_train"):
        rel = x["release"]
        out["release"] = {"items": rel, "base": sum(i["points"] for i in rel), "mult": _release_mult(content, len(rel)),
                          "next_mult": _release_mult(content, len(rel) + 1), "max": _O(content, "release_train")["max_items"],
                          "ship_min": _O(content, "release_train")["ship_min"]}
    if _orig(content, "change_review"):
        R = _O(content, "change_review")
        out["review"] = {"trust": x["trust"], "trust_max": R["trust_max"], "inspect_min": R["inspect_min"], "ask_min": R["ask_min"],
                         "fix_min": R["fix_min"]}
    out["leaderboard"] = _orig(content, "leaderboard")
    if _orig(content, "team_board"):
        T = _O(content, "team_board")
        team = {}
        for d, m in x["team"].items():
            c = next((k for k in s["pile"] if k["id"] == m["task"]), None)
            mins = _task_minutes(content, d, c) if c else 0
            team[d] = {"task": m["task"], "title": (content.tickets[c["ticket"]]["title"] if c and c["ticket"] else c and c["type"]),
                       "progress": round(m["progress"], 3), "eta_min": round((1 - m["progress"]) * mins) if c else None,
                       "stuck": m["stuck"], "stuck_min": round(m["stuck_min"]), "speed": T["speed"][d], "bug_chance": T["bug_chance"][d]}
        out["team"] = team
        out["unblock_min"] = T["unblock_min"]
        out["stuck_limit"] = T["stuck_escalate_min"]
        out["quick_min"] = T["quick_unblock_min"]
        wv = x.get("wave")
        out["wave"] = {"left": wv["left"], "total": len(wv["ids"]), "failed": wv["failed"]} if wv else None
    if _orig(content, "combo"):
        C = _O(content, "combo")
        out["combo"] = {"count": x["combo"], "next_mult": round(1 + min(C["cap"], C["step"] * x["combo"]), 2)}
    return out
    return out


def _x_public(s: dict, content: Content) -> dict:
    X, x, b = _X(content), s["x"], content.balance
    costs = {k: round(_cost(s, content, k), 1) for k in b["costs_min"]}
    window = X["intents_window_min"] * 60
    names = {"po": "Marlo", "dev1": "Ines", "dev2": "Tobi"}
    intents = []
    for item in x["sched"][s["sched_pos"]:]:
        dt = item["at_s"] - s["clock_s"]
        if dt > window:
            break
        if item["kind"] == "event":
            continue   # surprises stay surprises
        who = names.get(item.get("sender") or item["spec"]["sender"], "Someone")
        if item["kind"] == "call":
            text = f"{who} will call you"
        elif item["kind"] == "ping":
            text = f"{who} will message you"   # whether it is a clue, noise or a trap stays hidden
        else:
            sp = item["spec"]
            text = {"fix": f"{who} will report a bug", "build": f"{who} will ask for a new feature",
                    "help_call": f"{who} will ask for help", "status_demand": f"{who} will want a status update"}[sp["type"]]
        intents.append({"in_min": round(dt / 60), "text": text, "kind": item["kind"]})
    shop = None
    if x["shop"]:
        prices = X["shop"]["reroll_price"]
        sh = x["shop"]
        shop = {"free": sh["free"], "offers": sh["offers"],
                "reroll_price": 0 if sh["free"] and sh["rerolls"] == 0 else prices[min(sh["rerolls"], len(prices) - 1)]}
    style = _x_style_rank(x["style_log"], content)
    boss_sprint = X["boss_sprint"]
    return {"sprints_total": X["sprints_total"], "boss": x["boss"], "boss_sprint": boss_sprint, "goal": _x_goal(s, content),
            "boss_live": bool(x.get("boss_live")), "clock_running": s["stage"] == "BUILD" and _x_clock_running(s, content),
            "move_costs": costs, "day_minutes": _day_minutes(s, content), "intents": intents,
            "practices": [{"id": k, **v} for k, v in x["practices"].items()], "slots": X["practices"]["slots"],
            "shop": shop, "momentum": x["momentum"], "momentum_full": x["momentum_full"],
            "protected_min": max(0, round((x["protect_until_s"] - s["clock_s"]) / 60)),
            "retro_left": (_fx(s, content, "retrospective", "uses_per_sprint") - x["retro_uses"]) if _has(s, "retrospective") else 0,
            "last_stand": x["last_stand"], "max_cover": x["max_cover"], "style": style, "heat": x["heat"],
            "process_score": process_score(s, content),
            "next_clean_factor": round(b["push"]["repeat_decay"] ** s["repeat_counts"].get("clean", 0), 3),
            "prices": {"standup": dict(b["standup_cover"]), "unticked_box": b["push"]["dod_unticked_cover"],
                       "contradiction_cover": b["contradiction_cover"],
                       "vague_multiplier": X["bosses"]["demo_day"]["vague_multiplier"] if _x_boss_now(s) == "demo_day" else 1},
            "bug_odds": round(_bug_chance(s, content), 3), "focus_switch_cost": X["focus"]["switch_cost"],
            "standup_timer_s": X["bosses"]["demo_day"]["standup_timer_s"] if _x_boss_now(s) == "demo_day" else None,
            "seed": s["seed"], "features": x.get("features", list(FEATURES)),
            "perk_shop": [{"id": k, "price": v["price"]} for k, v in content.balance["perks"].items()],
            "unlocks_next": [f for f in _features_for(s["sprint"] + 1, content) if f not in x.get("features", FEATURES)],
            **_o_public(s, content)}


HANDLERS = {"open_card": _h_open_card, "flag_line": _h_flag_line, "select_patch": _h_select_patch,
            "run_script": _h_run_script, "toggle_dod": _h_toggle_dod, "push": _h_push, "hold": _h_hold,
            "triage_reorder": _h_triage_reorder, "delegate": _h_delegate, "coach": _h_coach, "defer": _h_defer,
            "reply_standup": _h_reply_standup, "answer_call": _h_answer_call, "watch_tutorial": _h_watch_tutorial,
            "buy_perk": _h_buy_perk, "use_assistant": _h_use_assistant, "advance_stage": _h_advance_stage,
            "tick": _h_tick, "configure": _h_configure, "buy_practice": _h_buy_practice, "reroll_shop": _h_reroll_shop,
            "lock_offer": _h_lock_offer, "retro": _h_retro, "use_ultimate": _h_use_ultimate,
            "regroup": _h_regroup, "add_card": _h_add_card, "remove_card": _h_remove_card,
            "review_inspect": _h_review_inspect, "review_fix": _h_review_fix, "review_ship": _h_review_ship,
            "review_send_back": _h_review_send_back, "ship_release": _h_ship_release, "unblock": _h_unblock}
EXPERIMENTAL_ONLY = ("configure", "buy_practice", "reroll_shop", "lock_offer", "retro", "use_ultimate", "regroup", "add_card",
                     "remove_card", "review_inspect", "review_fix", "review_ship", "review_send_back", "ship_release", "unblock")


def apply(state: dict, command: dict, content: Content) -> tuple[dict, list[dict]]:
    """command = {"type": str, "payload": dict}. Raises GameError; never mutates `state`."""
    if state["status"] != "active":
        raise GameError("ILLEGAL_COMMAND", "the run has ended")
    h = HANDLERS.get(command.get("type"))
    if command.get("type") in EXPERIMENTAL_ONLY and not state.get("x"):
        h = None
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
    out = {"ending": s["ending"], "status": s["status"], "rating": m["rating"], "cover": m["cover"], "points": m["points"],
           "process_score": ps, "gap": rating_pct - ps, "shipped": [x["result"] for x in s["shipped"]]}
    if s.get("x"):
        out["x"] = _x_debrief(s, content)
    return out


def _x_debrief(s: dict, content: Content) -> dict:
    X, x = _X(content), s["x"]
    story = X["story"]
    lines = [story[s["ending"]]] if s["ending"] in story else []
    log = s["process_log"]
    if x["clutches"]:
        lines.append(story["clutch"])
    if any(sh["result"] == "security_hole" for sh in s["shipped"]):
        lines.append(story["shipped_hole"])
    if "coach" in log:
        lines.append(story["coached"])
    if "dod_skipped" in log:
        lines.append(story["skipped_dod"])
    if "no_bluff_sprint" in x["achievements"]:
        lines.append(story["honest"])
    else:
        lines.append(story["bluffed"])
    heat = len(x["heat"])
    run_score = round(s["meters"]["points"] * (1 + X["heat"]["bonus_per_level"] * heat))
    return {"sprints_played": len(x["style_history"]), "style": x["style_history"], "max_cover": x["max_cover"],
            "near_miss": x["max_cover"] >= X["suspicion"]["last_stand_from"], "clutches": x["clutches"],
            "story": lines[:4], "heat": x["heat"], "run_score": run_score, "practices": list(x["practices"]),
            "achievements": x["achievements"], "boss": x["boss"], "seed": s["seed"], "goals": x["goals"]}


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
                         "last_run": w["last_run"], "assistant": w["assistant"],
                         "speed": _speed_public(s, content, w),
                         "scan": (None if "security_scan" not in s["perks"] or not w["selected"] else
                                  ("hole" if _option(t, w["selected"])["effect"] == "security_hole" else "clear"))}
    st = s["pending_standup"]
    standup = None
    if st:
        choices = ["vague", "wrong"] + (["accurate"] if _accurate_ok(s, st) else [])
        standup = {"n": st["n"], "ticket": st["ticket"], "teammate": st["teammate"], "choices": choices}
    return {"status": s["status"], "ending": s["ending"], "sprint": s["sprint"], "stage": s["stage"], "day": s["day"],
            "clock_min": round(s["clock_s"] / 60, 1), "day_used_min": round(_day_used_min(s), 1),
            "meters": s["meters"], "warnings": s["warnings"], "open_card": s["open_card"], "work": open_work,
            "standup": standup, "call": s["call"], "unlocked": s["unlocked"], "perks": s["perks"],
            "pile": [{"id": c["id"], "type": c["type"], "sender": c["sender"], "ticket": c["ticket"],
                      "title": content.tickets[c["ticket"]]["title"] if c["ticket"] else None,
                      "state": c["state"], "escalation": c["escalation"], "payoff": c["payoff"], "penalty": c["penalty"],
                      "deadline_min": None if c["deadline_s"] is None else round(c["deadline_s"] / 60, 1),
                      **({"review": _review_public(c)} if c.get("review") else {}),
                      **(_x_card_public(s, c) if s.get("x") else {})}
                     for c in s["pile"]],
            **({"x": _x_public(s, content)} if s.get("x") else {})}


def _speed_public(s: dict, content: Content, w: dict):
    if not (s.get("x") and _orig(content, "speed_fix")):
        return None
    S = _O(content, "speed_fix")
    tier, secs = _speed_tier(content, w)
    return {"ms": w.get("ms", 0), "misses": w.get("misses", 0), "tier": tier, "seconds": round(secs, 1),
            "perfect_s": S["perfect_s"], "good_s": S["good_s"], "penalty_s": S["miss_penalty_s"]}


def _x_card_public(s: dict, c: dict) -> dict:
    out = {"bounty": c.get("bounty", False), "spot": c.get("spot", False), "outage": c.get("outage", False), "urgent": c.get("urgent", False), "wave": c.get("wave", False),
           "assignee": c.get("assignee")}
    if c["state"] in ("delegated", "returned") and c["ticket"] and _has(s, "tdd_pair"):
        out["bug_known"] = c["hidden_bug"]   # TDD Pair: you can tell whether returned work is bugged
    return out
