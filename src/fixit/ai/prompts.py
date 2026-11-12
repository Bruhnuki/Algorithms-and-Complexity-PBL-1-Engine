"""Prompt builders. Layout of every request: the fixed SYSTEM prompt, then a fixed per-kind task block, then the small variable part last,
so the engine can reuse its cached prefix and only reads the new tail. All variable text comes from the game's own content, sanitised."""
from __future__ import annotations

import random

from ..rules.content import Content
from .guardrails import SYSTEM, clean_value

AREAS = ["coupons", "delivery slots", "card payments", "product search", "customer reviews", "gift cards", "login and passwords", "order tracking",
         "returns and refunds", "wish lists", "stock levels", "loyalty points", "the checkout page", "push notifications", "the mobile app"]
SITUATIONS = ["a teammate asks for help", "a stakeholder pushes for a change", "the team disagrees about how to work", "something is blocked",
              "a shortcut tempts the team", "work is unclear", "a promise was made without asking the team", "quality is slipping"]
# (function name, what it does, level). Level 2 and 3 only reach players in later Sprints.
TOPICS = [("coupon_note", "a coupon: returns \"valid\" when code is 1, otherwise \"expired\"", 1), ("stock_label", "stock: returns \"in stock\" when count is 1, otherwise \"sold out\"", 1),
          ("review_label", "reviews: returns \"verified\" when verified is 1, otherwise \"unverified\"", 1), ("gift_wrap_fee", "gift wrap: returns 0 when wrap is 0, otherwise returns 3", 1),
          ("member_price", "price: returns price minus 5 when member is 1, otherwise price", 1), ("double_points", "loyalty: returns points times 2 when bonus is 1, otherwise points", 1),
          ("night_fee", "fee: returns 4 when night is 1, otherwise 0", 1), ("trial_days", "trial: returns 14 when new is 1, otherwise 0", 1),
          ("refund_amount", "refund: returns price when damaged is 1, otherwise price divided by 2", 1), ("cart_label", "cart: returns \"empty\" when items is 0, otherwise \"has items\"", 1),
          ("age_gate", "age gate: returns \"allowed\" when adult is 1, otherwise \"blocked\"", 1), ("ship_speed", "shipping: returns \"fast\" when express is 1, otherwise \"standard\"", 1),
          ("tax_total", "total: returns price plus tax, where tax is price divided by 10", 2), ("tip_total", "tip: returns bill plus tip, where tip is bill divided by 5", 2),
          ("ship_cost", "shipping: when member is 1 return 0; otherwise when express is 1 return 9, else return 5 (write it as an if inside the else block, never else-if)", 2),
          ("vip_discount", "discount: when vip is 1 return price minus 10; otherwise when coupon is 1 return price minus 5, else return price", 2),
          ("order_status", "status: when paid is 0 return \"unpaid\"; otherwise when shipped is 1 return \"sent\", else return \"packing\"", 3),
          ("late_fee", "late fee: when late is 0 return 0; otherwise when vip is 1 return 2, else return 6 (write it as an if inside the else block, never else-if)", 2),
          ("seat_price", "seat price: when child is 1 return 8; otherwise when senior is 1 return 10, else return 15 (write it as an if inside the else block, never else-if)", 2),
          ("sale_total", "sale: when sale is 1 return price minus price divided by 4, otherwise return price", 2),
          ("gate_pass", "gate: when badge is 0 return \"denied\"; otherwise when guest is 1 return \"escort\", else return \"enter\" (write it as an if inside the else block, never else-if)", 3),
          ("parcel_cost", "parcel: when express is 1 return 12; otherwise when heavy is 1 return 9, else return 4 (write it as an if inside the else block, never else-if)", 3),
          ("refund_type", "refund: when paid is 0 return \"none\"; otherwise when damaged is 1 return \"full\", else return \"half\" (write it as an if inside the else block, never else-if)", 3)]

TASK_SCENARIO = """TASK: write one scenario.
Return JSON with: title (3 to 8 words); dev1_says (the first teammate tells the player the problem and asks what to do, in that teammate's voice); dev2_says (the same problem told by the second teammate in their own voice, different wording); best, weak, harmful: each an object with text (what the player answers) and feedback (one or two plain sentences saying why it works or not).
Rules: best follows the Scrum idea and is clearly the wisest; weak is a tempting half-measure that does not solve it; harmful goes against Scrum and does real damage. All three answers are realistic things a person might say, similar in length, and none reveals which is best. A feedback sentence about a weak or harmful answer must not start with praise; a feedback sentence about the best answer must not start with a refusal. No numbers anywhere. Do not mention points, scores, or rewards."""

TASK_CHALLENGE = """TASK: write one coding puzzle in ScrumScript.
Return JSON with: title (2 to 6 words); doc (one or two plain sentences: what the function must return, and what is going wrong); function; params; examples (exactly 5, each with input and expected; use 0 or 1 for yes/no flags); correct_source (the whole correct function, one line per array item, two spaces of indent per level, last item is just a closing brace); dev1_intro and dev2_intro (the two teammates ask the player for help in their own voices, 8 to 30 words each).
Rules: the correct_source must give the expected value for all 5 examples. Use only ScrumScript: there is no else-if (write } else { and put the next if inside it) and no var. Examples must use the same kind of value for expected every time. Plain ASCII.
Example of the shape (do not copy its content):
{"title": "Empty carts look full", "doc": "cart_note(items) must return \\"empty\\" when items is 0 and \\"has items\\" otherwise. Right now an empty cart says \\"has items\\".", "function": "cart_note", "params": ["items"], "examples": [{"input": [0], "expected": "empty"}, {"input": [2], "expected": "has items"}, {"input": [0], "expected": "empty"}, {"input": [5], "expected": "has items"}, {"input": [0], "expected": "empty"}], "correct_source": ["function cart_note(items) {", "  if items == 0 {", "    return \\"empty\\"", "  } else {", "    return \\"has items\\"", "  }", "}"], "dev1_intro": "Empty carts claim to have items. I have been staring at it too long. Your turn.", "dev2_intro": "Um, an empty cart says it has items. I am stuck, sorry. Could you find the line?"}"""

TASK_JUDGE = """TASK: you are a strict Scrum teacher checking a classroom scenario. Reply with JSON: best_letter (the one answer that best follows the Scrum idea), fits_idea (true only if that answer clearly applies the Scrum idea), makes_sense (true only if the situation is realistic for a small team and the three answers are coherent, distinct, and not contradictory)."""


def scenario_spec(content: Content, rnd: random.Random, max_level: int = 3, min_level: int = 1) -> dict:
    beats = [b for b in content.guide.get("beats", []) if b.get("teach") and b.get("concept") and min_level <= b.get("sprint", 1) <= max_level]
    b = rnd.choice(beats)
    return {"concept": b["concept"], "teach": b["teach"], "level": b["sprint"], "area": rnd.choice(AREAS), "situation": rnd.choice(SITUATIONS)}


def scenario_messages(content: Content, spec: dict) -> list[dict]:
    d1, d2 = content.teammates["dev1"], content.teammates["dev2"]
    user = (f"{TASK_SCENARIO}\n\nREQUEST DATA\nScrum idea: {clean_value(spec['concept'], 60)}. {clean_value(spec['teach'])}\n"
            f"Topic: {clean_value(spec['area'], 40)}. Situation: {clean_value(spec['situation'], 60)}.\n"
            f"dev1 is {clean_value(d1['name'], 20)}: {clean_value(d1['voice'], 80)}\ndev2 is {clean_value(d2['name'], 20)}: {clean_value(d2['voice'], 80)}")
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def judge_messages(item: dict, spec: dict) -> list[dict]:
    opts = "\n".join(f"{'ABC'[i]}. {clean_value(a['text'], 200)}" for i, a in enumerate(item["answers"]))
    user = (f"{TASK_JUDGE}\n\nREQUEST DATA\nScrum idea: {clean_value(spec['concept'], 60)}. {clean_value(spec['teach'])}\n"
            f"Situation told to the player: {clean_value(item['prompts']['dev1'], 300)}\nAnswers:\n{opts}")
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def challenge_spec(content: Content, rnd: random.Random, max_level: int = 3, min_level: int = 1) -> dict:
    fn, what, level = rnd.choice([t for t in TOPICS if min_level <= t[2] <= max_level])
    return {"function": fn, "what": what, "level": level}


def challenge_messages(content: Content, spec: dict) -> list[dict]:
    d1, d2 = content.teammates["dev1"], content.teammates["dev2"]
    if spec.get("theme"):   # a project's own puzzles: the model invents the function to fit the Sprint theme
        task = (f"Invent the function yourself: a short snake_case name and one simple rule that fits the theme '{clean_value(spec['theme'], 60)}' in {clean_value(spec.get('product', 'the product'), 80)}, "
                f"using 0 or 1 flags and small numbers, if/else only. Use your own parameter names and different example values than the sample. The correct_source must be {_LINES[spec['level']]} lines.\n")
    else:
        task = (f"Function name: {clean_value(spec['function'], 30)}. It handles {clean_value(spec['what'], 200)}. "
                f"Use your own parameter name(s) and different example values than the sample. The correct_source must be {_LINES[spec['level']]} lines.\n")
    user = (f"{TASK_CHALLENGE}\n\nREQUEST DATA\n{task}"
            f"dev1_intro is {clean_value(d1['name'], 20)} ({clean_value(d1['voice'], 80)}); dev2_intro is {clean_value(d2['name'], 20)} ({clean_value(d2['voice'], 80)}).")
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


_LINES = {1: "5 to 8", 2: "7 to 12", 3: "9 to 15"}


# ---------------------------------------------------------------- quiz questions (Scrum Guide beats) and project outlines
WHEN_OPENER = {"planning": "Sprint Planning", "daily_1": "Daily Scrum", "daily_2": "Daily Scrum", "review": "Sprint Review", "retro": "Sprint Retrospective"}

TASK_QUIZ = """TASK: write one multiple-choice Scrum question for the game's guided scenes.
Return JSON with: scene (one or two plain sentences that set the moment and begin with the event name given in the request; a teammate may say one short thing); question (one short question about the Scrum idea); right (the choice that correctly applies the idea); wrong_a and wrong_b (two believable but wrong choices, different mistakes); each choice is an object with text (what the player picks, 3 to 14 words) and feedback (one or two plain sentences explaining why it is right, or why it is not).
Rules: only the Scrum idea given in the request is tested, and right must agree exactly with the teaching line. The wrong choices must be wrong because of that idea, not because of a trick. Feedback for a wrong choice must not start with praise. Feedback for the right choice must not start with a refusal. No numbers, no points or scores, no lists."""

TASK_OUTLINE = """TASK: write the outline of one new project for the game.
Return JSON with: title (2 to 7 words, the project's name); premise (exactly 3 plain sentences: what the app is and what is going wrong for its users, what the player's job is as Scrum Master, and a hint at the pressure); sprints (exactly 3 items, one per Sprint, each with theme (2 to 6 words) and goal (a Sprint Goal sentence of 6 to 16 words that a customer would care about)).
Rules: a small team builds one software product for ordinary customers. The three Sprint themes must be about three different parts of that product and must make sense in order, from basics to harder problems. Invent the product and its company name; never use a real brand or real person. Plain ASCII, no numbers."""

PROJECT_TONE = {2: "A bigger app, a bigger mess: more features, more customers, a few things already breaking.", 3: "Real users, real pressure: the product is live, mistakes are costly and the stakeholders are impatient."}


def quiz_spec(content: Content, rnd: random.Random, beat: dict) -> dict:
    return {"for_beat": beat["id"], "concept": beat["concept"], "teach": beat["teach"], "when": beat["when"], "sprint": beat["sprint"], "speaker": beat["speaker"], "level": beat["sprint"]}


def quiz_messages(content: Content, spec: dict) -> list[dict]:
    user = (f"{TASK_QUIZ}\n\nREQUEST DATA\nScrum idea: {clean_value(spec['concept'], 80)}. {clean_value(spec['teach'])}\n"
            f"Event the scene starts with: {WHEN_OPENER.get(spec['when'], 'Sprint Planning')}. Setting: a small team building {clean_value(spec.get('product', 'a shopping app called Amazin'), 80)}. "
            f"Speaker in the scene: {clean_value(content.teammates.get(spec['speaker'], {}).get('name', 'Herb the heron'), 20)}.")
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def judge_quiz_messages(item: dict, spec: dict) -> list[dict]:
    opts = "\n".join(f"{'ABC'[i]}. {clean_value(c['text'], 200)}" for i, c in enumerate(item["choices"]))
    user = (f"{TASK_JUDGE}\n\nREQUEST DATA\nScrum idea: {clean_value(spec['concept'], 80)}. {clean_value(spec['teach'])}\n"
            f"Scene: {clean_value(item['scene'], 300)} Question: {clean_value(item['question'], 200)}\nAnswers:\n{opts}")
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def outline_spec(n: int, rnd: random.Random) -> dict:
    return {"n": n, "tone": PROJECT_TONE.get(n, PROJECT_TONE[2]), "flavour": rnd.choice(AREAS)}


def outline_messages(content: Content, spec: dict) -> list[dict]:
    user = (f"{TASK_OUTLINE}\n\nREQUEST DATA\nProject number {spec['n']} of 3. {clean_value(spec['tone'], 200)} "
            f"One area the product could involve: {clean_value(spec['flavour'], 40)}. The team: Ines and Tobi (developers), Marlo (Product Owner); the player is the Scrum Master.")
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


SHAPES = {   # what the rule of a project puzzle looks like; the model invents names and values to fit the Sprint theme
    2: ["when FLAG is 1 return WORD_A, otherwise return WORD_B (flags are 0 or 1; the words are short plain words)",
        "when FLAG is 1 return AMOUNT minus a small whole number, otherwise return AMOUNT (two inputs: FLAG and AMOUNT)",
        "when FLAG is 0 return a small whole number; otherwise when FLAG2 is 1 return another small number, else return a third (an if inside the else block)"],
    3: ["when FLAG is 0 return WORD_A; otherwise when FLAG2 is 1 return WORD_B, else return WORD_C (an if inside the else block, short plain words)",
        "when FLAG is 1 return AMOUNT times 2; otherwise when FLAG2 is 1 return AMOUNT plus 3, else return AMOUNT (an if inside the else block, inputs FLAG, FLAG2, AMOUNT)",
        "when FLAG is 1 return AMOUNT divided by 2, otherwise return AMOUNT minus 1 (two inputs: FLAG and AMOUNT)"]}


def themed_challenge_spec(theme: str, level: int, product: str, rnd: random.Random | None = None) -> dict:
    shape = (rnd or random.Random(0)).choice(SHAPES[min(3, max(2, level))])
    return {"function": None, "what": None, "theme": theme, "product": product, "level": level, "shape": shape}
