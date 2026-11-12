"""The team's arguments in Slackish. The AI writes each heated line in the speaker's own voice when it is connected; these authored lines are the fallback
(and keep the demo working without it). What happens in the game (tension, who is fighting, what it costs) is decided by the reducer, never here."""
from __future__ import annotations

import json
import re

from ..engines import e1
from .gateway import MAX_WORDS, TONES, _leaks, _norm

ARGUE = {   # topic -> speaker -> lines (used in order, round by round)
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
_BAD = re.compile(r"\b(fuck\w*|shit\w*|bitch|asshole|bastard|idiot|moron|stupid)\b", re.I)


def authored(topic: str, speaker: str, round_: int) -> str:
    pool = ARGUE[topic][speaker]
    return pool[(round_ // 2) % len(pool)]


def prompt(content, speaker: str, other: str, about: str, round_: int, facts: dict, history: list[str]) -> list[dict]:
    p = content.teammates[speaker]
    system = (f"You are {p['name']}, {p['role']} on a small software team. Voice: {p['voice']} You are in a real, heated argument with your teammate {PLAIN[other]}. "
              f"What it is about: {about} Round {round_} of the argument (0 = you start it; higher = it has been going on). Your morale is {facts.get('morale', 50)} and your sanity {facts.get('sanity', 80)} out of 100: "
              f"the lower they are, the shorter your temper. Write ONE line (at most 30 words) said to {PLAIN[other]}, in your own voice, specific to this disagreement, like a real coworker who is "
              f"frustrated: blunt, defensive, hurt or sarcastic as your personality would be. No swearing, no insults about who they are, no violence. Do not address the Scrum Master. "
              f"Reply with JSON only: {{\"text\": string, \"tone\": \"pushy\" | \"panicked\"}}.")
    mem = e1.select_segments([{"id": f"h{i}", "text": line, "seq": i} for i, line in enumerate(history)], "BUILD", budget=500)
    user = "Recent chat:\n" + ("\n".join(s["text"] for s in mem) or "(nothing yet)")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


SCHEMA = {"type": "object", "additionalProperties": False, "required": ["text", "tone"], "properties": {"text": {"type": "string"}, "tone": {"enum": ["pushy", "panicked"]}}}


def line(content, ai, model, speaker: str, other: str, topic: str, about: str, round_: int, facts: dict, history: list[str]) -> dict:
    """One heated line from `speaker` to `other`: written by the AI when it is connected and the answer passes the checks, else the authored line."""
    if ai is not None:
        try:
            r = ai.generate(prompt(content, speaker, other, about, round_, facts, history), SCHEMA, priority="interactive", max_tokens=110, temperature=0.9, model=model)
            d = json.loads(r.get("content"))
            text = str(d["text"]).strip()
            secrets = [t["secret"] for k, t in content.teammates.items() if k != speaker]
            if text and len(text.split()) <= MAX_WORDS and d.get("tone") in TONES and not _BAD.search(text) and not any(_leaks(sec, text) for sec in secrets):
                return {"text": text, "tone": d["tone"], "source": "llm"}
        except Exception:   # noqa: BLE001  (the authored line keeps the argument going)
            pass
    return {"text": authored(topic, speaker, round_), "tone": "pushy" if speaker != "dev2" else "panicked", "source": "fallback"}
