"""Turn the model's JSON proposal into a game item, or reject it with a short reason.

Scenario: the model writes text for three ROLES (best, weak, harmful). The game shuffles them, numbers the ids and sets
the trust values. Challenge: the model writes one correct line, one buggy line and one plausible wrong line; the game builds
the rest of the ticket and proves every option with the ScrumScript interpreter.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path

import jsonschema

from ..rules import interp
from ..rules.content import Content, source_with
from . import guardrails as G

TRUST = {"best": 3, "weak": -1, "harmful": -5}   # same values as the authored scenarios; the model never sets them
WORD = re.compile(r"[A-Za-z']+")
BAD_TEXT = re.compile(r"(https?://|www\.|@\w|```|[#*`<>{}\[\]\\|]|\bTODO\b|\bas an ai\b|\blanguage model\b)", re.I)
PROFANE = re.compile(r"\b(fuck\w*|shit\w*|bitch\w*|bastard|damn|crap|idiot|stupid|dumb|hate you|kill|retard\w*)\b", re.I)


def _words(s: str) -> list[str]:
    return WORD.findall(s)


def _tokens(s: str) -> set[str]:
    return {w.lower() for w in _words(s) if len(w) > 3}


def similar(a: str, b: str) -> float:
    x, y = _tokens(a), _tokens(b)
    return len(x & y) / len(x | y) if x and y else 0.0


def clean_text(s, lo: int, hi: int, what: str, *, scenario: bool = True) -> str | None:
    """None when the text is fine, else the reason."""
    if not isinstance(s, str):
        return f"{what}:type"
    bad = G.output_policy(s, scenario=scenario)
    if bad:
        return f"{what}:{bad}"
    n = len(_words(s))
    if n < lo or n > hi:
        return f"{what}:length"
    if BAD_TEXT.search(s):
        return f"{what}:symbols"
    if PROFANE.search(s):
        return f"{what}:language"
    if not s.isascii():
        return f"{what}:non_ascii"
    return None


def short_id(prefix: str, *parts: str) -> str:
    return f"{prefix}_{hashlib.sha1('|'.join(parts).encode()).hexdigest()[:8]}"


# ---------------------------------------------------------------- scenarios
SCENARIO_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["title", "dev1_says", "dev2_says", "best", "weak", "harmful"],
    "properties": {"title": {"type": "string"}, "dev1_says": {"type": "string"}, "dev2_says": {"type": "string"},
                   **{k: {"type": "object", "additionalProperties": False, "required": ["text", "feedback"],
                          "properties": {"text": {"type": "string"}, "feedback": {"type": "string"}}} for k in TRUST}},
}


def validate_scenario(raw, spec: dict, content: Content, existing_texts: list[str]) -> tuple[dict | None, str]:
    try:
        jsonschema.validate(raw, SCENARIO_SCHEMA)
    except jsonschema.ValidationError:
        return None, "schema"
    lv = G.LEVELS[min(3, max(1, spec.get("level", 1)))]
    checks = [clean_text(raw["title"], 2, 9, "title"), clean_text(raw["dev1_says"], *lv["scenario_words"], "dev1_says"), clean_text(raw["dev2_says"], *lv["scenario_words"], "dev2_says")]
    for role in TRUST:
        checks += [clean_text(raw[role]["text"], *lv["answer_words"], f"{role}.text"), clean_text(raw[role]["feedback"], *lv["feedback_words"], f"{role}.feedback"),
                   G.tone_policy(role, raw[role]["feedback"]) if isinstance(raw[role]["feedback"], str) else None]
    bad = next((c for c in checks if c), None)
    if bad:
        return None, bad
    texts = [raw[r]["text"] for r in TRUST]
    if any(similar(texts[i], texts[j]) > 0.6 for i in range(3) for j in range(i + 1, 3)):
        return None, "answers_too_similar"
    for dev, other in (("dev1_says", "dev2_says"), ("dev2_says", "dev1_says")):   # two different voices, not one text twice
        if similar(raw[dev], raw[other]) > 0.75:
            return None, "prompts_too_similar"
    if any(similar(raw["best"]["feedback"], raw[r]["feedback"]) > 0.7 for r in ("weak", "harmful")):
        return None, "feedback_not_distinct"
    blob = " ".join([raw["title"], raw["dev1_says"], raw["dev2_says"], *texts])
    for t in content.teammates.values():   # never reveal another teammate's secret
        if t.get("secret") and sum(w in _tokens(blob) for w in _tokens(t["secret"])) >= 3:
            return None, "leaks_secret"
    if any(similar(blob, e) > 0.6 for e in existing_texts):
        return None, "duplicate"
    rnd = random.Random(short_id("o", raw["title"], blob))
    roles = list(TRUST)
    rnd.shuffle(roles)
    answers = []
    for i, role in enumerate(roles):
        a = {"id": "abc"[i], "text": raw[role]["text"].strip(), "trust": TRUST[role], "feedback": raw[role]["feedback"].strip()}
        if role == "best":
            a["best"] = True
        answers.append(a)
    hid = short_id("hr_scenario_gen", raw["title"], blob)
    item = {"id": hid, "type": "scenario", "title": raw["title"].strip(), "prompts": {"dev1": raw["dev1_says"].strip(), "dev2": raw["dev2_says"].strip()},
            "answers": answers, "generated": True, "concept": spec.get("concept"), "level": spec.get("level", 1)}
    return item, "ok"


# ---------------------------------------------------------------- challenges
CHALLENGE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["title", "doc", "function", "params", "examples", "correct_source", "dev1_intro", "dev2_intro"],
    "properties": {
        "title": {"type": "string"}, "doc": {"type": "string"}, "function": {"type": "string"},
        "params": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3},
        "examples": {"type": "array", "minItems": 5, "maxItems": 5, "items": {"type": "object", "additionalProperties": False, "required": ["input", "expected"],
                                                                              "properties": {"input": {"type": "array", "items": {"type": ["number", "string"]}}, "expected": {"type": ["number", "string"]}}}},
        "correct_source": {"type": "array", "items": {"type": "string"}, "minItems": 5, "maxItems": 12},
        "bug_line": {"type": "integer"}, "buggy_line_text": {"type": "string"},
        "dev1_intro": {"type": "string"}, "dev2_intro": {"type": "string"}}}
IDENT = re.compile(r"^[a-z][a-z_]{2,24}$")
GLOSSARY = {"==": "Checks whether two things are equal.", "if": "Runs the next block only when the condition is true.",
            "return": "Hands a value back to whoever called the function.", "+": "Addition, or joining two pieces of text together.",
            "-": "Subtraction.", "*": "Multiplication.", "/": "Division. Dividing by zero crashes the program."}


def _outcome(content: Content, source: str, ticket: dict) -> str:
    runs = interp.run_examples(source, ticket["examples"], ticket["params"], allowed=content.allowed, step_limit=content.balance["interpreter"]["step_limit"])
    if any(r["error"] for r in runs):
        return "error"
    return "pass" if all(r["pass"] for r in runs) else "fail"


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _flawed(line: str, string_result: bool) -> str | None:
    """A fix that works but is sloppy (same trick the authored tickets use)."""
    m = re.match(r"^(\s*return\s+)(.+)$", line)
    return f"{m.group(1)}{m.group(2)} + {chr(34) * 2 if string_result else '0'}" if m else None


def _locate_bug(src: list[str], n: int, buggy: str) -> int | None:
    """The line the buggy text replaces: same indentation and same first word, nearest to where the model said."""
    first = buggy.split()[0] if buggy.split() else ""
    cands = [i + 1 for i in range(1, len(src) - 1) if src[i].split() and src[i].split()[0] == first and _indent(src[i]) == _indent(buggy)
             and src[i].strip() not in ("}", "} else {") and src[i].strip() != buggy.strip()]
    return min(cands, key=lambda i: abs(i - n)) if cands else None


def _derive_bug(content: Content, base: dict, src: list[str], examples: list[dict], key: str) -> tuple[int | None, str | None]:
    """Break a `return` line by returning another value the examples expect; the first break the interpreter confirms wins."""
    consts = list(dict.fromkeys(json.dumps(e["expected"]) for e in examples)) + ['"none"', "0"]
    rets = [i for i in range(1, len(src) - 1) if src[i].strip().startswith("return ")]
    if not rets:
        return None, None
    start = sum(map(ord, key)) % len(rets)                 # which return line first varies from puzzle to puzzle, but is the same on every run
    for i in rets[start:] + rets[:start]:
        for c in consts:
            cand = f"{_indent(src[i])}return {c}"
            if cand.strip() != src[i].strip() and _outcome(content, source_with({**base, "buggy_line": i + 1}, {"text": cand}), base) in ("fail", "error"):
                return i + 1, cand
    return None, None


def _wrong_line(content: Content, base: dict, correct: str, buggy: str, examples: list[dict]) -> str | None:
    """A plausible fix that runs but is wrong. Candidates are tried against the interpreter; the first that really fails wins."""
    ind = _indent(correct)
    consts = [json.dumps(e["expected"]) for e in examples] + ['"none"', '"unknown"', "0", "1", '"ok"']
    if correct.strip().startswith("return "):
        pool = [f"{ind}return {c}" for c in dict.fromkeys(consts)]
    else:   # a condition line: flip what it compares against
        pool = [re.sub(r"== *(\d+)", lambda m: f"== {int(m.group(1)) + 1}", correct, count=1)]
    for cand in pool:
        if cand.strip() not in (correct.strip(), buggy.strip()) and _outcome(content, source_with(base, {"text": cand}), base) == "fail":
            return cand
    return None


def _crashing(line: str, params: list[str]) -> str | None:
    """The same line with a name that does not exist, like a typo."""
    if line.strip().startswith("return "):
        return f"{_indent(line)}return value_missing"     # a name that was never defined, like the authored "return note"
    masked = re.sub(r'"[^"]*"', lambda m: " " * len(m.group()), line)
    hit = [m for m in re.finditer(r"[a-z_]+", masked) if m.group() in params]
    if not hit:
        return None
    m = hit[-1]
    return line[: m.end()] + "x" + line[m.end():]


def validate_challenge(raw, spec: dict, content: Content, existing_texts: list[str]) -> tuple[tuple[dict, dict] | None, str]:
    """-> ((ticket, help_request), "ok") or (None, reason). The interpreter is the judge of every line of code."""
    try:
        jsonschema.validate(raw, CHALLENGE_SCHEMA)
    except jsonschema.ValidationError:
        return None, "schema"
    for chk in (clean_text(raw["title"], 1, 7, "title", scenario=False), clean_text(raw["doc"], 10, 55, "doc", scenario=False), clean_text(raw["dev1_intro"], 6, 40, "dev1_intro", scenario=False), clean_text(raw["dev2_intro"], 6, 40, "dev2_intro", scenario=False)):
        if chk:
            return None, chk
    fn, params, src = raw["function"], raw["params"], [ln.replace("	", "  ").rstrip() for ln in raw["correct_source"]]
    if re.match(r"^\s*\}\W*$", src[-1]):
        src[-1] = "}"                                   # a stray character after the last brace is a typo, not a different program
    while len(src) > 1 and src[-1] == "}" and sum(x.count("}") for x in src) > sum(x.count("{") for x in src):
        src.pop()                                       # one closing brace too many
    lv = G.LEVELS[min(3, max(1, spec.get("level", 1)))]
    if not IDENT.match(fn) or fn not in raw["doc"] or any(not re.match(r"^[a-z][a-z_]{0,20}$", p) for p in params) or len(set(params)) != len(params):
        return None, "names"
    if src[0].strip() != f"function {fn}({', '.join(params)}) {{" or src[-1].strip() != "}":
        return None, "function_shape"
    if not lv["source_lines"][0] <= len(src) <= lv["source_lines"][1]:
        return None, "too_long_or_short_for_level"
    ex = raw["examples"]
    if any(len(e["input"]) != len(params) for e in ex) or len({json.dumps(e["input"]) for e in ex}) < 2:
        return None, "examples"
    if len({json.dumps(e["expected"]) for e in ex}) < 2:
        return None, "examples_all_same"
    base = {"examples": ex, "params": params, "source": src, "buggy_line": 2, "blank_line": None}
    if _outcome(content, chr(10).join(src), base) != "pass":
        return None, "correct_code_fails"             # the model's own "correct" code must pass its own examples
    n = buggy_line = None
    if raw.get("bug_line") and raw.get("buggy_line_text"):   # the model may suggest the bug; the game only keeps it when it works
        bl = raw["buggy_line_text"].rstrip()
        n0 = _locate_bug(src, raw["bug_line"], bl)
        if n0 and _indent(src[n0 - 1]) == _indent(bl) and _outcome(content, source_with({**base, "buggy_line": n0}, {"text": bl}), base) in ("fail", "error"):
            n, buggy_line = n0, bl
    if n is None:
        n, buggy_line = _derive_bug(content, base, src, ex, raw["title"])   # the game breaks the code itself: swap a returned value, prove it fails
    if n is None:
        return None, "bug_not_a_bug"
    base = {**base, "buggy_line": n}
    correct_line = src[n - 1]
    original = _outcome(content, source_with(base, {"text": buggy_line}), base)
    wrong_line = _wrong_line(content, base, correct_line, buggy_line, ex)   # built by the game, proven by the interpreter
    if wrong_line is None:
        return None, "cannot_build_wrong_option"
    string_result = any(isinstance(e["expected"], str) for e in ex)
    flawed, crash = _flawed(correct_line, string_result), _crashing(correct_line, params)
    if not flawed or not crash:
        return None, "cannot_build_options"
    if _outcome(content, source_with(base, {"text": flawed}), base) != "pass":
        return None, "flawed_option_fails"
    if _outcome(content, source_with(base, {"text": crash}), base) != "error":
        return None, "crash_option_runs"
    tid = short_id("help_gen", fn, raw["title"])
    rnd = random.Random(tid)
    order = ["correct", "wrong", "crash", "flawed"]
    rnd.shuffle(order)
    spec_of = {"correct": ("correct", None, "pass", correct_line), "wrong": ("wrong_hidden", "wrong_result", "fail", wrong_line),
               "crash": ("crashes", "runtime_error", "error", crash), "flawed": ("correct_small_flaw", "sloppy_fix", "pass", flawed)}
    options = [{"id": "abcd"[i], "text": spec_of[k][3], "effect": spec_of[k][0], "bug_type": spec_of[k][1], "run_outcome": spec_of[k][2]} for i, k in enumerate(order)]
    body = "\n".join(src)
    ticket = {"id": tid, "kind": "fix", "difficulty": lv["difficulty"], "concept": "conditions", "title": raw["title"].strip(), "doc": raw["doc"].strip(),
              "params": params, "examples": ex, "source": [(buggy_line if i + 1 == n else ln) for i, ln in enumerate(src)], "buggy_line": n, "blank_line": None,
              "run_shows_failure": True, "options": options, "original_outcome": original,
              "glossary": {k: v for k, v in GLOSSARY.items() if (k if k.isalpha() else re.escape(k)) and (re.search(rf"\b{k}\b", body) if k.isalpha() else k in body)} or {"return": GLOSSARY["return"]},
              "generated": True}
    schema = json.loads((Path(__file__).resolve().parents[3] / "content" / "schemas" / "ticket.schema.json").read_text(encoding="utf-8"))
    try:
        jsonschema.validate(ticket, schema)
    except jsonschema.ValidationError:
        return None, "ticket_schema"
    sig = f"{raw['title']} {raw['doc']}"
    if any(similar(sig, e) > 0.6 for e in existing_texts):
        return None, "duplicate"
    hid = short_id("hr_challenge_gen", tid)
    help_def = {"id": hid, "type": "challenge", "ticket": tid, "title": raw["title"].strip(),
                "intros": {"dev1": raw["dev1_intro"].strip(), "dev2": raw["dev2_intro"].strip()}, "generated": True,
                "concept": "conditions", "level": spec.get("level", 1)}
    return (ticket, help_def), "ok"


# ---------------------------------------------------------------- judge (second opinion on the Scrum teaching)
JUDGE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["best_letter", "fits_idea", "makes_sense"],
                "properties": {"best_letter": {"enum": ["A", "B", "C"]}, "fits_idea": {"type": "boolean"}, "makes_sense": {"type": "boolean"}}}


def judge_agrees(item: dict, judge_raw) -> bool:
    """The judge was shown the three answers in the game's shuffled order, without the labels."""
    try:
        jsonschema.validate(judge_raw, JUDGE_SCHEMA)
    except jsonschema.ValidationError:
        return False
    best = next(i for i, a in enumerate(item["answers"]) if a.get("best"))
    return "ABC"[best] == judge_raw["best_letter"] and judge_raw["fits_idea"] and judge_raw["makes_sense"]


# ---------------------------------------------------------------- quiz questions (guide beats)
_CH = {"type": "object", "additionalProperties": False, "required": ["text", "feedback"], "properties": {"text": {"type": "string"}, "feedback": {"type": "string"}}}
QUIZ_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["scene", "question", "right", "wrong_a", "wrong_b"],
               "properties": {"scene": {"type": "string"}, "question": {"type": "string"}, "right": _CH, "wrong_a": _CH, "wrong_b": _CH}}


def validate_quiz(raw, spec: dict, content: Content, existing_texts: list[str]) -> tuple[dict | None, str]:
    """A new wording of one authored Scrum question. The game keeps the slot, the speaker and the teaching line; the model writes the words."""
    try:
        jsonschema.validate(raw, QUIZ_SCHEMA)
    except jsonschema.ValidationError:
        return None, "schema"
    checks = [clean_text(raw["scene"], 10, 55, "scene"), clean_text(raw["question"], 4, 26, "question")]
    for role in ("right", "wrong_a", "wrong_b"):
        checks += [clean_text(raw[role]["text"], 3, 16, f"{role}.text"), clean_text(raw[role]["feedback"], 6, 42, f"{role}.feedback"),
                   G.tone_policy("best" if role == "right" else "weak", raw[role]["feedback"]) if isinstance(raw[role]["feedback"], str) else None]
    bad = next((c for c in checks if c), None)
    if bad:
        return None, bad
    opener = WHEN_OPENER_CHECK.get(spec["when"], "")
    if opener and not raw["scene"].lstrip().lower().startswith(opener.lower()):
        return None, "scene_opener"
    texts = [raw[r]["text"] for r in ("right", "wrong_a", "wrong_b")]
    if any(similar(texts[i], texts[j]) > 0.6 for i in range(3) for j in range(i + 1, 3)):
        return None, "answers_too_similar"
    if any(similar(raw["right"]["feedback"], raw[r]["feedback"]) > 0.7 for r in ("wrong_a", "wrong_b")):
        return None, "feedback_not_distinct"
    blob = " ".join([raw["scene"], raw["question"], *texts])
    for t in content.teammates.values():
        if t.get("secret") and sum(w in _tokens(blob) for w in _tokens(t["secret"])) >= 3:
            return None, "leaks_secret"
    if any(similar(blob, e) > 0.6 for e in existing_texts):
        return None, "duplicate"
    rnd = random.Random(short_id("q", spec["for_beat"], blob))
    roles = ["right", "wrong_a", "wrong_b"]
    rnd.shuffle(roles)
    choices = []
    for i, role in enumerate(roles):
        c = {"id": "abc"[i], "text": raw[role]["text"].strip(), "feedback": raw[role]["feedback"].strip()}
        if role == "right":
            c["correct"] = True
        choices.append(c)
    item = {"id": short_id("beat_gen", spec["for_beat"], blob), "sprint": spec["sprint"], "when": spec["when"], "kind": "quiz", "speaker": spec["speaker"],
            "concept": spec["concept"], "scene": raw["scene"].strip(), "question": raw["question"].strip(), "choices": choices, "teach": spec["teach"],
            "generated": True, "for_beat": spec["for_beat"], "level": spec.get("level", 1)}
    return item, "ok"


WHEN_OPENER_CHECK = {"planning": "Sprint Planning", "daily_1": "Daily Scrum", "daily_2": "Daily Scrum", "review": "Sprint Review", "retro": "Sprint Retrospective"}


def judge_agrees_quiz(item: dict, judge_raw) -> bool:
    try:
        jsonschema.validate(judge_raw, JUDGE_SCHEMA)
    except jsonschema.ValidationError:
        return False
    best = next(i for i, c in enumerate(item["choices"]) if c.get("correct"))
    return "ABC"[best] == judge_raw["best_letter"] and judge_raw["fits_idea"] and judge_raw["makes_sense"]


# ---------------------------------------------------------------- a project's outline
OUTLINE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["title", "premise", "sprints"],
                  "properties": {"title": {"type": "string"}, "premise": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "string"}},
                                 "sprints": {"type": "array", "minItems": 3, "maxItems": 3,
                                             "items": {"type": "object", "additionalProperties": False, "required": ["theme", "goal"],
                                                       "properties": {"theme": {"type": "string"}, "goal": {"type": "string"}}}}}}


def validate_outline(raw, spec: dict, existing_titles: list[str]) -> tuple[dict | None, str]:
    try:
        jsonschema.validate(raw, OUTLINE_SCHEMA)
    except jsonschema.ValidationError:
        return None, "schema"
    checks = [clean_text(raw["title"], 2, 8, "title")]
    checks += [clean_text(x, 8, 40, f"premise{i}") for i, x in enumerate(raw["premise"])]
    for i, sp in enumerate(raw["sprints"]):
        checks += [clean_text(sp["theme"], 2, 7, f"theme{i}"), clean_text(sp["goal"], 6, 20, f"goal{i}")]
    bad = next((c for c in checks if c), None)
    if bad:
        return None, bad
    themes = [sp["theme"] for sp in raw["sprints"]]
    if any(similar(themes[i], themes[j]) > 0.5 for i in range(3) for j in range(i + 1, 3)) or len({t.lower() for t in themes}) < 3:
        return None, "themes_too_similar"
    if any(similar(raw["title"], t) > 0.6 for t in existing_titles):
        return None, "duplicate"
    return {"title": raw["title"].strip(), "premise": [x.strip() for x in raw["premise"]],
            "sprints": [{"theme": sp["theme"].strip(), "goal": sp["goal"].strip()} for sp in raw["sprints"]]}, "ok"
