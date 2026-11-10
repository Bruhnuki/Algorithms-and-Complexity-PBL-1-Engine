"""Front-end safety checks that do not need a browser. Full-browser E2E (Playwright) is not set up yet."""
import re
from pathlib import Path

import yaml

from api_helpers import Driver, Env, new_run
from fixit import bot

WEB = Path(__file__).resolve().parents[1] / "src" / "fixit" / "web"


def test_UI_no_inline_script_or_style():
    for page in (WEB / "index.html", WEB / "play" / "index.html"):   # landing page and game page
        html = page.read_text(encoding="utf-8")
        assert not re.search(r"<script(?![^>]*\bsrc=)", html) and "style=" not in html and "onclick=" not in html, page


def test_e2e_dialogue_text_is_escaped_by_construction():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert banned not in js, banned
    assert "document.createTextNode" in js


def test_UI_no_rules_in_js(content):
    js = (WEB / "app.js").read_text(encoding="utf-8")
    b = content.balance
    # none of the scoring/cost numbers from balance.yaml are hardcoded as rules in the page
    for token in ("repeat_decay", "dod_unticked_cover", "standup_cover", "hidden_bug", "effect", "correct_small_flaw"):
        assert token not in js
    assert "0.7" not in js and str(b["attack_check"]["points"]) not in js


def test_e2e_csp_and_static_served(tmp_path, content):
    c = Env(tmp_path, content).client()
    r = c.get("/")
    assert r.status_code == 200 and "script-src 'self'" in r.headers["content-security-policy"]
    assert c.get("/app.js").status_code == 200 and c.get("/style.css").status_code == 200
    for path in ("/play/", "/guide.js", "/welcome.js", "/welcome.css", "/icons.svg", "/landing.js", "/landing.css", "/theme.css", "/game-font.css", "/fonts/dm-sans-latin-400.woff2"):
        assert c.get(path).status_code == 200, path


def test_e2e_full_sprint_over_http_matches_bot(tmp_path, content):
    for pol in bot.POLICIES:
        e = Env(tmp_path, content, name=f"{pol}.db")
        c = e.signup("a@x.io")
        rid = new_run(c)
        b = bot.play(11, content, pol)
        Driver(c, rid).replay_bot(b)
        s = c.get(f"/api/v1/runs/{rid}/state").json()["state"]
        assert s["meters"] == b.s["meters"] and s["status"] == "ended"


def test_balance_yaml_has_only_numbers_not_logic():
    cfg = yaml.safe_load((Path(__file__).resolve().parents[1] / "content" / "balance.yaml").read_text())
    assert cfg["push"]["repeat_decay"] == 0.7 and cfg["time"]["real_to_game"] == 160 and cfg["time"]["day_minutes"] == 480


def test_guide_scoring_copy_matches_balance(content):
    """The in-game scoring guide explains scoring in plain words. Its numbers must not drift from content/balance.yaml."""
    b = content.balance
    js = (WEB / "guide.js").read_text(encoding="utf-8")
    push, sc, lim = b["push"], b["standup_cover"], b["limits"]
    expected = [
        f"+{push['points']['clean']} pts", f"+{push['points']['acceptable']} pts", f"−{abs(push['points']['runtime_error'])} pts",
        f"−{abs(b['attack_check']['points'])} pts", f"−{abs(b['attack_check']['rating'])} Rating",
        f"Suspicion −{abs(sc['accurate'])}", f"Suspicion +{sc['vague']}", f"Suspicion +{sc['wrong']}", f"Suspicion +{b['contradiction_cover']}",
        f"Suspicion +{push['dod_unticked_cover']}", f"{b['perks']['ai_assistant']['price']} pts",
        f"below {lim['rating_lose_below']}", f"Suspicion reaches {lim['cover_lose_at']}", f"{lim['warnings_lose_at']} strikes",
        f"wrong about 1 time in {round(1 / b['perks']['ai_assistant']['error_rate'])}", f"up to {b['process_score']['max_per_behaviour']} times",
    ]
    missing = [e for e in expected if e not in js]
    assert not missing, missing
