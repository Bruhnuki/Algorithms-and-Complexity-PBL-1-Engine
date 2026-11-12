"""The team's arguments in Slackish. The AI writes each heated line in the speaker's own voice when it is connected; these authored lines are the fallback
(and keep the demo working without it). What happens in the game (tension, who is fighting, what it costs) is decided by the reducer, never here."""
from __future__ import annotations

import json
import re

from ..engines import e1
from .gateway import MAX_WORDS, TONES, _leaks, _norm

ARGUE = {   # topic -> speaker -> lines (used in order, round by round)
    "venting": {"dev1": ["Don't take it out on me. I'm not the one who just got torn into.", "I'm angry too, but that's not on you or me. Stop snapping.", "We're both getting it from the boss. Fighting each other helps nobody."],
                "dev2": ["Sorry, I'm just really upset after what was said to us. I didn't mean to snap at you.", "It's like everything we do is wrong. I can't stop shaking, and now we're fighting.",
                         "Why is everyone yelling at everyone? I just want it to stop."],
                "po": ["Whatever is going on with the boss, don't drag the team into it. I have a board to face.", "I'm trying to hold this together and everyone's biting heads off.", "Can someone be professional? Please?"]},
    "handoffs": {"dev1": ["Tobi, that's the third ticket you've dumped on me today. I have my own work, you know.", "I'm not your safety net. Finish one thing without asking me to check it.",
                          "Fine. Say it to my face then: do you want me to do your job too?"],
                 "dev2": ["I'm not dumping anything! I just wanted a second opinion, I'm sorry, I'm trying.", "You make me feel stupid every time I ask. That's why I get things wrong!",
                          "Maybe if you didn't sigh every time I talk, I'd be less scared of messing up."]},
    "bluntness": {"dev1": ["Tobi, 'sorry' isn't a fix. Say what you actually did.", "I told you the truth about that patch. If it stings, the bug is the problem, not me.",
                            "Stop making me the villain. I'm the one cleaning up here."],
                  "dev2": ["You didn't have to say it like that in front of everyone, Ines.", "Every message from you feels like a verdict. I can't think when you're like this.",
                           "I'm trying to learn. Why does everything have to be a fight with you?"]},
    "scope": {"po": ["Ines, the board wants the discount rule in this Sprint. Just squeeze it in.", "Quality, quality... customers don't see tests, they see dates. Make it work.",
                     "I'm not asking, I'm telling the team what the business needs."],
              "dev1": ["Marlo, 'squeeze it in' is how we got the last outage. I'm not shipping it broken.", "You promised dates I never agreed to. Don't hand me your problem.",
                       "Then pick: fast, cheap or working. You don't get all three."]},
    "dates": {"po": ["I told the board Friday. Friday, Ines. Why is this a surprise?", "You people never give me numbers, so I make them up. That's on you.", "Do I need to escalate this? Because I can."],
              "dev1": ["You told the board, not us. Don't act shocked that we didn't sign up.", "I give honest estimates. You round them down and call it a plan.",
                       "Escalate. Maybe someone will finally ask us what's possible."]},
    "pressure": {"po": ["Tobi, why is this still open? I need status, not apologies.", "Everyone's panicking and you're the loudest. Pull it together.", "I don't have time to hold anyone's hand today."],
                 "dev2": ["I'm working as fast as I can! When you hover I can't think straight, sorry, sorry.", "You keep saying it's urgent. Everything is urgent. I'm scared of breaking it.",
                          "I can't do this when you shout. Please. Just give me one clear priority."]},
    "reassurance": {"po": ["Tobi, you asked me that yesterday. I need results, not another question.", "I can't keep reassuring you, I have investors to calm.", "Just decide something. Anything. Please."],
                    "dev2": ["I only wanted to check it's okay... I don't want to break anything.", "If nobody tells me I'm on the right track, I freeze. You know that.",
                             "It's easy to say 'just decide' when it's not your name on the bug."]}}
BANTER = {   # when things are going well they talk to each other too: speaker -> the other -> lines
    "dev1": {"dev2": ["Tobi, want me to look at that cart ticket with you?", "That patch looks decent. Don't tell anyone I said so.", "Coffee after this? You've earned it."],
             "po": ["Marlo, the discount rule is done. Yes, really, before the deadline.", "If you protect our test time, I'll protect your dates.", "Okay, that's a fair priority. Let's do it your way."]},
    "dev2": {"dev1": ["Yes please! I got stuck on the discount rule again.", "Thanks Ines, that helps a lot. I'll run the tests first this time.", "Coffee sounds great. I'll even buy!"],
             "po": ["Marlo, I think I can finish the checkout fix today!", "Thanks for the clear priority. It really helps me focus.", "I'll tell you the moment it's done, promise."]},
    "po": {"dev1": ["Ines, great work on that fix. The board will love it.", "Tell me what you need and I'll keep the extra requests away.", "Nice. That's exactly the quality I was hoping for."],
           "dev2": ["Tobi, good progress today. Keep going, you've got this.", "No rush on this one. Get it right and we're fine.", "Ask if you need anything. I'm here to unblock you."]}}
BREAK = {"dev1": "That's it. I'm not touching anything until this is sorted. Find someone else.", "dev2": "I... I can't. I'm sorry. I'm stepping away from this.",
         "po": "Enough. This team is a mess and it's landing on me. I'm out until someone fixes it."}
RESOLVED = {   # how it ended -> speaker -> what they say once it is over
    "listen": {"dev1": "Alright. Thanks for letting us say it out loud. I'll try to say things nicer.", "dev2": "Thank you for listening. I feel a bit less scared now.",
               "po": "Fair. I'll be clearer about dates. Let's get back to the Sprint."},
    "goal": {"dev1": "Sprint Goal. Right, we want the same thing. Fine. New rule: ask before piling on.", "dev2": "Okay! A working rule helps. I can follow a rule.",
             "po": "Agreed. One priority at a time. Back to work."},
    "chat": {"dev1": "...Okay. That helped, actually. Let's drop it.", "dev2": "Thanks. I'm sorry I got heated too.", "po": "Alright, point taken. Let's move on."},
    "sided": {"dev1": "Fine. If that's the call, that's the call.", "dev2": "Okay... I guess that's decided. Sorry.", "po": "Noted. Let's just get this done."}}
SIDED_LOSER = "So I'm the problem. Great. Fine."
UNMOVED = {"dev1": "I'm not ready to talk. Not while I'm this fed up.", "dev2": "I can't hear this right now, I'm too upset. Please, later.", "po": "Not now. I'm too angry to be reasonable."}
DISMISSED = {"dev1": "'Stop arguing' isn't a solution. It's a gag.", "dev2": "You just told us to stop... but nothing's solved. It's still there.", "po": "Telling us to be quiet doesn't fix a thing."}
PLAIN = {"dev1": "Ines", "dev2": "Tobi", "po": "Marlo"}
_BAD = re.compile(r"\b(fuck\w*|shit\w*|bitch|asshole|bastard|idiot|moron|stupid|nigg\w*|niger|faggot|retard\w*)\b|[{}]|\*\*|\"(tone|text)\"|/note|\bnote:", re.I)


EXPLAIN = {"dev1": "Fine, my side: I'm carrying too much, and nobody asks before piling more on.", "dev2": "My side... I'm scared of getting it wrong, so I keep asking. I don't want to break anything.",
           "po": "My side: the board is pushing me, and I need dates I can trust, not surprises."}


def explain(content, ai, model, speaker: str, other: str, about: str, facts: dict, history: list[str]) -> dict:
    """The Scrum Master asked for their side: a calm, honest line to the Scrum Master (the AI writes it when it is connected)."""
    if ai is not None:
        try:
            p = content.teammates[speaker]
            system = (f"You are {p['name']}, {p['role']} on a small software team. Voice: {p['voice']} The Scrum Master has stopped the argument between you and {PLAIN[other]} and asked each of you to explain your side. "
                      f"What it is about: {about} Your morale is {facts.get('morale', 50)} and your sanity {facts.get('sanity', 80)} out of 100. Reply to the Scrum Master in ONE or TWO short sentences (at most 28 words): "
                      f"honest about how you feel and what bothers you, calmer than before, in your own voice. No quotes, no stage directions, no swearing. Reply with JSON only: {{\"text\": string, \"tone\": \"calm\"}}.")
            mem = e1.select_segments([{"id": f"h{i}", "text": line, "seq": i} for i, line in enumerate(history)], "BUILD", budget=500)
            from .chat import mask
            r = ai.generate([{"role": "system", "content": system}, {"role": "user", "content": "Recent chat:\n" + ("\n".join(mask(s["text"]) for s in mem) or "(nothing yet)")}], SCHEMA,
                            priority="interactive", max_tokens=120, temperature=0.8, model=model)
            d = json.loads(r.get("content"))
            text = str(d["text"]).strip()
            secrets = [t["secret"] for k, t in content.teammates.items() if k != speaker]
            if text and len(text.split()) <= 40 and not _BAD.search(text) and not any(_leaks(sec, text) for sec in secrets):
                return {"text": text, "tone": "talk", "source": "llm"}
        except Exception:   # noqa: BLE001
            pass
    return {"text": EXPLAIN[speaker], "tone": "talk", "source": "fallback"}


def authored(topic: str, speaker: str, round_: int) -> str:
    pool = ARGUE[topic][speaker]
    return pool[(round_ // 2) % len(pool)]


def prompt(content, speaker: str, other: str, about: str, round_: int, facts: dict, history: list[str], friendly: bool = False) -> list[dict]:
    p = content.teammates[speaker]
    if friendly:
        system = (f"You are {p['name']}, {p['role']} on a small software team. Voice: {p['voice']} You are chatting with your teammate {PLAIN[other]} in a private channel without the Scrum Master. "
                  f"Things are going well. Write ONE short, friendly chat line (at most 16 words) said to {PLAIN[other]} about the current Sprint work, supportive or lightly joking in your own voice, "
                  f"reacting to what was just said. No quotes, no stage directions, no swearing. Do not address the Scrum Master. Reply with JSON only: {{\"text\": string, \"tone\": \"calm\"}}.")
        mem = e1.select_segments([{"id": f"h{i}", "text": line, "seq": i} for i, line in enumerate(history)], "BUILD", budget=500)
        from .chat import mask
        return [{"role": "system", "content": system}, {"role": "user", "content": "Recent chat:\n" + ("\n".join(mask(s["text"]) for s in mem) or "(nothing yet)")}]
    system = (f"You are {p['name']}, {p['role']} on a small software team. Voice: {p['voice']} You are in a real, heated argument with your teammate {PLAIN[other]}. "
              f"What it is about: {about} Round {round_} of the argument (0 = you start it; higher = it has been going on). Your morale is {facts.get('morale', 50)} and your sanity {facts.get('sanity', 80)} out of 100: "
              f"the lower they are, the shorter your temper. Write ONE short chat line (at most 16 words) said to {PLAIN[other]} that reacts directly to what was just said, in your own voice, like a real coworker who is "
              f"frustrated in a fast, heated back-and-forth: blunt, defensive, hurt or sarcastic as your personality would be. No quotes, no stage directions. No swearing, no insults about who they are, no violence. Do not address the Scrum Master. "
              f"Reply with JSON only: {{\"text\": string, \"tone\": \"pushy\" | \"panicked\"}}.")
    mem = e1.select_segments([{"id": f"h{i}", "text": line, "seq": i} for i, line in enumerate(history)], "BUILD", budget=500)
    from .chat import mask
    user = "Recent chat:\n" + ("\n".join(mask(s["text"]) for s in mem) or "(nothing yet)")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


SCHEMA = {"type": "object", "additionalProperties": False, "required": ["text", "tone"], "properties": {"text": {"type": "string"}, "tone": {"enum": ["pushy", "panicked", "calm"]}}}


def line(content, ai, model, speaker: str, other: str, topic: str, about: str, round_: int, facts: dict, history: list[str], friendly: bool = False) -> dict:
    """One heated line from `speaker` to `other`: written by the AI when it is connected and the answer passes the checks, else the authored line."""
    if ai is not None:
        try:
            r = ai.generate(prompt(content, speaker, other, about, round_, facts, history, friendly), SCHEMA, priority="interactive", max_tokens=110, temperature=0.9, model=model)
            d = json.loads(r.get("content"))
            text = str(d["text"]).strip()
            secrets = [t["secret"] for k, t in content.teammates.items() if k != speaker]
            if text and len(text.split()) <= 24 and d.get("tone") in TONES and not _BAD.search(text) and not any(_leaks(sec, text) for sec in secrets):
                return {"text": text, "tone": d["tone"], "source": "llm"}
        except Exception:   # noqa: BLE001  (the authored line keeps the argument going)
            pass
    if friendly:
        pool = BANTER[speaker][other]
        return {"text": pool[round_ % len(pool)], "tone": "calm", "source": "fallback"}
    return {"text": authored(topic, speaker, round_), "tone": "pushy" if speaker != "dev2" else "panicked", "source": "fallback"}
