"""Templated puzzles for a project's tickets.

The game writes the code, the examples and the rule sentence; the interpreter produces every expected value. The model only supplies the story:
names and words that fit the Sprint theme. That keeps project puzzles correct by construction, so almost none are thrown away.
"""
from __future__ import annotations

import random
import re

import jsonschema

from ..rules import interp
from ..rules.content import Content, run_ticket
from .validate import IDENT, clean_text, validate_challenge

TEMPLATE_SCHEMA = {"type": "object", "additionalProperties": False,
                   "required": ["title", "function", "flag", "flag2", "amount", "word_a", "word_b", "word_c", "dev1_intro", "dev2_intro"],
                   "properties": {k: {"type": "string"} for k in ("title", "function", "flag", "flag2", "amount", "word_a", "word_b", "word_c", "dev1_intro", "dev2_intro")}}
SHAPES = {2: ["a", "b", "c"], 3: ["c", "d", "e"]}
_EX = {"a": [[1], [0], [1], [0], [1]], "b": [[1, 20], [0, 20], [1, 40], [0, 10], [1, 10]], "c": [[0, 0], [1, 1], [1, 0], [0, 1], [1, 1]],
       "d": [[1, 0, 10], [0, 1, 20], [0, 0, 30], [1, 1, 40], [0, 1, 10]], "e": [[1, 0], [0, 1], [0, 0], [1, 1], [0, 0]]}
_WORD = re.compile(r"^[a-z][a-z ]{1,22}[a-z]$")


def _template(shape: str, t: dict, k: int) -> tuple[list[str], list[str], str]:
    """-> (params, source lines, the rule in plain words)."""
    f, g, m, fn = t["flag"], t["flag2"], t["amount"], t["function"]
    A, B, C = (f'"{t[w]}"' for w in ("word_a", "word_b", "word_c"))
    if shape == "a":
        return [f], [f"function {fn}({f}) {{", f"  if {f} == 1 {{", f"    return {A}", "  } else {", f"    return {B}", "  }", "}"], \
            f"{fn}({f}) must return {A} when {f} is 1 and {B} otherwise."
    if shape == "b":
        n = (2, 5, 10)[k % 3]
        return [f, m], [f"function {fn}({f}, {m}) {{", f"  if {f} == 1 {{", f"    return {m} - {n}", "  } else {", f"    return {m}", "  }", "}"], \
            f"{fn}({f}, {m}) must return {m} minus {n} when {f} is 1, and {m} unchanged otherwise."
    if shape == "c":
        return [f, g], [f"function {fn}({f}, {g}) {{", f"  if {f} == 1 {{", f"    return {A}", "  } else {", f"    if {g} == 1 {{", f"      return {B}", "    } else {",
                        f"      return {C}", "    }", "  }", "}"], \
            f"{fn}({f}, {g}) must return {A} when {f} is 1. Otherwise it must return {B} when {g} is 1 and {C} when it is not."
    if shape == "d":
        return [f, g, m], [f"function {fn}({f}, {g}, {m}) {{", f"  if {f} == 1 {{", f"    return {m} * 2", "  } else {", f"    if {g} == 1 {{", f"      return {m} + 3",
                           "    } else {", f"      return {m}", "    }", "  }", "}"], \
            f"{fn}({f}, {g}, {m}) must return {m} times 2 when {f} is 1. Otherwise it must return {m} plus 3 when {g} is 1, and {m} unchanged when it is not."
    a, b, c = [(12, 8, 4), (9, 6, 3), (15, 10, 5)][k % 3]
    return [f, g], [f"function {fn}({f}, {g}) {{", f"  if {f} == 1 {{", f"    return {a}", "  } else {", f"    if {g} == 1 {{", f"      return {b}", "    } else {",
                    f"      return {c}", "    }", "  }", "}"], \
        f"{fn}({f}, {g}) must return {a} when {f} is 1. Otherwise it must return {b} when {g} is 1 and {c} when it is not."


def validate_templated(raw, spec: dict, content: Content, existing_texts: list[str]) -> tuple[tuple[dict, dict] | None, str]:
    """-> ((ticket, help_request), "ok") or (None, reason)."""
    try:
        jsonschema.validate(raw, TEMPLATE_SCHEMA)
    except jsonschema.ValidationError:
        return None, "schema"
    names = [raw["function"], raw["flag"], raw["flag2"], raw["amount"]]
    if not IDENT.match(raw["function"]) or any(not re.match(r"^[a-z][a-z_]{0,20}$", n) for n in names[1:]) or len(set(names)) != 4:
        return None, "names"
    words = [raw[w].strip().lower().replace("_", " ") for w in ("word_a", "word_b", "word_c")]
    if any(not _WORD.match(w) for w in words) or len(set(words)) != 3:
        return None, "words"
    for chk in (clean_text(raw["title"], 1, 7, "title", scenario=False), clean_text(raw["dev1_intro"], 6, 40, "dev1_intro", scenario=False),
                clean_text(raw["dev2_intro"], 6, 40, "dev2_intro", scenario=False), *(clean_text(w, 1, 3, "word", scenario=False) for w in words)):
        if chk:
            return None, chk
    level = spec.get("level", 2)
    shape = spec.get("shape") or random.Random(raw["title"]).choice(SHAPES[min(3, max(2, level))])
    t = {**raw, "word_a": words[0], "word_b": words[1], "word_c": words[2]}
    params, src, rule = _template(shape, t, sum(map(ord, raw["title"])))
    examples = []
    for args in _EX[shape]:
        try:
            out = interp.call(chr(10).join(src), args, allowed=content.allowed, step_limit=content.balance["interpreter"]["step_limit"])
        except interp.ScrumError:
            return None, "template_fails"
        examples.append({"input": args, "expected": int(out) if isinstance(out, float) and out == int(out) else out})
    built = {"title": raw["title"], "doc": rule + " Right now it gives a wrong answer for some inputs.", "function": raw["function"], "params": params,
             "examples": examples, "correct_source": src, "dev1_intro": raw["dev1_intro"], "dev2_intro": raw["dev2_intro"]}
    got, why = validate_challenge(built, {**spec, "level": level}, content, existing_texts)
    if not got:
        return None, why
    ticket, help_def = got
    fail = next((r for r in run_ticket(ticket, None, content) if not r["pass"]), None)   # say what is really going wrong, from the interpreter's own result
    if fail:
        given = ", ".join(f"{p} is {interp.fmt(a)}" for p, a in zip(ticket["params"], fail["input"]))
        ticket["doc"] = rule + f" Right now when {given} it gives {fail['error'] or interp.fmt(fail['actual'])} instead of {interp.fmt(fail['expected'])}."
    return (ticket, help_def), "ok"
