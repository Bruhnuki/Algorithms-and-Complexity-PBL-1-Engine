"""Tester round 4: team-wide penalties, put-down, giving work, interactive Help requests, pacing, final Grade and summary."""
import pytest

from fixit.rules import content as content_mod, reducer
from fixit.rules.reducer import GameError
from conftest import run, ship
from test_calm import clear_scenes, settle, start_sprint


@pytest.fixture(scope="module")
def calm():
    c = content_mod.get()
    assert reducer._calm(c)
    return c


def P(calm):
    return calm.balance["calm"]["penalties"]


def fix_card(s, calm):
    return next(c for c in s["pile"] if c["ticket"] and calm.tickets[c["ticket"]]["kind"] == "fix" and c["state"] == "pile")


def open_fix(s, calm):
    c = fix_card(s, calm)
    s, _ = run(s, calm, "open_card", card_id=c["id"])
    return s, c, calm.tickets[c["ticket"]]


def wrong_line(t):
    return next(n for n in range(1, len(t["source"]) + 1) if n != t["buggy_line"])


def option(t, effect):
    return next(o["id"] for o in t["options"] if o["effect"] == effect)


# ---------------------------------------------------------------- mistakes cost the whole team
def test_PEN1_every_wrong_line_costs_grade_and_trust_for_the_team(calm):
    s = start_sprint(reducer.start_run(1, calm)[0], calm)
    base = dict(s["x"]["team_trust"])
    s, c, t = open_fix(s, calm)
    s, ev = run(s, calm, "flag_line", line_no=wrong_line(t))
    pen = P(calm)["wrong_line"]
    assert s["x"]["grade_penalty"] == pen["grade"] == 1 and all(s["x"]["team_trust"][d] == base[d] - pen["trust"] for d in base)
    assert next(e for e in ev if e["type"] == "penalty")["why"] == "wrong_line"
    s, _ = run(s, calm, "flag_line", line_no=wrong_line(t))                       # the same wrong line again counts again
    assert s["x"]["grade_penalty"] == 2 and all(s["x"]["team_trust"][d] == base[d] - 2 for d in base)
    s, ev = run(s, calm, "flag_line", line_no=t["buggy_line"])
    assert s["x"]["grade_penalty"] == 2 and not any(e["type"] == "penalty" for e in ev)    # the right line is free
    assert s["guide"]["stats"]["wrong_line"] == 2


def test_PEN2_test_needs_a_line_and_a_fix_and_a_failed_test_costs_the_team(calm):
    s = start_sprint(reducer.start_run(1, calm)[0], calm)
    s, c, t = open_fix(s, calm)
    with pytest.raises(GameError) as e:
        run(s, calm, "run_script")
    assert "faulty line" in e.value.detail
    s, _ = run(s, calm, "flag_line", line_no=t["buggy_line"])
    with pytest.raises(GameError) as e:
        run(s, calm, "run_script")
    assert "replacement" in e.value.detail
    base = dict(s["x"]["team_trust"])
    s, _ = run(s, calm, "select_patch", option_id=option(t, "wrong_hidden"))
    s, ev = run(s, calm, "run_script")
    assert not next(e for e in ev if e["type"] == "script_run")["all_pass"]
    assert s["x"]["grade_penalty"] == P(calm)["failed_test"]["grade"] and all(s["x"]["team_trust"][d] == base[d] - 1 for d in base)
    s, _ = run(s, calm, "select_patch", option_id=option(t, "correct"))
    s, ev = run(s, calm, "run_script")
    assert next(e for e in ev if e["type"] == "script_run")["all_pass"] and not any(e["type"] == "penalty" for e in ev)
    with pytest.raises(GameError) as e:
        run(s, calm, "run_script")                                                  # it passed: no more testing
    assert "already passed" in e.value.detail
    pub = reducer.public_state(s, calm)["work"]
    assert pub["flag_ok"] is True and pub["last_run"]["all_pass"]


def test_PEN3_every_wrong_scene_answer_counts_separately(calm):
    s, _ = reducer.start_run(1, calm)
    base = dict(s["x"]["team_trust"])
    b = next(x for x in calm.guide["beats"] if x["id"] == "s1_backlog_owner")
    for wrong in [c for c in b["choices"] if not c.get("correct")]:
        s, _ = run(s, calm, "guide_answer", choice_id=wrong["id"])
    n = sum(1 for c in b["choices"] if not c.get("correct"))
    pen = P(calm)["wrong_answer"]
    assert n == 2 and s["x"]["grade_penalty"] == n * pen["grade"] == 4
    assert all(s["x"]["team_trust"][d] == base[d] - n * pen["trust"] for d in base) and s["guide"]["stats"]["wrong_scene"] == 2


def test_PEN4_put_it_down_removes_the_item_and_costs_the_team_but_never_ends_the_run(calm):
    s = start_sprint(reducer.start_run(1, calm)[0], calm)
    s["sprint"] = 2                                                                   # the sprints where a low rating normally ends the run
    pen = P(calm)["put_down"]
    base, rating = dict(s["x"]["team_trust"]), s["meters"]["rating"]
    left = reducer._g_unresolved(s)
    s, c, t = open_fix(s, calm)
    s, ev = run(s, calm, "hold")
    assert next(x for x in s["pile"] if x["id"] == c["id"])["state"] == "dropped" and s["open_card"] is None
    assert reducer._g_unresolved(s) == left - 1                                       # resolved
    assert s["x"]["grade_penalty"] == pen["grade"] == 30
    assert all(s["x"]["team_trust"][d] == max(10, base[d] - pen["trust"]) for d in base)
    assert s["meters"]["rating"] == pen["rating_floor"] == 2.0 < rating                # -2 stars, but never below the floor
    assert s["status"] == "active"
    done = next(e for e in ev if e["type"] == "item_put_down")
    assert done["grade"] == 30 and done["trust"] == 20 and done["rating"] == round(rating - 2.0, 2)
    s, c2, t2 = open_fix(s, calm)                                                     # a second one: the rating stays put
    s, _ = run(s, calm, "hold")
    assert s["meters"]["rating"] == 2.0 and s["status"] == "active" and s["guide"]["stats"]["put_down"] == 2
    assert reducer.public_state(s, calm)["x"]["grade"] == 0                           # Grade bottoms out at 0
    assert reducer.public_state(s, calm)["x"]["penalties"]["put_down"]["grade"] == 30  # the UI warns with the real numbers


def test_PEN5_a_help_request_cannot_be_put_down(calm):
    s = start_sprint(reducer.start_run(1, calm)[0], calm)
    help_card = next(c for c in s["pile"] if c["type"] == "help_call")
    s, _ = run(s, calm, "open_card", card_id=help_card["id"])
    with pytest.raises(GameError):
        run(s, calm, "hold")


# ---------------------------------------------------------------- who may take an item
def test_GIVE1_the_author_cannot_take_their_own_item(calm):
    s = start_sprint(reducer.start_run(1, calm)[0], calm)
    c = next(c for c in s["pile"] if c["ticket"] and c["sender"] == "dev1")
    with pytest.raises(GameError) as e:
        run(s, calm, "delegate", card_id=c["id"], to="dev1")
    assert "wrote this one" in e.value.detail
    s2, _ = run(s, calm, "delegate", card_id=c["id"], to="dev2")                       # the other teammate can


# ---------------------------------------------------------------- Help requests
def help_card_for(s, hid, sender):
    c = next(c for c in s["pile"] if c["type"] == "help_call")
    c["help_id"], c["help_type"], c["sender"] = hid, ("challenge" if "challenge" in hid else "scenario"), sender
    return c


def test_HELP1_a_scenario_answer_moves_the_askers_trust(calm):
    for sender in ("dev1", "dev2"):
        for hid, h in [(k, v) for k, v in calm.help.items() if v["type"] == "scenario"]:
            for a in h["answers"]:
                s = start_sprint(reducer.start_run(2, calm)[0], calm)
                c = help_card_for(s, hid, sender)
                before = dict(s["x"]["team_trust"])
                s, _ = run(s, calm, "open_card", card_id=c["id"])
                pub = reducer.public_state(s, calm)["help"]
                assert pub["dev"] == sender and pub["prompt"] and [x["id"] for x in pub["answers"]] == [x["id"] for x in h["answers"]]
                assert "trust" not in str(pub["answers"])                              # the effects are not sent to the browser
                s, ev = run(s, calm, "help_answer", answer_id=a["id"])
                assert next(x for x in s["pile"] if x["id"] == c["id"])["state"] == "done" and s["open_card"] is None
                assert s["x"]["team_trust"][sender] == min(100, max(10, before[sender] + a["trust"]))
                other = "dev2" if sender == "dev1" else "dev1"
                assert s["x"]["team_trust"][other] == before[other]
                got = next(e for e in ev if e["type"] == "help_answered")
                assert got["delta"] == a["trust"] and got["feedback"] == a["feedback"] and got["best"] is bool(a.get("best"))


def test_HELP2_a_coding_challenge_costs_the_asker_3_per_mistake_and_pays_3_when_solved(calm):
    C = calm.balance["calm"]["help"]
    s = start_sprint(reducer.start_run(2, calm)[0], calm)
    c = help_card_for(s, "hr_challenge_vip", "dev2")
    base = dict(s["x"]["team_trust"])
    s, _ = run(s, calm, "open_card", card_id=c["id"])
    work = reducer.public_state(s, calm)["work"]
    assert work["challenge"] is True and work["intro"] and work["ticket"] == "help_vip"
    t = calm.tickets["help_vip"]
    s, _ = run(s, calm, "flag_line", line_no=wrong_line(t))                             # a wrong line: -3 for the asker only
    assert s["x"]["team_trust"]["dev2"] == base["dev2"] - C["challenge_fail"] and s["x"]["team_trust"]["dev1"] == base["dev1"]
    assert s["x"]["grade_penalty"] == 0                                                 # no team-wide penalty in a challenge
    s, _ = run(s, calm, "flag_line", line_no=t["buggy_line"])
    s, _ = run(s, calm, "select_patch", option_id=option(t, "wrong_hidden"))
    s, _ = run(s, calm, "run_script")                                                   # a failed test: -3 again
    assert s["x"]["team_trust"]["dev2"] == base["dev2"] - 2 * C["challenge_fail"] and s["x"]["grade_penalty"] == 0
    with pytest.raises(GameError):
        run(s, calm, "push")                                                            # it is solved by a passing test, not pushed
    s, _ = run(s, calm, "select_patch", option_id=option(t, "correct"))
    s, ev = run(s, calm, "run_script")
    assert any(e["type"] == "help_solved" for e in ev)
    assert next(x for x in s["pile"] if x["id"] == c["id"])["state"] == "done" and s["open_card"] is None
    assert s["x"]["team_trust"]["dev2"] == base["dev2"] - 2 * C["challenge_fail"] + C["challenge_solved"]


def test_HELP3_never_the_same_kind_twice_in_a_row(calm):
    s, _ = reducer.start_run(5, calm)
    kinds = []
    for _ in range(40):
        hid = reducer._g_pick_help(s, calm)
        kinds.append(calm.help[hid]["type"])
    assert all(a != b for a, b in zip(kinds, kinds[1:])) and {"scenario", "challenge"} == set(kinds)


def test_HELP4_there_is_enough_authored_content(calm):
    sc = [h for h in calm.help.values() if h["type"] == "scenario"]
    ch = [h for h in calm.help.values() if h["type"] == "challenge"]
    assert len(sc) >= 3 and len(ch) >= 3
    for h in sc:
        deltas = sorted(a["trust"] for a in h["answers"])
        assert deltas[0] == -5 and deltas[-1] == 3 and sum(1 for a in h["answers"] if a.get("best")) == 1 and set(h["prompts"]) == {"dev1", "dev2"}
    for h in ch:
        assert h["ticket"] in calm.tickets and set(h["intros"]) == {"dev1", "dev2"}
    assert not {t for t in calm.tickets if t.startswith(("help_", "story_"))} & set(calm.pool)


def test_HELP5_every_sprint_has_five_items_and_one_help_request(calm):
    for k, sp in calm.guide["sprints"].items():
        assert len(sp["tickets"]) == 5 and all(t in calm.tickets for t in sp["tickets"]), k
    s, _ = reducer.start_run(3, calm)
    assert sum(1 for c in s["pile"] if c["ticket"]) == 5 and sum(1 for c in s["pile"] if c["type"] == "help_call") == 1
    assert [c["batch"] for c in s["pile"] if c["ticket"]] == [1, 1, 1, 2, 2]


# ---------------------------------------------------------------- the end of the run
def test_FINAL1_final_grade_is_70_percent_grade_plus_30_percent_rating_score(calm, monkeypatch):
    s = start_sprint(reducer.start_run(1, calm)[0], calm)
    F = calm.balance["calm"]["final_grade"]
    for rating in (1.0, 3.5, 5.0):
        for g in range(0, 101, 5):
            s["meters"]["rating"] = rating
            monkeypatch.setattr(reducer, "_g_grade", lambda *_a, g=g: g)
            f = reducer._g_final(s, calm)
            rs = round((rating - 1) / 4 * 100)
            assert f["final"] == round(0.7 * g + 0.3 * rs) and f["rating_score"] == rs
            assert f["tier"] == ("low" if f["final"] < F["low_below"] else "high" if f["final"] > F["high_above"] else "mid")
    assert F["low_below"] == 50 and F["high_above"] == 85


def test_FINAL2_the_summary_cites_the_runs_own_numbers_and_always_recaps_what_was_learned(calm, monkeypatch):
    s = start_sprint(reducer.start_run(1, calm)[0], calm)
    st = s["guide"]["stats"]
    st.update(wrong_line=3, failed_test=2, put_down=1, vague=1, lie=2, wrong_scene=4, hidden_surfaced=2, accurate=0)
    s = clear_scenes(s, calm)
    s["meters"]["rating"] = 1.0
    monkeypatch.setattr(reducer, "_g_grade", lambda *_a: 10)
    low = reducer.debrief(s, calm)["x"]["summary"]
    assert low["tier"] == "low" and low["wrong"] and low["improve"] and not low["well"]
    text = " ".join(low["wrong"])
    assert "3 wrong lines" in text and "2 of your tests failed" in text and "put down 1 item," in text and "2 untrue" in text and "4 wrong answers" in text
    assert low["learned"] and {"concept", "teach"} <= set(low["learned"][0])
    monkeypatch.setattr(reducer, "_g_grade", lambda *_a: 95)
    s["meters"]["rating"] = 5.0
    st.update(wrong_line=0, failed_test=0, put_down=0, vague=0, lie=0, wrong_scene=0, hidden_surfaced=0, accurate=6, help_good=2)
    high = reducer.debrief(s, calm)["x"]["summary"]
    assert high["tier"] == "high" and high["well"] and not high["wrong"] and not high["improve"] and high["learned"]
    assert any("6 honest" in w for w in high["well"]) and any("2 time" in w for w in high["well"])
    monkeypatch.setattr(reducer, "_g_grade", lambda *_a: 70)
    s["meters"]["rating"] = 3.5
    st.update(wrong_line=2)
    mid = reducer.debrief(s, calm)["x"]["summary"]
    assert mid["tier"] == "mid" and mid["well"] and mid["wrong"] and mid["improve"] and mid["learned"]
    assert reducer.debrief(s, calm)["x"]["final"]["final"] == mid["numbers"]["final"]
