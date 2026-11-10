"""Experimental engagement mechanics (branch experimental/engagement-mechanics).

IDs follow Spec/Engagement Research.md section 6 (M1..M21). The MVP tests run with these switched off.
"""
import copy

import pytest

from fixit import bot
from fixit.rules import reducer
from fixit.rules.reducer import GameError


def run(s, c, typ, **payload):
    return reducer.apply(s, {"type": typ, "payload": payload}, c)


def fresh(c, seed=3, buy=None):
    s, _ = reducer.start_run(seed, c)
    if buy:
        s["x"]["practices"][buy] = {"level": 1, "uses": 0}
    s["x"]["shop"] = None
    return s


def to_build(c, seed=3, buy=None):
    s = fresh(c, seed, buy)
    s, _ = run(s, c, "advance_stage", to="STANDUP")
    s, _ = run(s, c, "reply_standup", answer="vague")
    s, _ = run(s, c, "advance_stage", to="BUILD")
    return s


def add_card(s, ticket, cid="z1", state="pile", deadline_min=10_000):
    s["pile"].append({"id": cid, "type": "fix", "sender": "po", "ticket": ticket, "deadline_s": deadline_min * 60.0,
                      "escalation": 0, "state": state, "payoff": {}, "penalty": {"cover": 3}, "work": None,
                      "hidden_bug": False, "returns_s": None, "bounty": False, "spot": False})
    return cid


def ship(s, c, cid, effect="correct", dod=True, honest=True):
    t = c.tickets[next(x["ticket"] for x in s["pile"] if x["id"] == cid)]
    s, _ = run(s, c, "open_card", card_id=cid)
    if t["kind"] == "fix":
        s, _ = run(s, c, "flag_line", line_no=t["buggy_line"])
    s, _ = run(s, c, "select_patch", option_id=next(o["id"] for o in t["options"] if o["effect"] == effect))
    if honest:
        s, _ = run(s, c, "run_script")
    if dod:
        for b in reducer.DOD:
            s, _ = run(s, c, "toggle_dod", box=b)
    return run(s, c, "push")


# ---------------------------------------------------------------- switch and determinism
def test_X_off_means_original_game(content):
    s, _ = reducer.start_run(1, content)
    assert "x" not in s and "x" not in reducer.public_state(s, content)
    with pytest.raises(GameError):
        run(s, content, "buy_practice", practice_id="timeboxing")


def test_X_same_seed_same_run(xcontent):
    for pol in bot.POLICIES:
        assert len({bot.play(42, xcontent, pol).digest() for _ in range(3)}) == 1


def test_X_bot_can_win_and_lose_over_three_sprints(xcontent):
    assert bot.play(1, xcontent, "coach_delegate").s["ending"] == "win"
    assert bot.play(1, xcontent, "reckless").s["ending"].startswith("lose")


# ---------------------------------------------------------------- Q4 hybrid clock, Q2 Focus
def test_X_clock_pauses_while_a_card_is_open(xcontent):
    s = to_build(xcontent)
    cid = add_card(s, "final_price")
    t0 = s["clock_s"]
    s, _ = run(s, xcontent, "tick", real_ms=5000)
    assert s["clock_s"] > t0                      # standing at the Pile: time runs
    s, _ = run(s, xcontent, "open_card", card_id=cid)
    t1 = s["clock_s"]
    s, _ = run(s, xcontent, "tick", real_ms=5000)
    assert s["clock_s"] == t1                     # reading code: paused
    assert reducer.public_state(s, xcontent)["x"]["clock_running"] is False


def test_X_focus_switch_cost_and_daily_refill(xcontent):
    s = to_build(xcontent)
    a, b = add_card(s, "final_price", "a1"), add_card(s, "average_rating", "b1")
    f0 = s["meters"]["focus"]
    s, _ = run(s, xcontent, "open_card", card_id=a)
    s, _ = run(s, xcontent, "hold")
    s, _ = run(s, xcontent, "open_card", card_id=b)
    assert s["meters"]["focus"] == f0 - xcontent.balance["experimental"]["focus"]["switch_cost"]
    s, _ = run(s, xcontent, "hold")
    s["meters"]["focus"] = 20
    s, _ = run(s, xcontent, "advance_stage", to="STANDUP")
    assert s["meters"]["focus"] == 20 + xcontent.balance["experimental"]["focus"]["day_refill"]


# ---------------------------------------------------------------- M5 seeded sprints, M8 intents
def test_M5_seeds_deal_different_sprints_without_repeating_tickets(xcontent):
    deals = set()
    for seed in range(6):
        s, _ = reducer.start_run(seed, xcontent)
        deals.add(tuple(sorted(s["x"]["used_tickets"])))
        assert len(s["x"]["used_tickets"]) == len(set(s["x"]["used_tickets"]))
        assert all(xcontent.tickets[t]["difficulty"] == 1 for t in s["x"]["used_tickets"])
    assert len(deals) > 1


def test_M8_intents_never_reveal_ping_kind(xcontent):
    s = to_build(xcontent)
    x = reducer.public_state(s, xcontent)["x"]
    assert x["intents"], "something should be coming up"
    for i in x["intents"]:
        assert "trap" not in i["text"] and "clue" not in i["text"]


# ---------------------------------------------------------------- M1, M2, M4, M9 visible prices
def test_M1_move_costs_include_focus_and_practices(xcontent):
    s = to_build(xcontent, buy="spike")
    x = reducer.public_state(s, xcontent)["x"]
    assert x["move_costs"]["tutorial"] == xcontent.balance["costs_min"]["tutorial"] * 0.5
    s["meters"]["focus"] = 10
    x = reducer.public_state(s, xcontent)["x"]
    assert x["move_costs"]["read"] == xcontent.balance["costs_min"]["read"] * 1.5


def test_M2_bug_odds_shown_and_halved_by_pair_programming(xcontent):
    s = to_build(xcontent)
    assert reducer.public_state(s, xcontent)["x"]["bug_odds"] == xcontent.balance["delegation"]["hidden_bug_chance"]
    s = to_build(xcontent, buy="pair_programming")
    assert reducer.public_state(s, xcontent)["x"]["bug_odds"] == xcontent.balance["delegation"]["hidden_bug_chance"] * 0.5


def test_M4_process_score_and_decay_visible_but_points_table_unchanged(xcontent):
    s = to_build(xcontent)
    cid = add_card(s, "final_price")
    p0 = s["meters"]["points"]
    s, ev = ship(s, xcontent, cid)
    pushed = next(e for e in ev if e["type"] == "pushed")
    assert pushed["points"] == xcontent.balance["push"]["points"]["clean"]
    x = reducer.public_state(s, xcontent)["x"]
    assert x["next_clean_factor"] == xcontent.balance["push"]["repeat_decay"]
    assert x["process_score"] == reducer.process_score(s, xcontent)
    assert s["meters"]["points"] == p0 + pushed["points"]


# ---------------------------------------------------------------- M3 practices and duos, M12 shop
def test_M3_definition_of_done_makes_first_run_free(xcontent):
    s = to_build(xcontent, buy="definition_of_done_p")
    cid = add_card(s, "final_price")
    s, _ = run(s, xcontent, "open_card", card_id=cid)
    t = s["clock_s"]
    s, _ = run(s, xcontent, "run_script")
    assert s["clock_s"] == t
    s, _ = run(s, xcontent, "run_script")
    assert s["clock_s"] > t


def test_M3_backlog_refinement_defer_does_not_escalate(xcontent):
    s = to_build(xcontent, buy="backlog_refinement")
    cid = add_card(s, "final_price")
    s, _ = run(s, xcontent, "defer", card_id=cid)
    assert next(c for c in s["pile"] if c["id"] == cid)["escalation"] == 0


def test_M3_psychological_safety_offers_accurate_without_tutorial(xcontent):
    s = fresh(xcontent, buy="psychological_safety")
    s, _ = run(s, xcontent, "advance_stage", to="STANDUP")
    assert "accurate" in reducer.public_state(s, xcontent)["standup"]["choices"]
    s, _ = run(s, xcontent, "reply_standup", answer="accurate")


def test_M3_duo_granted_and_practices_evolve(xcontent):
    s = fresh(xcontent)
    s["meters"]["points"] = 1000
    s["x"]["shop"] = {"free": False, "rerolls": 0, "offers": [{"id": "definition_of_done_p", "price": 100, "locked": False},
                                                             {"id": "pair_programming", "price": 100, "locked": False}]}
    s, _ = run(s, xcontent, "buy_practice", practice_id="definition_of_done_p")
    s, ev = run(s, xcontent, "buy_practice", practice_id="pair_programming")
    assert "tdd_pair" in s["x"]["practices"] and s["meters"]["points"] == 800
    s2 = to_build(xcontent, buy="definition_of_done_p")
    tickets = ["final_price", "average_rating", "shipping_fee", "stock_status", "points_balance"]
    for n in range(xcontent.balance["experimental"]["practices"]["evolve_at"]):
        cid = add_card(s2, tickets[n], f"e{n}")
        s2, _ = run(s2, xcontent, "open_card", card_id=cid)
        s2, ev = run(s2, xcontent, "run_script")
        s2, _ = run(s2, xcontent, "hold")
    assert s2["x"]["practices"]["definition_of_done_p"]["level"] == 2


def test_M12_shop_free_pick_reroll_lock_and_slots(xcontent):
    s, _ = reducer.start_run(4, xcontent)
    shop = s["x"]["shop"]
    assert shop["free"] and len(shop["offers"]) == 3
    locked = shop["offers"][0]["id"]
    s, _ = run(s, xcontent, "lock_offer", practice_id=locked)
    s, _ = run(s, xcontent, "reroll_shop")                     # first reroll of the free pick is free
    assert locked in [o["id"] for o in s["x"]["shop"]["offers"]]
    with pytest.raises(GameError):
        run(s, xcontent, "reroll_shop")                        # second costs points you do not have
    s, _ = run(s, xcontent, "buy_practice", practice_id=locked)
    assert locked in s["x"]["practices"] and s["x"]["shop"] is None and s["meters"]["points"] == 0
    s2 = fresh(xcontent)
    for p in ["timeboxing", "wip_limit", "swarming", "sustainable_pace", "spike"]:
        s2["x"]["practices"][p] = {"level": 1, "uses": 0}
    s2["x"]["shop"] = {"free": True, "rerolls": 0, "offers": [{"id": "backlog_refinement", "price": 0, "locked": False}]}
    with pytest.raises(GameError, match="slots"):
        run(s2, xcontent, "buy_practice", practice_id="backlog_refinement")


def test_M12_shop_closes_when_planning_ends(xcontent):
    s, _ = reducer.start_run(4, xcontent)
    s, _ = run(s, xcontent, "advance_stage", to="STANDUP")
    assert s["x"]["shop"] is None


# ---------------------------------------------------------------- M6 bosses
def boss_build(c, boss):
    s = to_build(c)
    s["x"]["boss"], s["x"]["boss_live"] = boss, True
    return s


def test_M6_friday_deploy_blocks_unticked_push(xcontent):
    s = boss_build(xcontent, "friday_deploy")
    cid = add_card(s, "final_price")
    with pytest.raises(GameError, match="Friday"):
        ship(s, xcontent, cid, dod=False)


def test_M6_auditor_attacks_a_shipped_hole_at_once(xcontent):
    s = boss_build(xcontent, "auditor")
    cid = add_card(s, "find_user")
    r0 = s["meters"]["rating"]
    s, ev = ship(s, xcontent, cid, effect="security_hole")
    assert any(e["type"] == "attack_check_resolved" for e in ev)
    assert s["meters"]["rating"] < r0


def test_M6_demo_day_doubles_vague_cost_and_times_the_standup(xcontent):
    s = fresh(xcontent)
    s["x"]["boss"], s["x"]["boss_live"] = "demo_day", True
    s, _ = run(s, xcontent, "advance_stage", to="STANDUP")
    assert reducer.public_state(s, xcontent)["x"]["standup_timer_s"] == 20
    c0 = s["meters"]["cover"]
    s, _ = run(s, xcontent, "reply_standup", answer="vague")
    assert s["meters"]["cover"] == c0 + 2 * xcontent.balance["standup_cover"]["vague"]


# ---------------------------------------------------------------- M7 auto-ship, M10 style, M11 suspicion
def test_M7_review_ships_unreviewed_delegated_work(xcontent):
    s = to_build(xcontent)
    cid = add_card(s, "final_price", state="delegated")
    s["pile"][-1]["hidden_bug"] = True
    s["day"] = 2
    s, ev = run(s, xcontent, "advance_stage", to="REVIEW")
    auto = [e for e in ev if e["type"] == "pushed" and e.get("unreviewed")]
    assert auto and auto[0]["result"] == "buggy"


def test_M10_style_rank_rewards_variety_and_never_changes_points(xcontent):
    lazy = reducer._x_style_rank(["dod_honest"] * 6, xcontent)
    varied = reducer._x_style_rank(["dod_honest", "coach", "standup_held", "review_before_push", "clean_push"], xcontent)
    assert varied["score"] > lazy["score"] and lazy["rank"] in ("D", "C")
    assert reducer._x_style_rank(["coach", "bluff", "dod_skipped"], xcontent)["rank"] == "D"


def test_M11_spot_checks_last_stand_and_clutch(xcontent):
    s = to_build(xcontent)
    s["meters"]["cover"] = 91
    s, ev = run(s, xcontent, "tick", real_ms=2000)
    types = [e["type"] for e in ev]
    assert "spot_check" in types and "last_stand" in types and s["x"]["last_stand"]
    cid = add_card(s, "final_price")
    s, ev = ship(s, xcontent, cid)
    assert any(e["type"] == "clutch" for e in ev)
    assert s["meters"]["cover"] < 91 and not s["x"]["last_stand"]
    assert reducer.debrief(s, xcontent)["x"]["max_cover"] >= 91


# ---------------------------------------------------------------- M13 director, M14 comeback, M21 ultimate
def test_M13_director_adds_work_when_quiet_and_relief_when_busy(xcontent):
    s = to_build(xcontent)
    s["pile"] = []
    s["x"]["sched"] = []
    s["sched_pos"] = 0
    n0 = len(s["pile"])
    for _ in range(12):
        s, _ = run(s, xcontent, "tick", real_ms=5000)
    assert len(s["pile"]) > n0
    s = to_build(xcontent)
    for i in range(5):
        add_card(s, "final_price", f"b{i}", deadline_min=s["clock_s"] / 60 + 500)
    s["x"]["next_director_s"] = s["clock_s"]
    s, ev = run(s, xcontent, "tick", real_ms=100)
    assert any(e["type"] == "director" and e["action"] == "relief" for e in ev)


def test_M14_comeback_bounty_when_behind(xcontent):
    s = to_build(xcontent)
    s, _ = ship(s, xcontent, add_card(s, "final_price"))   # meet the sprint goal so the run continues
    s["meters"]["rating"] = 2.6
    s["day"] = 2
    s, ev = run(s, xcontent, "advance_stage", to="REVIEW")
    assert any(e["type"] == "comeback_offered" for e in ev)
    assert any(item["kind"] == "card" and item["spec"].get("bounty") for item in s["x"]["sched"])


def test_M21_ultimate_needs_full_momentum(xcontent):
    s = to_build(xcontent)
    with pytest.raises(GameError):
        run(s, xcontent, "use_ultimate", kind="protect")
    s["x"]["momentum"] = s["x"]["momentum_full"]
    cid = add_card(s, "final_price", deadline_min=s["clock_s"] / 60 + 1)
    s, _ = run(s, xcontent, "use_ultimate", kind="protect")
    assert s["x"]["momentum"] == 0
    for _ in range(5):
        s, _ = run(s, xcontent, "tick", real_ms=5000)
    assert next(c for c in s["pile"] if c["id"] == cid)["escalation"] == 0


def test_M21_momentum_fills_from_good_process(xcontent):
    s = to_build(xcontent)
    cid = add_card(s, "final_price")
    s, _ = ship(s, xcontent, cid)
    assert s["x"]["momentum"] >= xcontent.balance["experimental"]["momentum"]["gain"]["dod_honest"]


# ---------------------------------------------------------------- M16 meta, M17 heat, M18 story
def test_M17_heat_requires_unlock_and_changes_rules(xcontent):
    s, _ = reducer.start_run(2, xcontent)
    with pytest.raises(GameError, match="first win"):
        run(s, xcontent, "configure", heat=["one_warning"])
    s, _ = run(s, xcontent, "configure", unlocks=["heat"], heat=["one_warning", "no_assistant"])
    with pytest.raises(GameError):
        run(s, xcontent, "configure", unlocks=["heat"], heat=[])
    s["meters"]["points"] = 999
    with pytest.raises(GameError, match="Heat"):
        run(s, xcontent, "buy_perk", perk_id="ai_assistant")
    s["warnings"] = 1
    s2, ev = run(s, xcontent, "advance_stage", to="STANDUP")
    assert s2["ending"] == "lose_warnings"


def test_M16_unlocks_widen_the_shop_pool(xcontent):
    s, _ = reducer.start_run(2, xcontent)
    assert "psychological_safety" not in reducer._x_pool(s, xcontent)
    s, _ = run(s, xcontent, "configure", unlocks=["psychological_safety"], heat=[])
    assert "psychological_safety" in reducer._x_pool(s, xcontent)


def test_M18_debrief_tells_the_story(xcontent):
    b = bot.play(1, xcontent, "coach_delegate")
    d = reducer.debrief(b.s, xcontent)["x"]
    assert d["story"][0] == xcontent.balance["experimental"]["story"]["win"]
    assert d["run_score"] == b.s["meters"]["points"] and d["sprints_played"] == 3


# ---------------------------------------------------------------- API: challenge codes, Heat, meta unlocks
def test_X_api_challenge_heat_and_server_only_configure(tmp_path, xcontent):
    from api_helpers import Driver, Env
    e = Env(tmp_path, xcontent)
    c = e.signup("x@test.io")
    r = c.post("/api/v1/runs", json={"challenge": 4242})
    assert r.status_code == 201, r.text
    st = r.json()["state"]
    assert st["x"]["seed"] == 4242 and st["x"]["shop"]["free"]
    run_id = r.json()["id"]
    d = Driver(c, run_id)
    assert d.cmd("configure", unlocks=["heat"], heat=["one_warning"]).status_code == 403
    locked = c.post("/api/v1/runs", json={"heat": ["one_warning"]})
    assert locked.status_code in (400, 409, 422) and "first win" in locked.text
    r2 = c.post("/api/v1/runs", json={"challenge": 4242})
    assert r2.json()["state"]["x"]["intents"] == st["x"]["intents"]     # same code, same sprint
    assert c.get("/api/v1/me/unlocks").json() == {"unlocks": [], "heat": []}
    # replay after a restart rebuilds the configured run
    from fixit.api.app import create_app
    e.app = create_app(e.db, xcontent, settings=e.settings, now=lambda: e.clock[0])
    c2 = e.client()
    c2.cookies = c.cookies
    c2.headers.update(c.headers)
    assert c2.get(f"/api/v1/runs/{run_id}/state").json()["state"]["x"]["seed"] == 4242


# ---------------------------------------------------------------- sprint goals
def idle_sprint(s, c):
    """A player who only clicks through the stages and ships nothing."""
    for typ, payload in (("advance_stage", {"to": "STANDUP"}), ("reply_standup", {"answer": "vague"}), ("advance_stage", {"to": "BUILD"}),
                         ("advance_stage", {"to": "STANDUP"}), ("reply_standup", {"answer": "vague"}), ("advance_stage", {"to": "BUILD"}),
                         ("advance_stage", {"to": "REVIEW"})):
        s, _ = run(s, c, typ, **payload)
    return s


def test_GOAL_doing_nothing_loses(xcontent):
    for seed in range(6):
        s = fresh(xcontent, seed)
        for _ in range(xcontent.balance["experimental"]["sprints_total"]):
            if s["status"] != "active":
                break
            s["x"]["shop"] = None
            s = idle_sprint(s, xcontent)
        assert s["ending"] != "win", seed


def test_GOAL_missed_goal_warns_and_met_goal_pays(xcontent):
    s = to_build(xcontent)
    s["day"] = 2
    s2, ev = run(s, xcontent, "advance_stage", to="REVIEW")
    goal = next(e for e in ev if e["type"] == "sprint_goal")
    assert not goal["met"] and s2["warnings"] >= 1
    s = to_build(xcontent)
    cid = add_card(s, "final_price")
    s, _ = ship(s, xcontent, cid)
    assert reducer.public_state(s, xcontent)["x"]["goal"]["met"]
    s["day"] = 2
    p0 = s["meters"]["points"]
    s, ev = run(s, xcontent, "advance_stage", to="REVIEW")
    assert next(e for e in ev if e["type"] == "sprint_goal")["met"]
    assert s["meters"]["points"] >= p0 + xcontent.balance["experimental"]["sprint_goal"]["hit_points"]


def test_GOAL_unreviewed_auto_ships_do_not_count(xcontent):
    s = to_build(xcontent)
    add_card(s, "final_price", state="delegated")
    s["day"] = 2
    s, ev = run(s, xcontent, "advance_stage", to="REVIEW")
    assert any(e.get("unreviewed") for e in ev if e["type"] == "pushed")
    assert not next(e for e in ev if e["type"] == "sprint_goal")["met"]
