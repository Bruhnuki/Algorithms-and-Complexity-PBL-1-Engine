"""Original (spec-breaking) mechanics, branch experimental/original-mechanics. See Spec/Original Mechanics.md."""
import pytest

from fixit import bot
from fixit.rules import reducer
from fixit.rules.reducer import GameError


def run(s, c, typ, **payload):
    return reducer.apply(s, {"type": typ, "payload": payload}, c)


def to_build(c, seed=3, hand=None):
    s, _ = reducer.start_run(seed, c)
    s["x"]["shop"] = None
    s, _ = run(s, c, "advance_stage", to="STANDUP")
    s, _ = run(s, c, "reply_standup", answer="vague")
    s, _ = run(s, c, "advance_stage", to="BUILD")
    if hand is not None:
        s["x"]["hand"] = list(hand)
    return s


def add_card(s, ticket, cid="z1", state="pile"):
    s["pile"].append({"id": cid, "type": "fix", "sender": "dev1", "ticket": ticket, "deadline_s": 10_000 * 60.0,
                      "escalation": 0, "state": state, "payoff": {}, "penalty": {}, "work": None,
                      "hidden_bug": False, "returns_s": None, "bounty": False, "spot": False})
    return cid


def ship(s, c, cid):
    t = c.tickets[next(x["ticket"] for x in s["pile"] if x["id"] == cid)]
    s, _ = run(s, c, "open_card", card_id=cid)
    if t["kind"] == "fix":
        s, _ = run(s, c, "flag_line", line_no=t["buggy_line"])
    s, _ = run(s, c, "select_patch", option_id=next(o["id"] for o in t["options"] if o["effect"] == "correct"))
    s, _ = run(s, c, "run_script")
    for b in reducer.DOD:
        s, _ = run(s, c, "toggle_dod", box=b)
    return run(s, c, "push")


# ---------------------------------------------------------------- switches and determinism
def test_O_off_by_switch(xcontent):
    s, _ = reducer.start_run(1, xcontent)
    assert "hand" not in reducer.public_state(s, xcontent)["x"]
    with pytest.raises(GameError):
        run(s, xcontent, "regroup")


def test_O_deterministic_and_winnable(ocontent, bcontent):
    assert len({bot.play(42, ocontent, "solo").digest() for _ in range(3)}) == 1
    # winnable the way players meet it: mechanics introduced one sprint at a time
    assert any(bot.play(seed, bcontent, "solo").s["ending"] == "win" for seed in range(1, 13))
    assert bot.play(1, ocontent, "reckless").s["ending"].startswith("lose")


# ---------------------------------------------------------------- O1 action hand
def test_O1_moves_need_a_card_and_regroup_draws_a_new_hand(ocontent):
    s = to_build(ocontent, hand=["test"])
    cid = add_card(s, "final_price")
    with pytest.raises(GameError) as e:
        run(s, ocontent, "open_card", card_id=cid)
    assert e.value.code == "NO_CARD"
    t0 = s["clock_s"]
    s, ev = run(s, ocontent, "regroup")
    assert len(s["x"]["hand"]) == ocontent.balance["originals"]["action_hand"]["hand_size"]
    assert s["clock_s"] - t0 >= ocontent.balance["originals"]["action_hand"]["regroup_min"] * 60
    s["x"]["hand"] = ["work"]
    s, ev = run(s, ocontent, "open_card", card_id=cid)
    assert s["x"]["hand"] == [] and "work" in s["x"]["discard"]


def test_O1_deck_shop_adds_and_removes_cards(ocontent):
    s, _ = reducer.start_run(2, ocontent)
    with pytest.raises(GameError, match="free practice"):
        run(s, ocontent, "add_card", kind="work")
    s["x"]["shop"]["free"] = False
    s["meters"]["points"] = 100
    s, _ = run(s, ocontent, "add_card", kind="work")
    assert s["x"]["deck_list"]["work"] == 5 and s["meters"]["points"] == 60
    s, _ = run(s, ocontent, "remove_card", kind="defer")
    assert s["x"]["deck_list"]["defer"] == 1 and s["meters"]["points"] == 30


# ---------------------------------------------------------------- O2 change-by-change review
def returned(s, c, bugged=True):
    cid = add_card(s, "final_price", "r1", state="returned")
    card = s["pile"][-1]
    card["hidden_bug"], card["assignee"] = bugged, "dev1"
    reducer._make_review(s, c, card)
    return cid, card


def test_O2_count_is_known_but_not_which_change(ocontent):
    s = to_build(ocontent)
    cid, card = returned(s, ocontent)
    pub = next(c for c in reducer.public_state(s, ocontent)["pile"] if c["id"] == cid)["review"]
    assert pub["faulty_count"] >= 1
    assert all("faulty" not in ch for ch in pub["changes"])          # the truth never reaches the browser
    with pytest.raises(GameError):
        run(s, ocontent, "open_card", card_id=cid)                   # no code reading for returned work


def test_O2_inspect_fix_ship_clean_and_unreviewed_ship_is_buggy(ocontent):
    s = to_build(ocontent, hand=["test"] * 5 + ["work"] * 3)
    cid, card = returned(s, ocontent)
    for i, ch in enumerate(card["review"]["changes"]):
        s, _ = run(s, ocontent, "review_inspect", card_id=cid, index=i, tool="test")
        cur = next(c for c in s["pile"] if c["id"] == cid)["review"]["changes"][i]
        if cur["shown"] == "faulty":
            s, _ = run(s, ocontent, "review_fix", card_id=cid, index=i)
    s, ev = run(s, ocontent, "review_ship", card_id=cid)
    assert next(e for e in ev if e["type"] == "pushed")["result"] == "clean"
    s2 = to_build(ocontent)
    cid2, _ = returned(s2, ocontent)
    s2, ev = run(s2, ocontent, "review_ship", card_id=cid2)
    assert next(e for e in ev if e["type"] == "pushed")["result"] in ("buggy", "security_hole")


def test_O2_asking_costs_trust_and_trust_raises_bug_chance(ocontent):
    s = to_build(ocontent)
    cid, _ = returned(s, ocontent)
    before = s["x"]["trust"]["dev1"]
    s, _ = run(s, ocontent, "review_inspect", card_id=cid, index=0, tool="ask")
    assert s["x"]["trust"]["dev1"] == before - 1
    assert reducer._trust_penalty(s, ocontent, "dev1") > reducer._trust_penalty(s, ocontent, "dev2")


# ---------------------------------------------------------------- O3 multiplier, O4 release train
def test_O3_honest_streak_and_process_multiply_points(ocontent):
    s = to_build(ocontent, hand=["work", "test"] * 4)
    m1 = reducer.public_state(s, ocontent)["x"]["mult"]["next_honest"]
    assert m1 > 1
    s, ev = ship(s, ocontent, add_card(s, "final_price"))
    pushed = next(e for e in ev if e["type"] == "pushed")
    assert pushed["mult"] == m1 and pushed["points"] == round(100 * m1)
    assert s["x"]["honest_streak"] == 1


def test_O4_release_holds_points_until_shipped_and_rewards_size(ocontent):
    s = to_build(ocontent, hand=["work", "test"] * 6)
    p0 = s["meters"]["points"]
    for i, t in enumerate(["final_price", "shipping_fee"]):
        s, _ = ship(s, ocontent, add_card(s, t, f"q{i}"))
    assert s["meters"]["points"] == p0 and len(s["x"]["release"]) == 2
    base = sum(i["points"] for i in s["x"]["release"])
    s, ev = run(s, ocontent, "ship_release")
    shipped = next(e for e in ev if e["type"] == "release_shipped")
    assert not shipped["failed"] and shipped["points"] == round(base * 1.25)
    assert s["meters"]["points"] == p0 + shipped["points"]


def test_O4_a_bad_item_loses_the_release_bonus_and_review_ships_leftovers(ocontent):
    s = to_build(ocontent)
    s["x"]["release"] = [{"ticket": "a", "result": "clean", "points": 100}, {"ticket": "b", "result": "buggy", "points": 20}]
    s, ev = run(s, ocontent, "ship_release")
    shipped = next(e for e in ev if e["type"] == "release_shipped")
    assert shipped["failed"] and shipped["points"] == 120
    s["x"]["release"] = [{"ticket": "a", "result": "clean", "points": 100}]
    s["day"] = 2
    s, ev = run(s, ocontent, "advance_stage", to="REVIEW")
    assert any(e["type"] == "release_shipped" and e["auto"] for e in ev)


# ---------------------------------------------------------------- rebalance: delegating with review must pay off (spec G2)
def test_REBAL_trust_rebuilds_through_coaching_standups_and_fair_reviews(ocontent):
    R = ocontent.balance["originals"]["change_review"]
    s = to_build(ocontent, hand=["coach"])
    s["x"]["trust"]["dev2"] = 1
    s["pile"].append({"id": "h1", "type": "help_call", "sender": "dev2", "ticket": None, "deadline_s": 1e7, "escalation": 0,
                      "state": "pile", "payoff": {}, "penalty": {}, "work": None, "hidden_bug": False, "returns_s": None})
    s, _ = run(s, ocontent, "coach", card_id="h1")
    assert s["x"]["trust"]["dev2"] == 1 + R["trust_per_coach"]
    s, _ = run(s, ocontent, "advance_stage", to="STANDUP")
    assert s["x"]["trust"]["dev2"] == 1 + R["trust_per_coach"] + R["trust_daily_recovery"]


def test_REBAL_returned_work_gets_a_fresh_deadline_and_zero_fault_ship_counts(ocontent):
    s = to_build(ocontent)
    cid, card = returned(s, ocontent, bugged=False)
    card["review"]["faulty_count"] = 0
    for ch in card["review"]["changes"]:
        ch["faulty"] = False
    assert card["deadline_s"] >= s["clock_s"] + ocontent.balance["originals"]["change_review"]["review_deadline_min"] * 60 - 1
    s, ev = run(s, ocontent, "review_ship", card_id=cid)
    pushed = next(e for e in ev if e["type"] == "pushed")
    assert pushed["result"] == "clean" and not pushed["unreviewed"]
    assert reducer.public_state(s, ocontent)["x"]["goal"]["shipped"] == 1


def test_REBAL_coaching_and_delegating_beats_doing_it_all(ocontent):
    seeds = range(1, 13)
    team = [bot.play(n, ocontent, "coach_delegate").s for n in seeds]
    solo = [bot.play(n, ocontent, "solo").s for n in seeds]
    wins = lambda runs: sum(r["ending"] == "win" for r in runs)
    assert wins(team) >= wins(solo)
    assert sum(reducer.process_score(r, ocontent) for r in team) > sum(reducer.process_score(r, ocontent) for r in solo)


# ---------------------------------------------------------------- beginner onboarding: one idea at a time
def finish_sprint(s, c):
    for typ, pl in (("advance_stage", {"to": "STANDUP"}), ("reply_standup", {"answer": "vague"}), ("advance_stage", {"to": "BUILD"}),
                    ("advance_stage", {"to": "STANDUP"}), ("reply_standup", {"answer": "vague"}), ("advance_stage", {"to": "BUILD"}),
                    ("advance_stage", {"to": "REVIEW"})):
        s, _ = run(s, c, typ, **pl)
    return s


def test_ONBOARD_sprint_1_is_only_the_basics(bcontent):
    s, _ = reducer.start_run(4, bcontent)
    x = reducer.public_state(s, bcontent)["x"]
    # the live team board is the core loop, so handing work to the team is there from the start
    assert x["features"] == ["delegate"] and "hand" not in x and "release" not in x and "mult" not in x and x["shop"] is None
    assert set(x["unlocks_next"]) >= {"practices", "intents"}
    s, _ = run(s, bcontent, "advance_stage", to="STANDUP")
    s, _ = run(s, bcontent, "reply_standup", answer="vague")
    s, _ = run(s, bcontent, "advance_stage", to="BUILD")
    cid = add_card(s, "final_price")
    s, ev = ship(s, bcontent, cid)                     # no cards needed in sprint 1
    pushed = next(e for e in ev if e["type"] == "pushed")
    combo = sum(e["points"] for e in ev if e["type"] in ("combo", "speed_result"))
    assert "held" not in pushed and "mult" not in pushed and s["meters"]["points"] == pushed["points"] + combo


def test_ONBOARD_teamwork_in_sprint_2_advanced_systems_in_sprint_3(bcontent):
    s, _ = reducer.start_run(4, bcontent)
    s["warnings"] = -5                                 # survive the idle sprints of this test
    s = finish_sprint(s, bcontent)
    assert s["sprint"] == 2 and set(s["x"]["features"]) >= {"delegate", "practices", "intents"}
    assert "hand" not in s["x"]["features"] and s["x"]["shop"]["free"]
    s["x"]["shop"] = None
    s = finish_sprint(s, bcontent)
    assert s["sprint"] == 3 and {"hand", "release", "multiplier", "momentum"} <= set(s["x"]["features"])
    s, _ = run(s, bcontent, "advance_stage", to="STANDUP")
    assert len(s["x"]["hand"]) == bcontent.balance["originals"]["action_hand"]["hand_size"]


def test_ONBOARD_bots_still_win_with_onboarding(bcontent):
    assert any(bot.play(n, bcontent, "coach_delegate").s["ending"] == "win" for n in (1, 2, 3))


# ---------------------------------------------------------------- live team board, combo, surprises
def test_TEAM_teammates_work_get_stuck_and_hand_work_back(ocontent):
    s = to_build(ocontent, hand=["delegate"] * 3)
    cid = add_card(s, "final_price")
    s, ev = run(s, ocontent, "delegate", card_id=cid, to="dev1")
    assert s["x"]["team"]["dev1"]["task"] == cid
    with pytest.raises(GameError, match="busy"):
        run(s, ocontent, "delegate", card_id=add_card(s, "shipping_fee", "z2"), to="dev1")
    s["x"]["team"]["dev1"]["stuck"] = True
    p0 = s["x"]["team"]["dev1"]["progress"]
    s, _ = run(s, ocontent, "tick", real_ms=5000)
    assert s["x"]["team"]["dev1"]["progress"] == p0          # stuck teammates make no progress
    s, ev = run(s, ocontent, "unblock", dev="dev1")
    assert not s["x"]["team"]["dev1"]["stuck"] and "blocker_cleared" in s["process_log"]
    for _ in range(60):
        if next(c for c in s["pile"] if c["id"] == cid)["state"] == "returned":
            break
        s["x"]["team"]["dev1"]["stuck"] = False
        s, _ = run(s, ocontent, "tick", real_ms=5000)
    assert next(c for c in s["pile"] if c["id"] == cid)["state"] == "returned" and s["x"]["team"]["dev1"]["task"] is None


def test_COMBO_on_time_finishes_build_a_combo_and_lateness_breaks_it(ocontent):
    s = to_build(ocontent, hand=["work", "test"] * 6)
    s["x"]["release"] = []
    for i, t in enumerate(["final_price", "shipping_fee"]):
        s, ev = ship(s, ocontent, add_card(s, t, f"k{i}"))
    assert s["x"]["combo"] == 2
    late = add_card(s, "stock_status", "late")
    next(c for c in s["pile"] if c["id"] == late)["escalation"] = 1
    s, ev = ship(s, ocontent, late)
    assert s["x"]["combo"] == 0 and any(e["type"] == "combo_broken" for e in ev)


def test_EVENTS_outage_pays_when_fixed_and_hurts_when_missed(ocontent):
    s = to_build(ocontent, hand=["work", "test"] * 4)
    reducer._fire_event(s, [], ocontent, "outage")
    card = s["pile"][-1]
    assert card["outage"]
    r0 = s["meters"]["rating"]
    s2, ev = ship(s, ocontent, card["id"])
    assert any(e["type"] == "outage_fixed" for e in ev) and s2["meters"]["rating"] > r0
    card["deadline_s"] = s["clock_s"]
    s3, ev = run(s, ocontent, "tick", real_ms=1000)
    assert any(e["type"] == "outage_missed" for e in ev) and s3["meters"]["rating"] < r0


# ---------------------------------------------------------------- speed-fix, quick rescue, bug waves
def test_SPEED_real_seconds_on_the_open_card_decide_the_bonus(ocontent):
    def fix(secs, wrong=0):
        s = to_build(ocontent, hand=["work", "test"] * 6)
        cid = add_card(s, "final_price")
        s, _ = run(s, ocontent, "open_card", card_id=cid)
        t0 = s["clock_s"]
        for _ in range(int(secs / 5)):
            s, _ = run(s, ocontent, "tick", real_ms=5000)
        assert s["clock_s"] == t0                         # the world waits while you read
        for _ in range(wrong):
            s, _ = run(s, ocontent, "flag_line", line_no=1)
        t = ocontent.tickets["final_price"]
        s, _ = run(s, ocontent, "flag_line", line_no=t["buggy_line"])
        s, _ = run(s, ocontent, "select_patch", option_id=next(o["id"] for o in t["options"] if o["effect"] == "correct"))
        s, _ = run(s, ocontent, "run_script")
        for b in reducer.DOD:
            s, _ = run(s, ocontent, "toggle_dod", box=b)
        s, ev = run(s, ocontent, "push")
        return next(e for e in ev if e["type"] == "speed_result"), ev
    perfect, _ = fix(15)
    good, _ = fix(40)
    slow, _ = fix(90)
    assert (perfect["tier"], good["tier"], slow["tier"]) == ("perfect", "good", "slow")
    assert perfect["points"] > good["points"] > slow["points"] == 0
    missed, ev = fix(15, wrong=2)                          # two wrong lines add 16 s of penalty
    assert missed["tier"] == "good" and missed["misses"] == 2


def test_SPEED_a_wrong_line_breaks_the_combo(ocontent):
    s = to_build(ocontent, hand=["work"] * 3)
    s["x"]["combo"] = 3
    s, _ = run(s, ocontent, "open_card", card_id=add_card(s, "final_price"))
    s, ev = run(s, ocontent, "flag_line", line_no=1)
    assert s["x"]["combo"] == 0 and any(e["type"] == "combo_broken" and e["why"] == "wrong line" for e in ev)
    assert reducer.public_state(s, ocontent)["work"]["speed"]["misses"] == 1


def test_RESCUE_a_quick_unblock_pays_a_bonus_a_slow_one_does_not(ocontent):
    for stuck_min, pays in ((5, True), (30, False)):
        s = to_build(ocontent, hand=["delegate"] * 2)
        s, _ = run(s, ocontent, "delegate", card_id=add_card(s, "final_price"), to="dev1")
        s["x"]["team"]["dev1"].update(stuck=True, stuck_min=stuck_min)
        p0 = s["meters"]["points"]
        s, ev = run(s, ocontent, "unblock", dev="dev1")
        assert any(e["type"] == "quick_save" for e in ev) == pays
        assert (s["meters"]["points"] - p0 == ocontent.balance["originals"]["team_board"]["quick_bonus_points"]) == pays
    assert reducer.public_state(s, ocontent)["x"]["stuck_limit"] == ocontent.balance["originals"]["team_board"]["stuck_escalate_min"]


def test_WAVE_clear_all_on_time_for_a_bonus_and_one_louder_card_fails_it(ocontent):
    s = to_build(ocontent, hand=["work", "test"] * 8)
    s["pile"] = []
    reducer._fire_event(s, [], ocontent, "wave")
    ids = [c["id"] for c in s["pile"]]
    size = ocontent.balance["originals"]["events"]["wave_size"]
    assert len(ids) == size and all(c["wave"] for c in s["pile"])
    assert reducer.public_state(s, ocontent)["x"]["wave"] == {"left": size, "total": size, "failed": False}
    p0 = s["meters"]["points"]
    for cid in ids:
        s, ev = ship(s, ocontent, cid)
    assert any(e["type"] == "wave_clear" for e in ev) and reducer.public_state(s, ocontent)["x"]["wave"] is None
    assert s["meters"]["points"] - p0 >= ocontent.balance["originals"]["events"]["wave_bonus_points"]   # pushes wait in the release; the bonus is banked at once
    s2 = to_build(ocontent, hand=["work", "test"] * 8)
    s2["pile"] = []
    reducer._fire_event(s2, [], ocontent, "wave")
    wave_cards = [c for c in s2["pile"]]
    wave_cards[0]["deadline_s"] = s2["clock_s"]
    s2, ev = run(s2, ocontent, "tick", real_ms=1000)
    assert any(e["type"] == "wave_failed" for e in ev) and reducer.public_state(s2, ocontent)["x"]["wave"]["failed"]
