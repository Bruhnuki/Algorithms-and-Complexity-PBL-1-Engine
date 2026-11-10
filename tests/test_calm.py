"""Calm learning mode: no timers, guided Scrum scenes, a Retrospective stage, coaching and Definition-of-Done consequences."""
import json

import pytest

from fixit.rules import content as content_mod, reducer
from fixit.rules.reducer import GameError
from conftest import run, ship


@pytest.fixture(scope="module")
def calm():
    c = content_mod.get()
    assert reducer._calm(c), "the shipped balance.yaml must be the calm learning mode"
    return c


def correct_choice(content, beat_id):
    b = next(x for x in content.guide["beats"] if x["id"] == beat_id)
    if b["kind"] == "pick":
        return None
    return next(c["id"] for c in b["choices"] if c.get("correct"))


def clear_scenes(s, content, mistakes=False):
    """Answer every open scene correctly (optionally after one wrong try) and continue."""
    while s["guide"]["pending"]:
        bid = s["guide"]["pending"]
        b = next(x for x in content.guide["beats"] if x["id"] == bid)
        if b["kind"] == "pick":
            pub = reducer.public_state(s, content)["guide"]["pending"]
            s, _ = run(s, content, "guide_answer", choice_id=pub["choices"][0]["id"])
        else:
            if mistakes:
                wrong = next(c["id"] for c in b["choices"] if not c.get("correct"))
                s, _ = run(s, content, "guide_answer", choice_id=wrong)
            s, _ = run(s, content, "guide_answer", choice_id=correct_choice(content, bid))
        s, _ = run(s, content, "guide_next")
    return s


def start_sprint(s, content):
    s = clear_scenes(s, content)
    s, _ = run(s, content, "advance_stage", to="STANDUP")
    s = clear_scenes(s, content)
    s, _ = run(s, content, "reply_standup", answer="accurate")
    s, _ = run(s, content, "advance_stage", to="BUILD")
    return s


def touch(s, content):
    """Open an item and put it down again: enough to count as having started work today."""
    cid = next(c["id"] for c in s["pile"] if c["ticket"] and c["state"] == "pile")
    s, _ = run(s, content, "open_card", card_id=cid)
    return run(s, content, "hold")[0]


def finish_sprint(s, content):
    if not s["guide"]["worked"]:
        s = touch(s, content)
    s, _ = run(s, content, "advance_stage", to="STANDUP")
    s = clear_scenes(s, content)
    s, _ = run(s, content, "reply_standup", answer="accurate")
    s, _ = run(s, content, "advance_stage", to="BUILD")
    s, _ = run(s, content, "advance_stage", to="REVIEW")
    s = clear_scenes(s, content)
    s, _ = run(s, content, "advance_stage", to="RETRO")
    s = clear_scenes(s, content)
    return run(s, content, "advance_stage", to="PLANNING")[0]


# ---------------------------------------------------------------- no pressure
def test_CALM1_no_real_time_clock(calm):
    s = start_sprint(reducer.start_run(1, calm)[0], calm)
    s2, ev = run(s, calm, "tick", real_ms=10 ** 9)
    assert s2["clock_s"] == s["clock_s"] and ev == []


def test_CALM2_nothing_is_due_and_nothing_gets_louder(calm):
    s = start_sprint(reducer.start_run(1, calm)[0], calm)
    assert all(c["deadline_s"] is None for c in s["pile"])
    cid = next(c["id"] for c in s["pile"] if c["ticket"])
    s, _ = run(s, calm, "open_card", card_id=cid)
    s, _ = run(s, calm, "hold")
    # burn most of the day: a card that used to escalate in an hour stays quiet
    for _ in range(6):
        s, _ = run(s, calm, "open_card", card_id=cid)
        s, _ = run(s, calm, "hold")
    assert all(c["escalation"] == 0 for c in s["pile"])
    pub = reducer.public_state(s, calm)
    assert all(c["deadline_min"] is None for c in pub["pile"])


def test_CALM3_arcade_mechanics_are_off(calm):
    o = calm.balance["originals"]
    for k in ("speed_fix", "combo", "events", "action_hand", "release_train", "score_multiplier"):
        assert not o[k]["enabled"], k
    s = start_sprint(reducer.start_run(1, calm)[0], calm)
    pub = reducer.public_state(s, calm)
    assert pub["x"]["calm"] and not pub["x"]["boss_live"] and pub["x"]["standup_timer_s"] is None
    assert "hand" not in pub["x"] and "release" not in pub["x"] and pub["x"].get("wave") is None
    assert [p["id"] for p in pub["x"]["perk_shop"]] == ["ai_assistant"]
    with pytest.raises(GameError):
        run(s, calm, "buy_perk", perk_id="keyboard_warrior")


def test_CALM4_calls_never_expire(calm):
    s, _ = reducer.start_run(1, calm)
    reducer._ring(s, [], calm, "dev1")
    assert s["call"]["expires_s"] >= 1e12
    reducer._ring(s, [], calm, "dev2")          # a second call replaces the first without a penalty
    assert s["call_misses"] == 0 and s["call"]["sender"] == "dev2"


def test_CALM5_stable_sprint_backlog_all_items_at_planning(calm):
    s, _ = reducer.start_run(1, calm)
    assert [c["ticket"] for c in s["pile"]] == ["final_price", "total_with_tax", "shipping_fee"]
    pub = reducer.public_state(s, calm)["guide"]
    assert [b["in_sprint"] for b in pub["backlog"]] == [True, True, True, False, False]
    assert not pub["committed"]                                    # the forecast scene is still open


# ---------------------------------------------------------------- guided scenes
def test_GUIDE1_scene_blocks_the_sprint_until_answered(calm):
    s, _ = reducer.start_run(1, calm)
    with pytest.raises(GameError) as e:
        run(s, calm, "advance_stage", to="STANDUP")
    assert "scene" in e.value.detail
    pub = reducer.public_state(s, calm)["guide"]["pending"]
    assert pub["id"] == "s1_backlog_owner" and pub["step"] == 1 and pub["of"] == 3
    assert '"correct"' not in json.dumps(reducer.public_state(s, calm)["guide"])   # the answer key never leaves the server


def test_GUIDE2_wrong_answer_teaches_then_retry(calm):
    s, _ = reducer.start_run(1, calm)
    b = next(x for x in calm.guide["beats"] if x["id"] == "s1_backlog_owner")
    wrong = next(c for c in b["choices"] if not c.get("correct"))
    s, ev = run(s, calm, "guide_answer", choice_id=wrong["id"])
    assert ev[0]["ok"] is False
    pub = reducer.public_state(s, calm)["guide"]["pending"]
    assert not pub["resolved"] and pub["tried"][0]["feedback"] == wrong["feedback"] and "teach" not in pub
    with pytest.raises(GameError):
        run(s, calm, "guide_answer", choice_id=wrong["id"])        # same wrong choice again
    with pytest.raises(GameError):
        run(s, calm, "guide_next")                                  # cannot skip an unanswered question
    s, ev = run(s, calm, "guide_answer", choice_id=correct_choice(calm, "s1_backlog_owner"))
    assert ev[0]["ok"] is True and ev[0]["first_try"] is False
    assert reducer.public_state(s, calm)["guide"]["pending"]["teach"]
    s, _ = run(s, calm, "guide_next")
    assert s["guide"]["pending"] == "s1_sprint_goal"


def test_GUIDE3_standup_waits_for_the_daily_scrum_scene(calm):
    s, _ = reducer.start_run(1, calm)
    s = clear_scenes(s, calm)
    s, _ = run(s, calm, "advance_stage", to="STANDUP")
    assert s["guide"]["pending"] == "s1_daily_purpose" and s["pending_standup"]
    with pytest.raises(GameError):
        run(s, calm, "reply_standup", answer="accurate")
    s = clear_scenes(s, calm)
    s, _ = run(s, calm, "reply_standup", answer="accurate")        # honest answer needs no tutorial in learning mode


def test_GUIDE4_full_run_follows_the_five_scrum_events(calm):
    s, _ = reducer.start_run(7, calm)
    goals_met = []
    for sprint in (1, 2, 3):
        assert s["sprint"] == sprint and s["stage"] == "PLANNING"
        s = start_sprint(s, calm)
        tickets = [c for c in s["pile"] if c["ticket"] and c["state"] == "pile"]
        for c in tickets[:2]:
            s, _ = ship(s, calm, c["id"])
        goals_met.append(reducer.public_state(s, calm)["x"]["goal"]["met"])
        s = finish_sprint(s, calm) if sprint < 3 else _finish_last(s, calm)
    assert s["status"] == "ended" and s["ending"] == "win"
    assert all(goals_met)
    sc = reducer.debrief(s, calm)["x"]["scrum"]
    assert sc["asked"] == sc["of"] and sc["first_try"] == sc["of"]
    assert len(s["guide"]["picks"]) == 3                            # one Retrospective improvement per sprint


def _finish_last(s, calm):
    s, _ = run(s, calm, "advance_stage", to="STANDUP")
    s = clear_scenes(s, calm)
    s, _ = run(s, calm, "reply_standup", answer="accurate")
    s, _ = run(s, calm, "advance_stage", to="BUILD")
    s, _ = run(s, calm, "advance_stage", to="REVIEW")
    s = clear_scenes(s, calm)
    s, _ = run(s, calm, "advance_stage", to="RETRO")
    s = clear_scenes(s, calm)
    return run(s, calm, "advance_stage", to="PLANNING")[0]


def test_GUIDE5_review_scene_reports_what_is_really_done(calm):
    s = start_sprint(reducer.start_run(3, calm)[0], calm)
    first, second = [c["id"] for c in s["pile"] if c["ticket"]][:2]
    s, _ = ship(s, calm, first)                                     # honest, fully ticked: Done
    s, _ = ship(s, calm, second, dod=False)                         # sent with the checklist skipped: not Done
    s, _ = run(s, calm, "advance_stage", to="STANDUP")
    s = clear_scenes(s, calm)
    s, _ = run(s, calm, "reply_standup", answer="accurate")
    s, _ = run(s, calm, "advance_stage", to="BUILD")
    s, _ = run(s, calm, "advance_stage", to="REVIEW")
    scene = reducer.public_state(s, calm)["guide"]["pending"]["scene"]
    assert "1 met the Definition of Done" in scene and "1 more went to users but are not truly Done" in scene
    assert "1 not finished, so they go back to the Product Backlog" in scene


def test_GUIDE6_retro_stage_gates_the_next_sprint_and_grants_the_pick(calm):
    s = touch(start_sprint(reducer.start_run(5, calm)[0], calm), calm)
    s, _ = run(s, calm, "advance_stage", to="STANDUP")
    s = clear_scenes(s, calm)
    s, _ = run(s, calm, "reply_standup", answer="accurate")
    s, _ = run(s, calm, "advance_stage", to="BUILD")
    s, _ = run(s, calm, "advance_stage", to="REVIEW")
    assert s["stage"] == "REVIEW" and s["sprint"] == 1              # the sprint does not roll over at the review
    with pytest.raises(GameError):
        run(s, calm, "advance_stage", to="PLANNING")
    s = clear_scenes(s, calm)
    s, _ = run(s, calm, "advance_stage", to="RETRO")
    pend = reducer.public_state(s, calm)["guide"]["pending"]
    assert pend["id"] == "s1_retro_purpose"
    s, _ = run(s, calm, "guide_answer", choice_id=correct_choice(calm, "s1_retro_purpose"))
    s, _ = run(s, calm, "guide_next")
    pend = reducer.public_state(s, calm)["guide"]["pending"]
    assert pend["kind"] == "pick" and "You did not coach anyone" in pend["scene"]
    assert "swarming" in [c["id"] for c in pend["choices"] if c["suggested"]]   # evidence points at coaching
    s, ev = run(s, calm, "guide_answer", choice_id="swarming")
    assert "swarming" in s["x"]["practices"]
    s, _ = run(s, calm, "guide_next")
    s, _ = run(s, calm, "advance_stage", to="PLANNING")
    assert s["sprint"] == 2 and s["stage"] == "PLANNING" and s["guide"]["pending"] == "s2_refine"
    assert [c["ticket"] for c in s["pile"] if c["state"] == "pile"] == ["loyalty_discount", "points_balance", "average_rating"]


def test_GUIDE7_unfinished_items_return_to_the_product_backlog(calm):
    s = start_sprint(reducer.start_run(2, calm)[0], calm)
    s = finish_sprint(s, calm)
    assert s["sprint"] == 2
    live = [c["ticket"] for c in reducer.public_state(s, calm)["pile"] if c["state"] != "backlog"]
    assert "final_price" not in live and "loyalty_discount" in live


def test_GUIDE8_first_sprint_is_safe(calm):
    s = start_sprint(reducer.start_run(4, calm)[0], calm)
    s["meters"]["rating"] = 1.0
    s["meters"]["cover"] = 150
    s["warnings"] = 5
    reducer._check_end(s, [], calm)
    assert s["status"] == "active"
    s["sprint"] = 2
    reducer._check_end(s, [], calm)
    assert s["status"] == "ended"


# ---------------------------------------------------------------- coaching and Definition of Done pay off
def test_PAYOFF1_coaching_lowers_a_developers_mistake_chance(calm):
    s = start_sprint(reducer.start_run(1, calm)[0], calm)
    s["clock_s"] += 130 * 60
    reducer._fire_schedule(s, [], calm)
    help_card = next(c for c in s["pile"] if c["type"] == "help_call")
    before = reducer.public_state(s, calm)["x"]["team"][help_card["sender"]]["bug_chance"]
    s, ev = run(s, calm, "coach", card_id=help_card["id"])
    after = reducer.public_state(s, calm)["x"]["team"][help_card["sender"]]["bug_chance"]
    assert any(e["type"] == "skill_grew" for e in ev)
    assert round(before - after, 3) == calm.balance["calm"]["coach_skill_gain"]


def test_PAYOFF2_skipping_the_checklist_adds_debt_and_honest_work_pays_it_back(calm):
    s = start_sprint(reducer.start_run(1, calm)[0], calm)
    a, b, _c = [c["id"] for c in s["pile"] if c["ticket"]]
    s, _ = ship(s, calm, a, dod=False)
    debt = s["x"]["debt"]
    assert debt == calm.balance["calm"]["debt_per_skipped_dod"]
    base = calm.balance["originals"]["team_board"]["bug_chance"]["dev2"]
    assert reducer.public_state(s, calm)["x"]["team"]["dev2"]["bug_chance"] == round(base + debt, 3)
    s, _ = ship(s, calm, b)
    assert s["x"]["debt"] == 0.0


def test_DEBRIEF1_story_names_what_the_player_did(calm):
    s = start_sprint(reducer.start_run(1, calm)[0], calm)
    s, _ = ship(s, calm, next(c["id"] for c in s["pile"] if c["ticket"]), dod=False)
    s["status"], s["ending"] = "ended", "lose_rating"
    d = reducer.debrief(s, calm)
    joined = " ".join(d["x"]["story"])
    assert "never coached" in joined and "skipped 1 time" in joined


def test_CONTENT1_every_beat_has_exactly_one_correct_choice_and_known_tickets(calm):
    g = calm.guide
    for b in g["beats"]:
        if b["kind"] == "quiz":
            assert sum(1 for c in b["choices"] if c.get("correct")) == 1, b["id"]
        else:
            assert all(p in g["retro_options"] and p in calm.balance["experimental"]["practices"]["effects"] for p in b["pool"]), b["id"]
        assert b["sprint"] in (1, 2, 3)
    for sp in g["sprints"].values():
        assert all(t in calm.tickets for t in sp["tickets"] + sp["backlog_more"])
    ids = [b["id"] for b in g["beats"]]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------- tester feedback
def test_FEEDBACK1_cannot_end_day_one_before_touching_the_work(calm):
    s = start_sprint(reducer.start_run(1, calm)[0], calm)
    with pytest.raises(GameError) as e:
        run(s, calm, "advance_stage", to="STANDUP")
    assert "at least one item" in e.value.detail
    assert reducer.public_state(s, calm)["guide"]["worked"] is False
    s = touch(s, calm)
    assert reducer.public_state(s, calm)["guide"]["worked"] is True
    run(s, calm, "advance_stage", to="STANDUP")


def test_FEEDBACK2_suspicion_and_strikes_cannot_end_a_learning_run(calm):
    s = start_sprint(reducer.start_run(1, calm)[0], calm)
    s["sprint"] = 2
    s["meters"]["cover"], s["warnings"] = 500, 9
    reducer._check_end(s, [], calm)
    assert s["status"] == "active"
    s["meters"]["rating"] = 1.5
    reducer._check_end(s, [], calm)
    assert s["status"] == "ended" and s["ending"] == "lose_rating"


def test_FEEDBACK3_missing_the_goal_is_not_a_strike(calm):
    s = start_sprint(reducer.start_run(1, calm)[0], calm)
    s = touch(s, calm)
    s, _ = run(s, calm, "advance_stage", to="STANDUP")
    s = clear_scenes(s, calm)
    s, _ = run(s, calm, "reply_standup", answer="accurate")
    s, _ = run(s, calm, "advance_stage", to="BUILD")
    s, ev = run(s, calm, "advance_stage", to="REVIEW")
    assert s["warnings"] == 0 and not any(e["type"] == "warning_issued" for e in ev)
    assert any(e["type"] == "sprint_goal" and e["met"] is False for e in ev)


def test_FEEDBACK4_no_completion_codes_in_self_study(calm):
    s = start_sprint(reducer.start_run(5, calm)[0], calm)
    s = touch(s, calm)
    s, _ = run(s, calm, "advance_stage", to="STANDUP")
    s = clear_scenes(s, calm)
    s, _ = run(s, calm, "reply_standup", answer="accurate")
    s, _ = run(s, calm, "advance_stage", to="BUILD")
    s, _ = run(s, calm, "advance_stage", to="REVIEW")
    s = clear_scenes(s, calm)
    s, ev = run(s, calm, "advance_stage", to="RETRO")
    assert not any("code" in e["type"] for e in ev)
    blob = json.dumps(reducer.public_state(s, calm)["guide"]) + json.dumps(reducer.debrief(s, calm))
    assert "codes" not in blob and "final_code" not in blob


def test_FEEDBACK5_a_vague_daily_scrum_answer_hides_a_problem(calm):
    s = start_sprint(reducer.start_run(1, calm)[0], calm)
    base = s["x"]["debt"]
    s2, _ = run(touch(s, calm), calm, "advance_stage", to="STANDUP")
    s2 = clear_scenes(s2, calm)
    s2, _ = run(s2, calm, "reply_standup", answer="vague")
    assert s2["x"]["debt"] == base + calm.balance["calm"]["debt_per_skipped_dod"]
