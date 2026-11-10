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


def test_O_deterministic_and_winnable(ocontent):
    assert len({bot.play(42, ocontent, "solo").digest() for _ in range(3)}) == 1
    assert any(bot.play(seed, ocontent, "solo").s["ending"] == "win" for seed in (1, 5, 13))
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
    s, _ = run(s, ocontent, "review_inspect", card_id=cid, index=0, tool="ask")
    assert s["x"]["trust"]["dev1"] == ocontent.balance["originals"]["change_review"]["trust_start"] - 1
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


# ---------------------------------------------------------------- O5 leaderboard
def test_O5_leaderboard_ranks_finished_runs_by_challenge_code(tmp_path, ocontent):
    from api_helpers import Driver, Env
    e = Env(tmp_path, ocontent)
    names = []
    for n, pol in enumerate(("solo", "reckless")):
        c = e.signup(f"p{n}@test.io", name=f"Player{n}")
        r = c.post("/api/v1/runs", json={"challenge": 777})
        d = Driver(c, r.json()["id"])
        b = bot.Bot(777, ocontent, pol)
        b.s, _ = reducer.apply(b.s, {"type": "configure", "payload": {"unlocks": [], "heat": []}}, ocontent)
        b.play()
        for cmd in b.log:
            assert d.cmd(cmd["type"], **cmd["payload"]).status_code == 200
        names.append(c)
    lb = names[0].get("/api/v1/leaderboard?seed=777").json()
    assert lb["players"] == 2 and lb["top"][0]["score"] >= lb["top"][1]["score"]
    assert lb["your_best"]["name"] == "Player0" and lb["median"] is not None
    assert names[0].get("/api/v1/leaderboard?seed=1").json()["players"] == 0
