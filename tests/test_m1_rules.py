import copy
import json
import time
from dataclasses import replace

import jsonschema
import pytest
from hypothesis import given, settings, strategies as st

from conftest import add_card, run, ship, to_build
from fixit import bot
from fixit.engines import e1, e2
from fixit.rules import content as cm, interp, reducer
from fixit.rules.reducer import GameError


# ---------------------------------------------------------------- content / CODE-1, CODE-2
def test_CODE1_all_tickets_validate_schema(content):
    assert {"final_price", "average_rating", "find_user", "total_with_tax"} <= set(content.tickets)
    for t in content.tickets.values():
        assert 5 <= len(t["source"]) <= 15
        assert 3 <= len(t["options"]) <= 4
        assert t["glossary"] and t["concept"]


def test_CODE1_bad_ticket_fails_validation(content):
    bad = dict(content.tickets["final_price"], source=["x"])
    schema = json.loads((cm.ROOT / "schemas" / "ticket.schema.json").read_text())
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_CODE2_one_correct_option(content):
    for t in content.tickets.values():
        assert [o["effect"] for o in t["options"]].count("correct") == 1


def test_CODE2_wrong_options_have_bug_type(content):
    for t in content.tickets.values():
        for o in t["options"]:
            assert (o["bug_type"] is None) == (o["effect"] == "correct")


def test_CODE2_mvp_ticket_set(content):
    # experimental branch adds 6 tickets for seeded sprints; the MVP schedule still uses exactly these 4
    assert {"final_price", "average_rating", "find_user", "total_with_tax"} <= set(content.tickets)
    assert {c["ticket"] for c in content.balance["schedule"]["cards"] if c["ticket"]} == {
        "final_price", "average_rating", "find_user", "total_with_tax"}
    assert content.tickets["total_with_tax"]["kind"] == "build"


# ---------------------------------------------------------------- interpreter
def _outcome(runs):
    return "error" if any(r["error"] for r in runs) else "pass" if all(r["pass"] for r in runs) else "fail"


def test_INTERP_golden_outputs_all_options(content):
    for t in content.tickets.values():
        for o in t["options"]:
            outcome = _outcome(cm.run_ticket(t, o, content))
            assert outcome == o["run_outcome"], (t["id"], o["id"])
            if o["effect"] == "crashes":
                assert outcome == "error"
            elif o["effect"] == "wrong_hidden":
                assert outcome == ("fail" if t["run_shows_failure"] else "pass")
            else:
                assert outcome == "pass"
        assert _outcome(cm.run_ticket(t, None, content)) == t["original_outcome"], t["id"]


FRAGS = ["function", "f", "(", ")", "{", "}", "return", "if", "else", "x", "=", "==", "1", "0", "+", "-", "*", "/",
         '"a"', "while", "clean", ",", "import", "__", "\n", "'", "$", "9" * 30]


@given(st.lists(st.sampled_from(FRAGS), max_size=40))
@settings(max_examples=300, deadline=None)
def test_INTERP_terminates_property(frags):
    try:
        interp.call(" ".join(frags), [1], allowed={"function", "return", "if", "else"}, step_limit=500)
    except interp.ScrumError:
        pass


def test_INTERP_step_limit_and_no_imports():
    allowed = {"function", "return", "if", "else"}
    with pytest.raises(interp.ScrumError):
        interp.call("function f(x) { while x == 1 { return 1 } }", [1], allowed=allowed)
    with pytest.raises(interp.ScrumError):
        interp.call("function f(x) { return __import__ }", [1], allowed=allowed)
    with pytest.raises(interp.ScrumError):
        interp.call("function f(x) { return 1 / 0 }", [1], allowed=allowed)


# ---------------------------------------------------------------- CODE-3
def test_CODE3_security_ticket_passes_runs(content):
    t = content.tickets["find_user"]
    hole = next(o for o in t["options"] if o["effect"] == "security_hole")
    runs = cm.run_ticket(t, hole, content)
    assert len(runs) == 5 and all(r["pass"] for r in runs)


def test_CODE3_five_runs_plain_english(content):
    s = to_build(content)
    s, _ = run(s, content, "open_card", card_id="c1")
    s, ev = run(s, content, "run_script")
    runs = ev[0]["runs"]
    assert len(runs) == 5
    assert all(r["text"].startswith("Run ") and ("Pass." in r["text"] or "Fail." in r["text"]) for r in runs)
    assert ev[0]["all_pass"] is False  # the original buggy source fails the doc's examples


# ---------------------------------------------------------------- CODE-4 / CODE-5
def test_CODE4_unticked_box_adds_5_cover(content):
    s = to_build(content)
    base = s["meters"]["cover"]
    s2, _ = ship(s, content, "c1", dod=False)
    assert s2["meters"]["cover"] == base + 5 and "dod_skipped" in s2["process_log"]
    s3, _ = ship(s, content, "c1", dod=True)
    assert s3["meters"]["cover"] == base and "dod_honest" in s3["process_log"]


CASES = [  # ticket, effect, result, points, rating recorded for review
    ("final_price", "correct", "clean", 100, 0.02),
    ("final_price", "correct_small_flaw", "acceptable", 50, -0.05),
    ("final_price", "wrong_hidden", "buggy", 20, 0),
    ("find_user", "security_hole", "security_hole", 20, 0),
]


@pytest.mark.parametrize("ticket,effect,result,points,rating", CASES)
def test_CODE5_push_result_table(content, ticket, effect, result, points, rating):
    s = to_build(content)
    cid = add_card(s, ticket, content)
    diff = content.tickets[ticket]["difficulty"]
    s2, ev = ship(s, content, cid, effect)
    assert next(e for e in ev if e["type"] == "pushed")["result"] == result
    assert s2["meters"]["points"] == points * (diff if result in ("clean", "acceptable") else 1)
    assert s2["shipped"][-1]["rating"] == rating


def test_CODE5_runtime_error_blocks_push(content):
    s = to_build(content)
    s2, ev = ship(s, content, "c1", "crashes")
    assert ev[-1]["type"] == "push_blocked" and s2["meters"]["points"] == -30
    assert s2["open_card"] == "c1" and not s2["shipped"]


def test_CODE5_run_shows_failure_still_pushable(content):
    s = to_build(content)
    assert content.tickets["final_price"]["run_shows_failure"]
    s2, ev = ship(s, content, "c1", "wrong_hidden")
    assert [e for e in ev if e["type"] == "pushed"][0]["result"] == "buggy"
    assert s2["process_log"][-1] == "dod_dishonest"  # ticked "tests" without a green run


def test_CODE5_rejects_unflagged_patch_and_push_without_patch(content):
    s = to_build(content)
    s, _ = run(s, content, "open_card", card_id="c1")
    with pytest.raises(GameError):
        run(s, content, "select_patch", option_id="a")
    with pytest.raises(GameError):
        run(s, content, "push")


def test_CODE5_review_order_and_penalties(content):
    s = to_build(content)
    s, _ = ship(s, content, "c1", "wrong_hidden")
    s["day"] = 2
    s2, ev = run(s, content, "advance_stage", to="REVIEW")
    order = [e["type"] for e in ev]
    assert order.index("review_resolved") < order.index("posts_resolved") < order.index("rating_resolved")
    assert s2["meters"]["rating"] < content.balance["start"]["rating"] - 0.1


# ---------------------------------------------------------------- METER
def test_METER1_repeat_reward(content):
    s = to_build(content)
    pts = []
    for _ in range(3):
        cid = add_card(s, "final_price", content)
        before = s["meters"]["points"]
        s, _ = ship(s, content, cid)
        pts.append(s["meters"]["points"] - before)
    assert pts == [100, 70, 49]


def _review_state(content, rating=3.5, warnings=0, cover=0):
    s = to_build(content)
    s["day"], s["meters"]["rating"], s["warnings"], s["meters"]["cover"] = 2, rating, warnings, cover
    return s


def test_METER2_lose_rating(content):
    s = _review_state(content, rating=2.5)
    s, _ = ship(s, content, "c1", "wrong_hidden")
    s["shipped"].append({"ticket": "find_user", "result": "security_hole", "effect": "security_hole", "sprint": 1, "rating": 0})
    s, _ = run(s, content, "advance_stage", to="REVIEW")
    assert s["ending"] == "lose_rating" and s["status"] == "ended"


def test_METER2_lose_cover(content):
    s = to_build(content)
    s["meters"]["cover"] = 99
    s, _ = ship(s, content, "c1", dod=False)
    assert s["ending"] == "lose_cover"
    with pytest.raises(GameError):
        run(s, content, "tick", real_ms=1)


def test_METER2_lose_two_warnings(content):
    s = _review_state(content, rating=2.9, warnings=1)
    s, _ = run(s, content, "advance_stage", to="REVIEW")
    assert s["warnings"] == 2 and s["ending"] == "lose_warnings"


def test_METER2_one_warning_then_win(content):
    s = _review_state(content, rating=2.9, warnings=0)
    s, _ = run(s, content, "advance_stage", to="REVIEW")
    assert s["warnings"] == 1 and s["ending"] == "win"


def test_MVP_attack_check_minus_0_8_minus_150(content):
    s = to_build(content)
    cid = add_card(s, "find_user", content)
    s, _ = ship(s, content, cid, "security_hole")
    r0, p0 = s["meters"]["rating"], s["meters"]["points"]
    s["day"] = 2
    s, ev = run(s, content, "advance_stage", to="REVIEW")
    assert abs(s["meters"]["rating"] - (r0 - 0.8)) < 1e-6 and s["meters"]["points"] == p0 - 150
    assert any(e["type"] == "attack_check_resolved" for e in ev)


# ---------------------------------------------------------------- TIME-1
def test_TIME1_day_cap_8h(content):
    s = to_build(content)
    s["clock_s"] = s["day_start_s"] + 475 * 60
    with pytest.raises(GameError) as e:
        run(s, content, "open_card", card_id="c1")
    assert e.value.code == "DAY_FULL"


def test_TIME1_low_focus_cost_plus_50pct(content):
    s = to_build(content)
    c0 = s["clock_s"]
    a, _ = run(s, content, "open_card", card_id="c1")
    s["meters"]["focus"] = 29
    b, _ = run(s, content, "open_card", card_id="c1")
    assert a["clock_s"] - c0 == 600 and b["clock_s"] - c0 == 900


def test_TIME1_tick_clamped_and_scaled(content):
    s = to_build(content)
    a, _ = run(s, content, "tick", real_ms=1000)
    assert a["clock_s"] - s["clock_s"] == 160
    b, _ = run(s, content, "tick", real_ms=10 ** 9)
    assert b["clock_s"] - s["clock_s"] == 5 * 160


# ---------------------------------------------------------------- SPRINT-1
def test_SPRINT1_illegal_transition(content):
    s, _ = reducer.start_run(1, content)
    for dst in ("PLANNING", "BUILD", "REVIEW", "NOPE"):
        with pytest.raises(GameError) as e:
            run(s, content, "advance_stage", to=dst)
        assert e.value.code == "ILLEGAL_TRANSITION"
    for src in e1.STAGES:
        for dst in e1.STAGES:
            assert e1.can_transition(src, dst) == (dst in e1.ALLOWED[src])
    # the arcade game ends a sprint at REVIEW; RETRO is reachable only in learning mode (see test_calm.py)
    assert e1.ALLOWED["REVIEW"] == {"RETRO"} and e1.ALLOWED["RETRO"] == {"PLANNING"}
    s_review = dict(s, stage="REVIEW")
    with pytest.raises(GameError):
        run(s_review, content, "advance_stage", to="RETRO")


def test_SPRINT1_full_stage_sequence(content):
    b = bot.play(1, content)
    stages = [e["stage"] for e in b.events if e["type"] == "stage_advanced"]
    assert stages == ["STANDUP", "BUILD", "STANDUP", "BUILD", "REVIEW"]


# ---------------------------------------------------------------- PILE
def test_PILE1_card_density_by_sprint(content):
    s, _ = reducer.start_run(1, content)
    assert len([c for c in s["pile"] if c["state"] == "pile"]) == content.balance["density"]["1"] == 2


def test_PILE1_cards_have_sender_deadline_payoff_penalty(content):
    s, _ = reducer.start_run(1, content)
    for c in reducer.public_state(s, content)["pile"]:
        assert c["sender"] and c["deadline_min"] is not None and "payoff" in c and "penalty" in c


def test_PILE2_illegal_second_card(content):
    s = to_build(content)
    s, _ = run(s, content, "open_card", card_id="c1")
    with pytest.raises(GameError) as e:
        run(s, content, "open_card", card_id="c2")
    assert e.value.code == "ILLEGAL_COMMAND"
    s, _ = run(s, content, "hold")
    s, _ = run(s, content, "open_card", card_id="c2")
    s0, _ = reducer.start_run(1, content)
    with pytest.raises(GameError) as e:
        run(s0, content, "push")
    assert e.value.code == "ILLEGAL_COMMAND"


def test_PILE3_ignored_card_escalates_never_disappears(content):
    s = to_build(content)
    for _ in range(80):
        s, _ = run(s, content, "tick", real_ms=5000)
    c1 = next(c for c in s["pile"] if c["id"] == "c1")
    assert c1["escalation"] >= 1 and c1["state"] == "pile" and s["meters"]["cover"] > 0


def test_PILE3_escalation_levels_cap(content):
    s = to_build(content)
    s["pile"][0]["deadline_s"] = s["clock_s"] + 1.0
    seen = []
    for _ in range(200):
        s, ev = run(s, content, "tick", real_ms=1000)
        seen += [e["level"] for e in ev if e["type"] == "card_escalated" and e["card_id"] == "c1"]
        if len(seen) >= 2:
            break
    assert seen[:2] == [1, 2]


def test_PILE4_hidden_bug_rate_45_55(content):
    hits = 0
    for seed in range(1000):
        s, _ = reducer.start_run(seed, content)
        hits += reducer.draw(s, "delegation_bug") < content.balance["delegation"]["hidden_bug_chance"]
    assert 450 <= hits <= 550


def test_PILE4_delegate_returns_and_needs_review(content):
    s = to_build(content)
    s, _ = run(s, content, "delegate", card_id="c1")
    assert s["pile"][0]["state"] == "delegated"
    for _ in range(60):
        s, _ = run(s, content, "tick", real_ms=5000)
        if s["pile"][0]["state"] == "returned":
            break
    assert s["pile"][0]["state"] == "returned"
    s, _ = run(s, content, "open_card", card_id="c1")
    assert s["pile"][0]["work"]["selected"]


def test_PILE4_coach_help_call(content):
    s = to_build(content)
    for _ in range(10):
        s, _ = run(s, content, "tick", real_ms=5000)
    hc = next(c for c in s["pile"] if c["type"] == "help_call")
    s, _ = run(s, content, "coach", card_id=hc["id"])
    assert "coach" in s["process_log"] and s["coach_credit"] == 1
    with pytest.raises(GameError):
        run(s, content, "coach", card_id="c1")


# ---------------------------------------------------------------- calls, defer, triage
def test_calls_ring_answer_and_third_miss_cover(content):
    s = to_build(content)
    while s["call"] is None:
        s, _ = run(s, content, "tick", real_ms=5000)
    s, ev = run(s, content, "answer_call")
    assert ev[-1]["type"] == "call_answered" and s["call"] is None
    s["call_misses"] = 2
    s["call"] = {"sender": "po", "expires_s": s["clock_s"] + 1}
    c0 = s["meters"]["cover"]
    s, _ = run(s, content, "tick", real_ms=1000)
    assert s["call_misses"] == 3 and s["meters"]["cover"] >= c0 + 3


def test_defer_escalates(content):
    s = to_build(content)
    s, _ = run(s, content, "defer", card_id="c1")
    assert next(c for c in s["pile"] if c["id"] == "c1")["escalation"] == 1


def test_triage_reorder(content):
    s = to_build(content)
    s, _ = run(s, content, "triage_reorder", order=["c2", "c1"])
    assert [c["id"] for c in s["pile"][:2]] == ["c2", "c1"]
    with pytest.raises(GameError):
        run(s, content, "triage_reorder", order=["c1"])


# ---------------------------------------------------------------- STAND-1 / MEM-1
def test_STAND1_accurate_only_if_unlocked(content):
    s, _ = reducer.start_run(1, content)
    s, _ = run(s, content, "advance_stage", to="STANDUP")
    assert "accurate" not in reducer.public_state(s, content)["standup"]["choices"]
    with pytest.raises(GameError):
        run(s, content, "reply_standup", answer="accurate")
    s, _ = run(s, content, "watch_tutorial", tutorial_id="conditions")
    assert "accurate" in reducer.public_state(s, content)["standup"]["choices"]
    run(s, content, "reply_standup", answer="accurate")


@pytest.mark.parametrize("ans,delta", [("accurate", -10), ("vague", 5), ("wrong", 15)])
def test_STAND1_cover_deltas(content, ans, delta):
    s, _ = reducer.start_run(1, content)
    s["meters"]["cover"] = 20
    s["unlocked"] = ["conditions"]
    s, _ = run(s, content, "advance_stage", to="STANDUP")
    s, _ = run(s, content, "reply_standup", answer=ans)
    assert s["meters"]["cover"] == 20 + delta


def test_STAND1_cannot_leave_standup_unanswered(content):
    s, _ = reducer.start_run(1, content)
    s, _ = run(s, content, "advance_stage", to="STANDUP")
    with pytest.raises(GameError):
        run(s, content, "advance_stage", to="BUILD")


def test_MEM1_contradiction_adds_10_once(content):
    s, _ = reducer.start_run(1, content)
    s["unlocked"] = ["conditions"]
    s, _ = run(s, content, "advance_stage", to="STANDUP")
    s, _ = run(s, content, "reply_standup", answer="accurate")  # claims final_price is fine
    s, _ = run(s, content, "advance_stage", to="BUILD")
    s, _ = ship(s, content, "c1", "wrong_hidden")
    c0 = s["meters"]["cover"]
    s, ev = run(s, content, "advance_stage", to="STANDUP")
    assert [e["type"] for e in ev].count("contradiction_detected") == 1
    assert s["meters"]["cover"] >= c0 + 10
    c1 = s["meters"]["cover"]
    reducer._check_contradictions(s, [], content)  # replay the same bluff: no second charge
    assert s["meters"]["cover"] == c1


# ---------------------------------------------------------------- perks, tutorials
def test_PERK1_ai_assistant_wrong_1_in_5_seeded(content):
    wrong = 0
    t = content.tickets["final_price"]
    for seed in range(1000):
        s = to_build(content, seed=seed)
        s["perks"] = ["ai_assistant"]
        s, _ = run(s, content, "open_card", card_id="c1")
        s, ev = run(s, content, "use_assistant")
        wrong += next(o for o in t["options"] if o["id"] == ev[0]["suggested"])["effect"] != "correct"
    assert 150 <= wrong <= 250


def test_PERK1_flag_off_always_right(content):
    c2 = replace(content, balance={**content.balance, "assistant_flaky": False})
    for seed in range(100):
        s = to_build(c2, seed=seed)
        s["perks"] = ["ai_assistant"]
        s, _ = run(s, c2, "open_card", card_id="c1")
        s, ev = run(s, c2, "use_assistant")
        assert ev[0]["suggested"] == "a"


def test_PERK1_buy_requires_points_and_not_in_score(content):
    s = to_build(content)
    with pytest.raises(GameError):
        run(s, content, "buy_perk", perk_id="ai_assistant")
    s["meters"]["points"] = 500
    before = reducer.process_score(s, content)
    s, _ = run(s, content, "buy_perk", perk_id="ai_assistant")
    assert s["meters"]["points"] == 350 and reducer.process_score(s, content) == before
    s["meters"]["points"] = 10 ** 6
    assert reducer.process_score(s, content) == before
    with pytest.raises(GameError):
        run(s, content, "use_assistant")  # no card open


def test_TUT1_costs_30min_unlocks_concept(content):
    s, _ = reducer.start_run(1, content)
    s, _ = run(s, content, "watch_tutorial", tutorial_id="conditions")
    assert s["clock_s"] == 1800 and "conditions" in s["unlocked"]
    with pytest.raises(GameError):
        run(s, content, "watch_tutorial", tutorial_id="conditions")


def test_TUT1_unknown_concept_shows_question_marks(content):
    t = to_build(content)
    t, _ = run(t, content, "open_card", card_id="c1")
    assert set(reducer.public_state(t, content)["work"]["glossary"].values()) == {"???"}
    t["unlocked"] = ["conditions"]
    assert "???" not in reducer.public_state(t, content)["work"]["glossary"].values()


# ---------------------------------------------------------------- PROC-1, END-1, ASSESS-1
def test_PROC1_solo_scores_lower_than_coach_delegate(content):
    a, b = bot.play(1, content, "solo"), bot.play(1, content, "coach_delegate")
    assert a.s["meters"]["points"] == b.s["meters"]["points"]
    assert reducer.process_score(a.s, content) < reducer.process_score(b.s, content)


def test_END1_four_endings_have_debrief_data(content):
    ends = {}
    for pol in ("solo", "reckless"):
        s = bot.play(1, content, pol).s
        ends[s["ending"]] = s
    s = to_build(content)
    s["meters"]["cover"] = 99
    s, _ = ship(s, content, "c1", dod=False)
    ends[s["ending"]] = s
    s, _ = run(_review_state(content, rating=2.9, warnings=1), content, "advance_stage", to="REVIEW")
    ends[s["ending"]] = s
    assert set(ends) == set(reducer.ENDINGS)
    for st_ in ends.values():
        assert {"rating", "cover", "points", "process_score", "gap", "ending"} <= set(reducer.debrief(st_, content))


def test_ASSESS1_gain_deterministic_with_interval():
    pre, post = [0.3, 0.4, 0.5, 0.2, 0.6], [0.6, 0.7, 0.8, 0.4, 0.7]
    a, b = e2.learning_gain(pre, post, seed=7), e2.learning_gain(pre, post, seed=7)
    assert a == b and a["low"] <= a["mean"] <= a["high"] and a["mean"] > 0


# ---------------------------------------------------------------- determinism / engines
def test_bot_replay_hash(content):
    for pol in bot.POLICIES:
        assert len({bot.play(42, content, pol).digest() for _ in range(5)}) == 1


def test_bot_same_final_state_20_runs(content):
    finals = {json.dumps([bot.play(7, content).s[k] for k in ("meters", "warnings")]) for _ in range(20)}
    assert len(finals) == 1


def test_bot_can_win_and_lose(content):
    assert bot.play(1, content, "solo").s["ending"] == "win"
    assert bot.play(1, content, "reckless").s["ending"].startswith("lose")


def test_rng_streams_independent(content):
    a, _ = reducer.start_run(5, content)
    b, _ = reducer.start_run(5, content)
    for _ in range(3):
        reducer.draw(b, "viral")
    assert [reducer.draw(a, "delegation_bug") for _ in range(5)] == [reducer.draw(b, "delegation_bug") for _ in range(5)]


def test_reducer_does_not_mutate_input_on_error(content):
    s = to_build(content)
    snap = copy.deepcopy(s)
    with pytest.raises(GameError):
        run(s, content, "push")
    assert s == snap


def test_public_state_hides_answer_keys(content):
    s = to_build(content)
    s, _ = run(s, content, "open_card", card_id="c1")
    blob = json.dumps(reducer.public_state(s, content))
    for secret in ("correct_small_flaw", "wrong_hidden", "security_hole", "hidden_bug", "effect", "bug_type"):
        assert secret not in blob


def test_E1_segments_budget_and_pinned():
    segs = [{"id": "p", "text": "persona " * 50, "seq": 0, "pinned": True}] + \
           [{"id": f"s{i}", "text": "x" * 400, "seq": i + 1} for i in range(100)]
    out = e1.select_segments(segs, "STANDUP", budget=10_000)  # cap applies
    assert sum(e1.tokens(x["text"]) for x in out) <= e1.BUDGET_CAP and out[0]["id"] == "p"


def test_E1_context_build_under_130ms():
    segs = [{"id": f"s{i}", "text": "word " * 60, "seq": i} for i in range(2000)]
    t0 = time.perf_counter()
    e1.select_segments(segs, "BUILD")
    assert time.perf_counter() - t0 < 0.13
