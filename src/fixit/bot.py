"""Scripted bot: plays a full sprint through the reducer. Used for determinism and balance tests."""
from __future__ import annotations

import hashlib
import json

from .rules import reducer
from .rules.content import Content
from .rules.reducer import GameError

POLICIES = ("solo", "coach_delegate", "reckless")


class Bot:
    def __init__(self, seed: int, content: Content, policy: str = "solo"):
        self.c, self.policy = content, policy
        self.s, ev = reducer.start_run(seed, content)
        self.log: list[dict] = []
        self.events: list[dict] = list(ev)

    def do(self, typ: str, **payload) -> bool:
        cmd = {"type": typ, "payload": payload}
        try:
            self.s, ev = reducer.apply(self.s, cmd, self.c)
        except GameError as e:
            # original-mechanics branch: out of the right action card -> regroup once and retry
            if e.code == "NO_CARD" and typ != "regroup" and self.do("regroup"):
                return self.do(typ, **payload)
            return False
        self.log.append(cmd)
        self.events += ev
        return True

    def ticket_of(self, card):
        return self.c.tickets[card["ticket"]]

    def correct(self, t, wanted="correct"):
        return next(o["id"] for o in t["options"] if o["effect"] == wanted)

    def work(self, card, effect="correct", honest=True):
        t = self.ticket_of(card)
        if not self.do("open_card", card_id=card["id"]):
            return False
        if self.s.get("x"):
            for _ in range(6):   # a person takes real seconds to read the code: about 30 s
                self.do("tick", real_ms=5000)
        if t["kind"] == "fix":
            self.do("flag_line", line_no=t["buggy_line"])
        self.do("select_patch", option_id=self.correct(t, effect))
        if honest:
            self.do("run_script")
            for box in reducer.DOD:
                self.do("toggle_dod", box=box)
        ok = self.do("push")
        if not ok:
            self.do("hold")
        return ok

    def live_tickets(self):
        return [c for c in self.s["pile"] if c["ticket"] and c["state"] in ("pile", "returned")]

    def standup(self):
        self.do("reply_standup", answer="vague")

    def build_day(self):
        for _ in range(60):
            if self.s["status"] != "active":
                return
            if self.s["call"] and self.policy != "reckless":
                self.do("answer_call")
            if self.s.get("x") and self.policy != "reckless":   # live team board: unblock whoever is stuck
                for dev, m in (self.s["x"].get("team") or {}).items():
                    if m["stuck"]:
                        self.do("unblock", dev=dev)
            helps = [c for c in self.s["pile"] if c["type"] == "help_call" and c["state"] == "pile"]
            if self.policy == "coach_delegate" and helps:
                self.do("coach", card_id=helps[0]["id"])
            cards = self.live_tickets()
            if not cards:
                if not self.do("tick", real_ms=5000):
                    return
                continue
            card = cards[0]
            if self.policy == "coach_delegate" and card["state"] == "pile" and not card["id"] in self._delegated() and self.time_to_delegate():
                self.delegated.add(card["id"])
                if self.do("delegate", card_id=card["id"]):
                    continue
            if card["state"] == "returned":
                self.work_returned(card)
            elif self.policy == "reckless":
                t = self.ticket_of(card)
                eff = "security_hole" if any(o["effect"] == "security_hole" for o in t["options"]) else "wrong_hidden"
                if not self.work(card, eff, honest=False):
                    return
            elif not self.work(card):
                if self.s["day"] and not self.do("tick", real_ms=5000):
                    return

    delegated: set

    def time_to_delegate(self) -> bool:
        """Only hand work off if it can come back and be reviewed before the day ends."""
        if not self.s.get("x"):
            return True
        used = (self.s["clock_s"] - self.s["day_start_s"]) / 60
        o = self.c.balance.get("originals", {}).get("change_review", {})
        back = o.get("return_after_min") if o.get("enabled") else self.c.balance["delegation"]["return_after_min"]
        return used + back + 60 <= reducer._day_minutes(self.s, self.c)

    def _delegated(self):
        if not hasattr(self, "delegated"):
            self.delegated = set()
        return self.delegated

    def review_changes(self, card):
        """Original O2: inspect every change, fix the faulty ones, ship."""
        for i in range(len(card["review"]["changes"])):
            cur = next(c for c in self.s["pile"] if c["id"] == card["id"])["review"]
            if sum(ch["shown"] == "faulty" for ch in cur["changes"]) >= cur["faulty_count"]:
                break   # every faulty change is found: stop checking
            trust = self.s["x"]["trust"].get(cur_card(self, card).get("assignee", "dev1"), 0)
            first, second = ("ask", "test") if trust >= 2 else ("test", "ask")   # asking needs no card while trust lasts
            if not self.do("review_inspect", card_id=card["id"], index=i, tool=first):
                self.do("review_inspect", card_id=card["id"], index=i, tool=second)
            cur = next(c for c in self.s["pile"] if c["id"] == card["id"])
            if cur["review"]["changes"][i]["shown"] == "faulty":
                self.do("review_fix", card_id=card["id"], index=i)
        self.do("review_ship", card_id=card["id"])

    def end_day(self):
        if self.s.get("x") and self.s["x"].get("release"):
            self.do("ship_release")

    def work_returned(self, card):
        if card.get("review"):
            return self.review_changes(card)
        t = self.ticket_of(card)
        self.do("open_card", card_id=card["id"])
        self.do("run_script")
        self.do("select_patch", option_id=self.correct(t))
        self.do("run_script")
        for box in reducer.DOD:
            self.do("toggle_dod", box=box)
        if not self.do("push"):
            self.do("hold")

    def play(self) -> "Bot":
        if self.policy == "coach_delegate":
            self.do("watch_tutorial", tutorial_id="conditions")
        if self.s.get("x"):   # experimental branch: several sprints with a shop between them
            for _ in range(self.c.balance["experimental"]["sprints_total"]):
                if self.s["status"] != "active":
                    break
                shop = self.s["x"]["shop"]
                if shop and shop["offers"] and self.policy != "reckless":
                    self.do("buy_practice", practice_id=shop["offers"][0]["id"])
                self.sprint()
            return self
        return self.sprint()

    def sprint(self) -> "Bot":
        self.do("advance_stage", to="STANDUP")
        self.standup()
        self.do("advance_stage", to="BUILD")
        self.build_day()
        if self.s["stage"] == "BUILD" and self.s["open_card"]:
            self.do("hold")
        self.end_day()
        self.do("advance_stage", to="STANDUP")
        self.standup()
        self.do("advance_stage", to="BUILD")
        self.build_day()
        if self.s["open_card"]:
            self.do("hold")
        self.end_day()
        self.do("advance_stage", to="REVIEW")
        return self

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.events, sort_keys=True, default=str).encode()).hexdigest()


def cur_card(bot: Bot, card: dict) -> dict:
    return next(c for c in bot.s["pile"] if c["id"] == card["id"])


def play(seed: int, content: Content, policy: str = "solo") -> Bot:
    return Bot(seed, content, policy).play()
