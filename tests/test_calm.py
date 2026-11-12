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


def correct_choice(content, beat_id, s=None):
    b = reducer._g_beat(s, content, beat_id) if s is not None else next(x for x in content.guide["beats"] if x["id"] == beat_id)
    if b["kind"] == "pick":
        return None
    return next(c["id"] for c in b["choices"] if c.get("correct"))


def clear_scenes(s, content, mistakes=False):
    """Answer every open scene correctly (optionally after one wrong try) and continue."""
    while s["guide"]["pending"]:
        bid = s["guide"]["pending"]
        b = reducer._g_beat(s, content, bid)
        if b["kind"] == "pick":
            pub = reducer.public_state(s, content)["guide"]["pending"]
            s, _ = run(s, content, "guide_answer", choice_id=pub["choices"][0]["id"])
        else:
            if mistakes:
                wrong = next(c["id"] for c in b["choices"] if not c.get("correct"))
                s, _ = run(s, content, "guide_answer", choice_id=wrong)
            s, _ = run(s, content, "guide_answer", choice_id=correct_choice(content, bid, s))
        s, _ = run(s, content, "guide_next")
    return s


def start_sprint(s, content):
    s = clear_scenes(s, content)
    s, _ = run(settle(s), content, "advance_stage", to="STANDUP")
    s = clear_scenes(s, content)
    s, _ = run(s, content, "reply_standup", answer="accurate")
    s, _ = run(s, content, "advance_stage", to="BUILD")
    reducer._g_reveal(s, [], 99, 2)       # most tests want every item on the list (the live feed has its own tests)
    return s


def settle(s):
    """Test shortcut: resolve whatever is blocking End the day / Finish the Sprint right now (the real rules have their own tests)."""
    if s["stage"] != "BUILD":
        return s
    upto = 1 if s["day"] < 2 else 99
    for c in s["pile"]:
        if c["state"] in ("pile", "open", "returned") and c.get("batch", 1) <= upto:
            c["state"], c["hidden"] = "done", False
    s["open_card"] = None
    return s


def touch(s, content):
    """Finish the day's work (see settle) and note that work started."""
    s["guide"]["worked"] = True
    return settle(s)


def finish_sprint(s, content):
    s = settle(s)
    s, _ = run(settle(s), content, "advance_stage", to="STANDUP")
    s = clear_scenes(s, content)
    s, _ = run(s, content, "reply_standup", answer="accurate")
    s, _ = run(s, content, "advance_stage", to="BUILD")
    s, _ = run(settle(s), content, "advance_stage", to="REVIEW")
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
    reducer._advance(s, [], calm, 6 * 3600)          # burn most of the day: a card that used to escalate in an hour stays quiet
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
    assert pub["x"]["perk_shop"] == []                       # Points became the Grade: nothing is for sale
    with pytest.raises(GameError):
        run(s, calm, "buy_perk", perk_id="ai_assistant")
    assert "focus" not in pub["meters"]                      # no Energy


def test_CALM4_calls_never_expire(calm):
    s, _ = reducer.start_run(1, calm)
    reducer._ring(s, [], calm, "dev1")
    assert s["call"]["expires_s"] >= 1e12
    reducer._ring(s, [], calm, "dev2")          # a second call replaces the first without a penalty
    assert s["call_misses"] == 0 and s["call"]["sender"] == "dev2"


def test_CALM5_stable_sprint_backlog_all_items_at_planning(calm):
    s, _ = reducer.start_run(1, calm)
    assert [c["ticket"] for c in s["pile"] if c["ticket"]] == ["final_price", "total_with_tax", "shipping_fee", "story_service_fee", "split_bill"]
    pub = reducer.public_state(s, calm)["guide"]
    assert [b["in_sprint"] for b in pub["backlog"]] == [True] * 5
    assert not pub["committed"]                                    # the forecast scene is still open


# ---------------------------------------------------------------- guided scenes
def test_GUIDE1_scene_blocks_the_sprint_until_answered(calm):
    s, _ = reducer.start_run(1, calm)
    with pytest.raises(GameError) as e:
        run(settle(s), calm, "advance_stage", to="STANDUP")
    assert "scene" in e.value.detail
    pub = reducer.public_state(s, calm)["guide"]["pending"]
    assert pub["id"] == "s1_backlog_owner" and pub["step"] == 1 and pub["of"] == 3
    assert '"correct"' not in json.dumps(reducer.public_state(s, calm)["guide"])   # the answer key never leaves the server


def test_GUIDE2_wrong_answer_teaches_then_retry(calm):
    s, _ = reducer.start_run(1, calm)
    b = next(x for x in calm.guide["beats"] if x["id"] == "s1_backlog_owner")
    wrong = next(c for c in b["choices"] if not c.get("correct"))
    s, ev = run(s, calm, "guide_answer", choice_id=wrong["id"])
    assert next(e for e in ev if e["type"] == "guide_answered")["ok"] is False
    pub = reducer.public_state(s, calm)["guide"]["pending"]
    assert not pub["resolved"] and pub["tried"][0]["feedback"] == wrong["feedback"] and "teach" not in pub
    with pytest.raises(GameError):
        run(s, calm, "guide_answer", choice_id=wrong["id"])        # same wrong choice again
    with pytest.raises(GameError):
        run(s, calm, "guide_next")                                  # cannot skip an unanswered question
    s, ev = run(s, calm, "guide_answer", choice_id=correct_choice(calm, "s1_backlog_owner"))
    answered = next(e for e in ev if e["type"] == "guide_answered")
    assert answered["ok"] is True and answered["first_try"] is False
    assert reducer.public_state(s, calm)["guide"]["pending"]["teach"]
    s, _ = run(s, calm, "guide_next")
    assert s["guide"]["pending"] == "s1_sprint_goal"


def test_GUIDE3_standup_waits_for_the_daily_scrum_scene(calm):
    s, _ = reducer.start_run(1, calm)
    s = clear_scenes(s, calm)
    s, _ = run(settle(s), calm, "advance_stage", to="STANDUP")
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
    s, _ = run(settle(s), calm, "advance_stage", to="STANDUP")
    s = clear_scenes(s, calm)
    s, _ = run(s, calm, "reply_standup", answer="accurate")
    s, _ = run(s, calm, "advance_stage", to="BUILD")
    s, _ = run(settle(s), calm, "advance_stage", to="REVIEW")
    s = clear_scenes(s, calm)
    s, _ = run(s, calm, "advance_stage", to="RETRO")
    s = clear_scenes(s, calm)
    return run(s, calm, "advance_stage", to="PLANNING")[0]


def test_GUIDE5_review_scene_reports_what_is_really_done(calm):
    s = start_sprint(reducer.start_run(3, calm)[0], calm)
    first, second = [c["id"] for c in s["pile"] if c["ticket"]][:2]
    s, _ = ship(s, calm, first)                                     # honest, fully ticked: Done
    s, _ = ship(s, calm, second, dod=False)                         # sent with the checklist skipped: not Done
    s, _ = run(settle(s), calm, "advance_stage", to="STANDUP")
    s = clear_scenes(s, calm)
    s, _ = run(s, calm, "reply_standup", answer="accurate")
    s, _ = run(s, calm, "advance_stage", to="BUILD")
    s, _ = run(settle(s), calm, "advance_stage", to="REVIEW")
    scene = reducer.public_state(s, calm)["guide"]["pending"]["scene"]
    assert "1 met the Definition of Done" in scene and "1 more went to users but are not truly Done" in scene
    assert "3 not finished, so they go back to the Product Backlog" in scene


def test_GUIDE6_retro_stage_gates_the_next_sprint_and_grants_the_pick(calm):
    s = touch(start_sprint(reducer.start_run(5, calm)[0], calm), calm)
    s, _ = run(settle(s), calm, "advance_stage", to="STANDUP")
    s = clear_scenes(s, calm)
    s, _ = run(s, calm, "reply_standup", answer="accurate")
    s, _ = run(s, calm, "advance_stage", to="BUILD")
    s, _ = run(settle(s), calm, "advance_stage", to="REVIEW")
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
    assert [c["ticket"] for c in s["pile"] if c["state"] == "pile" and c["ticket"]] == ["loyalty_discount", "points_balance", "average_rating", "story_birthday", "story_streak"]


def test_GUIDE7_the_next_sprints_items_arrive_with_its_work(calm):
    s = start_sprint(reducer.start_run(2, calm)[0], calm)
    s = finish_sprint(s, calm)
    assert s["sprint"] == 2
    by_ticket = {c["ticket"]: c for c in s["pile"] if c["ticket"]}
    assert by_ticket["final_price"]["state"] == "done"                          # last Sprint's work stays done
    assert by_ticket["loyalty_discount"]["hidden"] and by_ticket["loyalty_discount"]["state"] == "pile"   # Sprint 2's items arrive with its Work


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
def test_PAYOFF2_skipping_the_checklist_costs_trust_and_honest_work_rebuilds_it(calm):
    s = start_sprint(reducer.start_run(1, calm)[0], calm)
    a, b = [c["id"] for c in s["pile"] if c["ticket"]][:2]
    C = calm.balance["calm"]
    base = dict(s["x"]["team_trust"])
    s, _ = ship(s, calm, a, dod=False)
    assert all(s["x"]["team_trust"][d] == base[d] - C["dod_skip_trust"] for d in base)
    s, _ = ship(s, calm, b)
    assert all(s["x"]["team_trust"][d] == base[d] - C["dod_skip_trust"] + C["honest_push_trust"] for d in base)


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
def test_FEEDBACK1_cannot_end_day_one_with_work_left(calm):
    s = start_sprint(reducer.start_run(1, calm)[0], calm)
    with pytest.raises(GameError) as e:
        run(s, calm, "advance_stage", to="STANDUP")                              # not settled: the real rule applies
    assert "3 items still to do" in e.value.detail and reducer.public_state(s, calm)["x"]["todo"]["blocking"] == 3
    run(settle(s), calm, "advance_stage", to="STANDUP")


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
    s, _ = run(settle(s), calm, "advance_stage", to="STANDUP")
    s = clear_scenes(s, calm)
    s, _ = run(s, calm, "reply_standup", answer="accurate")
    s, _ = run(s, calm, "advance_stage", to="BUILD")
    s, ev = run(settle(s), calm, "advance_stage", to="REVIEW")
    assert s["warnings"] == 0 and not any(e["type"] == "warning_issued" for e in ev)
    assert any(e["type"] == "sprint_goal" and e["met"] is False for e in ev)


def test_FEEDBACK4_no_completion_codes_in_self_study(calm):
    s = start_sprint(reducer.start_run(5, calm)[0], calm)
    s = touch(s, calm)
    s, _ = run(settle(s), calm, "advance_stage", to="STANDUP")
    s = clear_scenes(s, calm)
    s, _ = run(s, calm, "reply_standup", answer="accurate")
    s, _ = run(s, calm, "advance_stage", to="BUILD")
    s, _ = run(settle(s), calm, "advance_stage", to="REVIEW")
    s = clear_scenes(s, calm)
    s, ev = run(s, calm, "advance_stage", to="RETRO")
    assert not any("code" in e["type"] for e in ev)
    blob = json.dumps(reducer.public_state(s, calm)["guide"]) + json.dumps(reducer.debrief(s, calm))
    assert "codes" not in blob and "final_code" not in blob


def _standup_with(calm, answer, seed=1):
    s = start_sprint(reducer.start_run(seed, calm)[0], calm)
    s = touch(s, calm)
    s, _ = run(settle(s), calm, "advance_stage", to="STANDUP")
    s = clear_scenes(s, calm)
    who = s["pending_standup"]["teammate"]
    before = (s["meters"]["rating"], s["x"]["team_trust"][who])
    s, ev = run(s, calm, "reply_standup", answer=answer)
    return s, ev, who, before


def test_FEEDBACK5_daily_scrum_answers_trade_rating_trust_and_a_hidden_problem(calm):
    C = calm.balance["calm"]
    out = {}
    for ans in ("accurate", "vague", "wrong"):
        s, ev, who, (r0, t0) = _standup_with(calm, ans)
        eff = C["standup"][ans]
        assert round(s["meters"]["rating"] - r0, 4) == round(eff["rating"] * C["rating_per_point"], 4)
        assert s["x"]["team_trust"][who] == t0 + eff["trust"] and s["guide"]["hidden"] == eff["hidden"]
        out[ans] = (eff["rating"], eff["trust"], eff["hidden"])
    # the lie wins today (+10 rating) but loses over the Sprint: the hidden problem and the lost trust
    assert out["wrong"][0] > out["accurate"][0] > 0 > out["vague"][0]                # vague LOWERS the rating, the lie RAISES it
    assert out["vague"][1] > out["accurate"][1] > 0 > out["wrong"][1]                # vague RAISES trust, the lie LOWERS it
    assert (out["vague"][0], out["vague"][1], out["wrong"][0], out["wrong"][1]) == (-10, 15, 10, -15)
    assert out["wrong"][0] - out["wrong"][2] < out["accurate"][0] - out["accurate"][2]
    pub = reducer.public_state(s, calm)["x"]["standup_outcomes"]
    assert pub["wrong"]["rating"] == 10 and pub["accurate"]["trust"] > 0


def test_FEEDBACK6_a_hidden_problem_comes_back_as_harder_items_in_the_next_sprint(calm):
    s, _, _, _ = _standup_with(calm, "wrong")
    s, _ = run(s, calm, "advance_stage", to="BUILD")
    r0 = s["meters"]["rating"]
    s, ev = run(settle(s), calm, "advance_stage", to="REVIEW")
    found = next(e for e in ev if e["type"] == "hidden_problem")
    assert found["harder"] is True and found["items"] == calm.balance["calm"]["standup"]["wrong"]["items"] == 2 and found["delta"] == 0
    assert s["meters"]["rating"] == r0 and s["guide"]["owed"] == 2 and s["guide"]["hidden"] == 0       # no rating penalty now: it is homework for Sprint 2
    s = clear_scenes(s, calm)
    s, _ = run(s, calm, "advance_stage", to="RETRO")
    s = clear_scenes(s, calm)
    s, _ = run(s, calm, "advance_stage", to="PLANNING")
    harder = [c for c in s["pile"] if c.get("harder")]
    assert s["sprint"] == 2 and len(harder) == 2 and s["guide"]["owed"] == 0
    assert all(calm.tickets[c["ticket"]]["difficulty"] == 2 and c["ticket"].startswith("hidden_") for c in harder)
    assert [b["ticket"] for b in reducer.public_state(s, calm)["guide"]["backlog"] if b.get("harder")] == [c["ticket"] for c in harder]
    assert not any(t.startswith("hidden_") for t in calm.pool)


def test_FEEDBACK6b_in_the_last_sprint_a_hidden_problem_still_costs_rating(calm):
    s = start_sprint(reducer.start_run(1, calm)[0], calm)
    s["sprint"], s["day"] = 3, 2
    s["guide"]["hidden"], s["guide"]["hidden_items"] = 12, 2
    r0 = s["meters"]["rating"]
    s, ev = run(settle(s), calm, "advance_stage", to="REVIEW")
    found = next(e for e in ev if e["type"] == "hidden_problem")
    assert found["harder"] is False and found["items"] == 0 and round(r0 - s["meters"]["rating"], 4) == round(12 * calm.balance["calm"]["rating_per_point"], 4)


def test_SPRINT_last_sprint_results_do_not_linger(calm):
    s = start_sprint(reducer.start_run(4, calm)[0], calm)
    s, _ = run(s, calm, "delegate", card_id=next(c["id"] for c in s["pile"] if c["ticket"] and c["sender"] != "dev2"), to="dev2")
    assert s["x"]["last_offload"]
    s = finish_sprint(s, calm)
    assert s["sprint"] == 2 and s["x"]["last_offload"] == {}
    assert reducer.public_state(s, calm)["x"]["team"]["dev2"]["last"] is None


# ---------------------------------------------------------------- the team chat reacts to what you do
def _chat_requests(calm, events, state):
    from fixit.gateway import context as gctx
    return gctx.requests_for(events, state, calm, "u1", 0)


def test_CHAT1_teammates_react_to_the_daily_scrum_answer_with_the_current_facts(calm):
    for ans, et in (("accurate", "react_standup_honest"), ("vague", "react_standup_vague"), ("wrong", "react_standup_lie")):
        s, ev, who, _ = _standup_with(calm, ans)
        reqs = [r for r in _chat_requests(calm, ev, s) if r.event_type.startswith("react_")]
        assert [(r.teammate_id, r.event_type) for r in reqs] == [(who, et)]
        f = reqs[0].facts
        assert f["trust"] == s["x"]["team_trust"][who] and f["rating"] == round(s["meters"]["rating"], 1) and f["item"]


def test_CHAT2_low_trust_changes_the_prompt_and_the_fallback_line(calm):
    from fixit.gateway.gateway import Gateway
    s, ev, who, _ = _standup_with(calm, "wrong")
    s["x"]["team_trust"][who] = 30
    r = next(r for r in _chat_requests(calm, ev, s) if r.event_type == "react_standup_lie")
    r.facts["trust"], r.facts["mood"] = 30, "cold"
    gw = Gateway(calm, None)
    prompt = gw.build_messages(r)[1]["content"]
    assert "UNTRUE" in prompt and '"trust": 30' in prompt and "cold" in prompt
    low = gw.generate(r)
    r.facts["trust"] = 90
    high = gw.generate(r)
    lows = set(calm.teammates[who]["reactions_low"]["react_standup_lie"])
    assert low.source == "fallback" and any(low.text == ln.format_map({"item": r.facts["item"], "trust": 30}) for ln in lows)
    assert low.text != high.text and low.tone in ("pushy", "panicked")


def test_CHAT3_offloads_coaching_pushes_reviews_and_new_sprints_all_get_a_reaction(calm):
    s = start_sprint(reducer.start_run(4, calm)[0], calm)
    cid = next(c["id"] for c in s["pile"] if c["ticket"])
    s2, ev = run(s, calm, "delegate", card_id=cid, to="dev2")
    r = [r for r in _chat_requests(calm, ev, s2) if r.event_type.startswith("react_offload")]
    assert len(r) == 1 and r[0].teammate_id == "dev2" and r[0].facts["item"] == calm.tickets[next(c["ticket"] for c in s["pile"] if c["id"] == cid)]["title"]
    s3, ev = ship(s, calm, cid)
    assert [r.teammate_id for r in _chat_requests(calm, ev, s3) if r.event_type == "react_push"] == ["po"]
    reqs = _chat_requests(calm, reducer.start_run(1, calm)[1], reducer.start_run(1, calm)[0])
    assert any(r.event_type == "sprint_open" and r.teammate_id == "po" and r.facts["goal"] for r in reqs)


def test_CHAT4_the_practice_sprint_has_no_reactions(calm):
    s = tutorial_run(calm)
    s, _ = run(settle(s), calm, "advance_stage", to="STANDUP")
    s, ev = run(s, calm, "reply_standup", answer="accurate")
    assert not [r for r in _chat_requests(calm, ev, s) if r.event_type.startswith("react_")]


def test_CHAT5_every_reaction_has_authored_lines_for_the_teammates_who_use_them(calm):
    from fixit.gateway.gateway import REACTION_TYPES
    mine = {"dev1": REACTION_TYPES[:6], "dev2": REACTION_TYPES[:6], "po": ("react_push", "react_review", "react_review_hidden", "sprint_open")}
    for tid, types in mine.items():
        for et in types:
            assert len(set(calm.teammates[tid]["reactions"][et])) >= 3, (tid, et)
            if et != "sprint_open":
                assert len(set(calm.teammates[tid]["reactions_low"][et])) >= 3, (tid, et)


# ---------------------------------------------------------------- instant offloading, trust = success rate
def test_OFFLOAD1_giving_work_to_a_teammate_is_instant_and_lowers_their_trust(calm):
    s = start_sprint(reducer.start_run(4, calm)[0], calm)
    C = calm.balance["calm"]
    base = s["x"]["team_trust"]["dev2"]
    cid = next(c["id"] for c in s["pile"] if c["ticket"] and c["sender"] != "dev2")
    s, ev = run(s, calm, "delegate", card_id=cid, to="dev2")
    res = next(e for e in ev if e["type"] == "offload_result")
    card = next(c for c in s["pile"] if c["id"] == cid)
    assert card["state"] == ("done" if res["ok"] else "pile") and not any(c["state"] == "delegated" for c in s["pile"])
    assert s["x"]["team_trust"]["dev2"] == base - C["offload_cost"]
    assert reducer.public_state(s, calm)["x"]["team"]["dev2"]["trust"] == base - C["offload_cost"]
    assert reducer.public_state(s, calm)["x"]["team"]["dev2"]["last"]["ok"] is res["ok"]


def test_OFFLOAD2_each_offload_drops_the_success_rate_by_two_points(calm):
    s = start_sprint(reducer.start_run(4, calm)[0], calm)
    start, other = s["x"]["team_trust"]["dev2"], s["x"]["team_trust"]["dev1"]
    rates = []
    for cid in [c["id"] for c in s["pile"] if c["ticket"] and c["sender"] != "dev2"][:3]:
        s, _ = run(s, calm, "delegate", card_id=cid, to="dev2")
        rates.append(s["x"]["team_trust"]["dev2"])
    assert rates == [start - 2, start - 4, start - 6] and s["x"]["team_trust"]["dev1"] == other   # the other teammate is untouched


def test_OFFLOAD3_the_rate_is_80_percent_normally_and_100_in_the_tutorial(calm):
    wins, n = 0, 200
    for seed in range(n):
        s = start_sprint(reducer.start_run(seed, calm)[0], calm)
        cid = next(c["id"] for c in s["pile"] if c["ticket"] and c["sender"] != "dev2")
        s, ev = run(s, calm, "delegate", card_id=cid, to="dev2")
        wins += next(e for e in ev if e["type"] == "offload_result")["ok"]
    assert 0.7 < wins / n < 0.9                                              # about 80%
    for seed in range(40):
        s = tutorial_run(calm, seed)
        s, _ = run(settle(s), calm, "advance_stage", to="STANDUP")
        s, _ = run(s, calm, "reply_standup", answer="accurate")
        s, _ = run(s, calm, "advance_stage", to="BUILD")
        cid = next(c["id"] for c in s["pile"] if c["ticket"] and c["sender"] != "dev2")
        s, ev = run(s, calm, "delegate", card_id=cid, to="dev2")
        assert next(e for e in ev if e["type"] == "offload_result")["ok"] is True


def test_OFFLOAD4_a_failed_offload_comes_back_to_you_and_cannot_be_retried_by_the_same_teammate(calm):
    for seed in range(200):
        s = start_sprint(reducer.start_run(seed, calm)[0], calm)
        cid = next(c["id"] for c in s["pile"] if c["ticket"] and c["sender"] != "dev2")
        s2, ev = run(s, calm, "delegate", card_id=cid, to="dev2")
        if not next(e for e in ev if e["type"] == "offload_result")["ok"]:
            card = next(c for c in s2["pile"] if c["id"] == cid)
            assert card["state"] == "pile" and card["failed_by"] == "dev2" and card["failed_devs"] == ["dev2"]
            pub = next(c for c in reducer.public_state(s2, calm)["pile"] if c["id"] == cid)
            assert pub["failed_by"] == "dev2" and pub["failed_devs"] == ["dev2"]
            with pytest.raises(GameError) as e:
                run(s2, calm, "delegate", card_id=cid, to="dev2")           # the same teammate cannot take it again
            assert "already failed" in e.value.detail
            s3, _ = run(s2, calm, "open_card", card_id=cid)                   # you can still do it yourself
            return
    raise AssertionError("no failure in 200 seeds")


def test_TRUST1_no_trust_notices_when_a_run_starts(calm):
    s, ev = reducer.start_run(1, calm)
    assert not any(e["type"] == "trust_changed" for e in ev)
    s = clear_scenes(s, calm)
    s, ev = run(settle(s), calm, "advance_stage", to="STANDUP")
    assert not any(e["type"] == "trust_changed" for e in ev)


# ---------------------------------------------------------------- live feed, grade, no energy
def test_FEED1_items_arrive_one_at_a_time_every_10_to_20_seconds_in_two_batches(calm):
    C = calm.balance["calm"]
    s, _ = reducer.start_run(1, calm)
    assert reducer.public_state(s, calm)["pile"] == []                         # committed at Planning, not yet on the list
    s = clear_scenes(s, calm)
    s, _ = run(s, calm, "advance_stage", to="STANDUP")
    s = clear_scenes(s, calm)
    s, _ = run(s, calm, "reply_standup", answer="accurate")
    assert reducer.public_state(s, calm)["pile"] == []
    s, _ = run(s, calm, "advance_stage", to="BUILD")
    tickets = lambda: [c for c in reducer.public_state(s, calm)["pile"] if c["ticket"]]       # noqa: E731
    assert len(tickets()) == 1                                                  # the first item arrives with Work
    feed = reducer.public_state(s, calm)["x"]["feed"]
    assert feed["left_today"] == C["day1_items"] - 1 and feed["left"] == 5      # 5 items + the Help request, 1 shown
    assert C["feed_min_s"] * 1000 <= s["guide"]["feed_gap_ms"] <= C["feed_max_s"] * 1000
    gaps, seen = [], len(tickets())
    for _ in range(40):
        s, _ = run(s, calm, "tick", real_ms=1000)
        if len(tickets()) > seen:
            seen = len(tickets())
            gaps.append(s["guide"]["feed_gap_ms"])
    assert seen == C["day1_items"]                                              # day 1 stops at its batch
    assert reducer.public_state(s, calm)["x"]["feed"]["left_today"] == 0 and reducer.public_state(s, calm)["x"]["feed"]["left"] == 3
    hidden = next(c for c in s["pile"] if c.get("hidden"))
    with pytest.raises(GameError):
        run(s, calm, "open_card", card_id=hidden["id"])                          # cannot be opened before it arrives
    with pytest.raises(GameError) as e:
        run(s, calm, "advance_stage", to="STANDUP")                              # all of day 1's items first
    assert "3 items still to do" in e.value.detail
    s = settle(s)
    s, _ = run(s, calm, "advance_stage", to="STANDUP")
    s = clear_scenes(s, calm)
    s, _ = run(s, calm, "reply_standup", answer="accurate")
    s, _ = run(s, calm, "advance_stage", to="BUILD")
    shown = [c for c in reducer.public_state(s, calm)["pile"] if c["state"] == "pile"]
    assert len(shown) == 1 and reducer.public_state(s, calm)["x"]["feed"]["left_today"] == 2   # day 2's batch starts the same way
    for _ in range(60):
        s, _ = run(s, calm, "tick", real_ms=1000)
    assert reducer.public_state(s, calm)["x"]["feed"]["left"] == 0
    kinds = [c["type"] for c in reducer.public_state(s, calm)["pile"] if c["state"] == "pile"]
    assert kinds.count("help_call") == 1 and len(kinds) == 3                    # 2 more items and the Help request


def test_FEED3_the_sprint_cannot_finish_with_anything_left(calm):
    s = start_sprint(reducer.start_run(1, calm)[0], calm)
    s = settle(s)
    s, _ = run(s, calm, "advance_stage", to="STANDUP")
    s = clear_scenes(s, calm)
    s, _ = run(s, calm, "reply_standup", answer="accurate")
    s, _ = run(s, calm, "advance_stage", to="BUILD")
    reducer._g_reveal(s, [], 99, 2)
    n = sum(1 for c in s["pile"] if c["state"] == "pile")
    with pytest.raises(GameError) as e:
        run(s, calm, "advance_stage", to="REVIEW")
    assert f"{n} item" in e.value.detail and reducer.public_state(s, calm)["x"]["todo"]["blocking"] == n   # items, harder items and the Help request all count
    run(settle(s), calm, "advance_stage", to="REVIEW")


def test_FEED2_the_tutorial_has_every_item_at_once(calm):
    s = tutorial_run(calm)
    assert len(reducer.public_state(s, calm)["pile"]) == 3 and reducer.public_state(s, calm)["x"]["feed"]["left"] == 0


def test_GRADE1_grade_rises_with_done_work(calm):
    s = start_sprint(reducer.start_run(1, calm)[0], calm)
    assert reducer.public_state(s, calm)["x"]["grade"] == 0
    s, _ = ship(s, calm, next(c["id"] for c in s["pile"] if c["ticket"]))
    g1 = reducer.public_state(s, calm)["x"]["grade"]
    s, _ = ship(s, calm, next(c["id"] for c in s["pile"] if c["ticket"] and c["state"] == "pile"))
    assert 0 < g1 < reducer.public_state(s, calm)["x"]["grade"] <= 100


def test_TUTORIALTICKET1_practice_problems_stay_out_of_real_sprints(calm):
    practice = {t for t in calm.tickets if t.startswith("practice_")}
    assert practice == {"practice_bag", "practice_late", "practice_wrap"} and not practice & set(calm.pool)
    for sp in calm.guide["sprints"].values():
        assert not practice & set(sp["tickets"] + sp["backlog_more"])
    s = tutorial_run(calm)
    assert {c["ticket"] for c in s["pile"]} == practice


def test_TUTORIALTICKET2_the_line_and_fix_are_validated_by_the_item_not_by_position(calm):
    s = tutorial_run(calm)
    s, _ = run(settle(s), calm, "advance_stage", to="STANDUP")
    s, _ = run(s, calm, "reply_standup", answer="accurate")
    s, _ = run(s, calm, "advance_stage", to="BUILD")
    cid = next(c["id"] for c in s["pile"] if c["ticket"] == "practice_bag")
    s, _ = run(s, calm, "open_card", card_id=cid)
    for wrong in (1, 4, 7):
        s, _ = run(s, calm, "flag_line", line_no=wrong)
        w = reducer.public_state(s, calm)["work"]
        assert w["flag_ok"] is False and w["tutorial"]["buggy_line"] is None or wrong == 7
    w = reducer.public_state(s, calm)["work"]
    assert w["flag_misses"] == 3 and w["tutorial"]["buggy_line"] == 5               # narrowed down after repeated misses
    assert w["tutorial"]["line_notes"]["4"] and w["tutorial"]["hints"] and w["tutorial"]["answer_option"] == "a"
    s, _ = run(s, calm, "flag_line", line_no=5)
    assert reducer.public_state(s, calm)["work"]["flag_ok"] is True
    # a normal run never sends any of that
    n = start_sprint(reducer.start_run(1, calm)[0], calm)
    n, _ = run(n, calm, "open_card", card_id=next(c["id"] for c in n["pile"] if c["ticket"]))
    assert reducer.public_state(n, calm)["work"]["tutorial"] is None


# ---------------------------------------------------------------- tutorial practice sprint
def tutorial_run(calm, seed=3):
    s, _ = reducer.start_run(seed, calm)
    assert s["guide"]["pending"] == "s1_backlog_owner"      # a normal run starts with a scene...
    s, _ = run(s, calm, "configure", unlocks=[], heat=[], tutorial=True)
    return s


def test_TUTORIAL1_practice_sprint_has_no_scenes_and_plays_normally(calm):
    s = tutorial_run(calm)
    assert s["guide"]["pending"] is None and s["guide"]["queue"] == []
    assert reducer.public_state(s, calm)["x"]["tutorial"] is True
    s, _ = run(settle(s), calm, "advance_stage", to="STANDUP")      # ...a tutorial run does not: nothing blocks the stages
    assert s["guide"]["pending"] is None and s["pending_standup"]
    s, _ = run(s, calm, "reply_standup", answer="accurate")
    s, _ = run(s, calm, "advance_stage", to="BUILD")
    s, ev = ship(s, calm, next(c["id"] for c in s["pile"] if c["ticket"]))
    assert any(e["type"] == "pushed" for e in ev)
    cid = next(c["id"] for c in s["pile"] if c["state"] == "pile" and c["ticket"])
    s, _ = run(s, calm, "delegate", card_id=cid, to="dev1")
    s, _ = run(settle(s), calm, "advance_stage", to="STANDUP")      # day 1 can end once work has started
    assert s["guide"]["pending"] is None and s["day"] == 2


def test_TUTORIAL2_a_normal_run_is_not_a_tutorial(calm):
    s, _ = reducer.start_run(3, calm)
    s, _ = run(s, calm, "configure", unlocks=[], heat=[])
    assert reducer.public_state(s, calm)["x"]["tutorial"] is False and s["guide"]["pending"] == "s1_backlog_owner"


def test_TUTORIAL3_api_creates_a_practice_run_and_hides_it_from_the_instructor(tmp_path, calm):
    from api_helpers import Env
    e = Env(tmp_path, calm)
    i = e.signup("ti@x.io", role="instructor", name="ti")
    c = e.signup("ts@x.io", cohort_code=i.info["join_code"], name="ts")
    r = c.post("/api/v1/runs", json={"tutorial": True})
    assert r.status_code == 201 and r.json()["state"]["x"]["tutorial"] is True and r.json()["state"]["guide"]["pending"] is None
    r2 = c.post("/api/v1/runs", json={})
    assert r2.json()["state"]["x"]["tutorial"] is False and r2.json()["state"]["guide"]["pending"]["id"] == "s1_backlog_owner"
    rows = i.get(f"/api/v1/instructor/cohorts/{i.info['cohort_id']}/runs").json()["runs"]
    assert [row["run_id"] for row in rows] == [r2.json()["id"]]       # the practice sprint is not listed
