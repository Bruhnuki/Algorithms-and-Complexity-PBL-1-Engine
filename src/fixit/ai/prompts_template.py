"""Prompt for the templated project puzzles (kept apart from prompts.py to keep that file readable)."""
from __future__ import annotations

from ..rules.content import Content
from .guardrails import SYSTEM, clean_value

TASK_TEMPLATE = """TASK: dress up one coding puzzle for the game. The game writes the code and the examples itself; you only choose the names and words so the puzzle fits the theme.
Return JSON with: title (2 to 6 words, a short problem title a customer would complain about); function (a short snake_case function name that fits the theme); flag and flag2 (two short snake_case names for yes/no inputs); amount (a short snake_case name for a number input); word_a, word_b, word_c (three different short plain lowercase words or two-word phrases the function can answer with, that fit the theme, letters only); dev1_intro and dev2_intro (the two teammates ask the player for help, 8 to 30 words each, in their own voices).
Rules: all names are different, lowercase letters and underscores only, no digits, and every name at most 14 characters. The three words contain only letters and spaces (no underscores). The words must make sense as answers for this theme. Plain ASCII."""


def template_messages(content: Content, spec: dict) -> list[dict]:
    d1, d2 = content.teammates["dev1"], content.teammates["dev2"]
    user = (f"{TASK_TEMPLATE}\n\nREQUEST DATA\nTheme of this Sprint: {clean_value(spec['theme'], 60)}. Product: {clean_value(spec.get('product', 'the product'), 80)}.\n"
            f"dev1_intro is {clean_value(d1['name'], 20)} ({clean_value(d1['voice'], 80)}); dev2_intro is {clean_value(d2['name'], 20)} ({clean_value(d2['voice'], 80)}).")
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
