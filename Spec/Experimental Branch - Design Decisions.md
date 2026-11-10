# Experimental Branch: Design Decisions

Branch `experimental/engagement-mechanics`. The main game on `main` is untouched. Everything here builds on `Spec/Engagement Research.md` and is **[EXPERIMENTAL]** until playtested.

## How to run it

The branch lives in its own folder (a git worktree), so the main game keeps working from the main folder at the same time.

```bash
cd ".claude/worktrees/engagement"
```

```bash
PORT=8001 DB_PATH=fixit_exp.db python run_dev.py
```

Open `http://localhost:8001/play/`. The main game still runs on port 8000 from the main folder.

**Switch:** `content/balance.yaml` → `experimental.enabled`. `false` gives the original MVP game exactly; the MVP test suite (M1 to M5) runs with it off and still passes, so the original rules are proven unchanged.

---

## Answers to the open questions

### Q1. Run length: 20 to 30 minutes

**Decision:** a run is **3 sprints** of 2 in-game days each. The third sprint is a boss sprint.

How the time adds up (estimate, not measured with a human player yet):
- A sprint deals 2 to 4 code tickets plus help calls and status demands, increasing per sprint (`sprint_deal` in `balance.yaml`).
- With the hybrid clock (Q4), real time is spent reading and deciding, about 1 to 1.5 minutes per code ticket, plus standups, the shop and the review.
- Estimated 6 to 9 real minutes per sprint, so 20 to 27 minutes per run.

To change the length: `experimental.sprints_total` and `experimental.sprint_deal.code_cards`.

### Q2. Focus: per day or per action?

| Option | How it plays | For | Against |
| --- | --- | --- | --- |
| **Per action / turn** (Slay the Spire energy) | A fixed Focus budget each turn; actions cost Focus; refills every turn. | Very legible; every turn is a clean puzzle. | Needs turns, which the spec's clock does not have (see Q4). Refilling every turn removes long-term pressure: there is never a reason to save. It also turns Focus into a second clock next to game minutes, so the player tracks two costs for one action. |
| **Per day** (daily budget) | Focus refills at each standup; actions that strain you spend it; low Focus makes everything slower. | Fits the sprint's natural rhythm (a day is a round). Creates a planning layer: spend Focus early or keep a reserve for the afternoon. Keeps a single cost (minutes) per action, with Focus as the multiplier on that cost. Works with any clock. | Less instant feedback than per-turn energy. |
| **Never refills** (current MVP: +10 per standup) | Focus only drains. | Simple. | Once low, a run snowballs into slower and slower actions with no way back; it punishes early mistakes for the rest of the run. |

**Recommendation and what is built: per-day budget.**
- Focus refills by **35** at each standup (`focus.day_refill`), more with the Sustainable Pace practice.
- **Switching between cards costs 6 Focus** (`focus.switch_cost`). This is the decision Focus now drives: finish what you started, or jump to the fire that just started.
- Below 30 Focus every action costs 50% more time (the existing TIME-1 rule).

Why this is the most engaging choice: it keeps one cost per action (minutes), adds one real trade-off (context switching), and gives the day a shape (fresh in the morning, careful by evening) without adding turns.

### Q3. Practices: 10 distinct ones, plus 2 combos

Each practice changes a different rule, so no two are "the same thing, slightly stronger". Practices never change the push points table or the process score.

| Practice | Rule it changes | Axis |
| --- | --- | --- |
| Definition of Done | First Run Script on each ticket costs no time (2 at level 2) | Tool cost |
| Pair Programming | Delegated tickets come back bugged half as often (a quarter at level 2) | Delegation risk |
| Timeboxing | New cards arrive with 60 more minutes before escalating (120 at level 2) | Deadlines |
| WIP Limit | Opening a card is 50% faster while 3 or fewer cards are live (75% at level 2) | Flow / pile size |
| Swarming | Coaching blocks one extra incoming call (2 at level 2) | Interruptions |
| Retrospective | Active: once per sprint, reset one card's escalation (twice at level 2) | Active ability |
| Psychological Safety | The accurate standup answer is available without the tutorial | Honesty |
| Sustainable Pace | +20 Focus each morning; low-Focus penalty starts at 20 instead of 30 | Energy |
| Backlog Refinement | Deferring a card no longer escalates it | Prioritisation |
| Spike | Tutorials take half the time | Learning |
| **TDD Pair** (combo: DoD + Pair Programming) | Run Script always free; you can see whether returned work is bugged | Combo |
| **Steady Flow** (combo: Timeboxing + Backlog Refinement) | No card escalates past a message | Combo |

- **Evolution:** a practice used 4 times levels up (`practices.evolve_at`).
- **Slots:** 5 (combos do not use a slot).
- **Pool:** 7 practices from the start; Definition of Done and Spike join when you watch the matching tutorial; Retrospective and Psychological Safety are unlocked by achievements in earlier runs.

### Q4. Clock: real-time, turn-based or hybrid?

| Option | For | Against |
| --- | --- | --- |
| **Real-time** (current MVP) | Constant urgency; calls and escalations feel alive. | Punishes reading speed, and reading code is learning goal G3. Slower readers lose to the clock, not to bad decisions. Stressful in a way that is not fair. |
| **Turn-based** | Fair to every reader; every decision is deliberate; easiest to balance. | Removes urgency entirely: calls, escalations and deadlines lose their bite. Feels like a board game, the opposite of "stressful but fair". Breaks the spec's real-time model. |
| **Hybrid** | Keeps urgency where it is a decision (which card next, answer the call or not) and removes it where it is a skill test (reading code). | One more rule to explain. A player can open a card to "freeze" the world, but every open costs reading time and Focus, so this has a price. |

**Recommendation and what is built: hybrid.**
- The clock **runs in real time while you stand at the Pile** choosing what to do next. Calls ring, deadlines approach, the director adds work.
- The clock **pauses while a card is open** (reading and fixing code) and **while a standup question is waiting** (`experimental.clock`).
- Actions still cost game minutes as before, so time keeps moving with every action, even while paused in real time.
- A chip in the HUD says "Clock running" or "Clock paused" so the rule is always visible.

Why: the tension sits on the choice, not on reading speed. That is the version of "stressful but fair" that teaches the right thing.

### Q5. What lives in `content/balance.yaml`

Every new number is in the `experimental:` block. Nothing is hardcoded in the front end; it reads costs, prices, timers and odds from the server state. Starting values and what to tune first:

| Section | Key values (starting guess) | Tune first if... |
| --- | --- | --- |
| `sprints_total`, `boss_sprint` | 3, 3 | runs are too long or short |
| `clock` | pause while card open: yes; while standup: yes | players freeze the world to think |
| `focus` | refill 35/day, switch cost 6, start 100 | Focus never matters, or always runs out |
| `sprint_deal` | code cards 2/3/4, help calls 1/1/2, status 1/1/1, calls 3/3/4, pings 4/4/5, deadlines 240 to 420 min, max difficulty 1/2/2 | sprints feel empty or overwhelming |
| `bosses` | Auditor +20 Cover on attack; Scope Creep every 90 min; Friday Deploy day 2 = 360 min; Demo Day 20 s standup, vague ×2 | a boss is trivial or impossible |
| `practices` | 5 slots, price 80 to 120, evolve at 4 uses, per-practice effect values | one practice is always picked |
| `shop` | 3 offers, rerolls 20/40/80/160, interest 10% capped at 25, free pick at start | players never buy, or hoard |
| `style` | ranks D 0, C 3, B 5, A 7, S 9 | everyone is D or everyone is S |
| `suspicion` | spot checks from 70 Cover every 120 min; last stand at 90; clutch −25 Cover | last stand never or always happens |
| `director` | every 60 min; adds work if ≤1 live card and Cover <50; relief +30 min once if ≥4 live | quiet stretches or pile-ups |
| `comeback` | behind if Rating <3.0 or a warning; bounty +150; +30 Focus | losing runs stay hopeless |
| `momentum` | gains: coach 20, review 15, honest DoD 15, accurate standup 20, blocker 5; full 100; protect 120 min | ultimates never or always ready |
| `heat` | +20% run score per modifier; 5 modifiers | experts stop replaying |
| `sprint_goal` | ship 1 / 2 / 3 tickets per sprint; miss: 1 warning and +10 Cover; hit: +50 points | goals feel trivial or unfair |
| `meta_unlocks` | win → Retrospective + Heat; a sprint with no bluff → Psychological Safety | unlocks come too fast or slow |
| `story` | authored debrief lines | n/a |

---

## What is built (Engagement Research section 6)

| ID | Mechanic | Where |
| --- | --- | --- |
| M1 | Visible move costs and "N other cards will escalate meanwhile" on every card | Pile (`priceTag`), `x.move_costs` |
| M2 | Known bug odds on delegated work; only reading the code tells you for sure | Pile (`odds`), `x.bug_odds` |
| M3 | 10 practices, 2 combos, evolutions, 5 slots | `practices` rules, shop |
| M4 | Points and process score side by side in the HUD; repeat-reward preview on push | HUD, push panel |
| M5 | Seeded sprints: tickets, calls and pings drawn from the seed, no ticket repeats in a run | `_x_deal_sprint` |
| M6 | 4 bosses that change a rule, announced from sprint 1 | `bosses` |
| M7 | Ending the sprint while delegated work is out ships it unreviewed | `_x_auto_ship` |
| M8 | "Coming up" list of the next 2 hours; ping kind (clue, noise, trap) stays hidden | `x.intents` |
| M9 | Each standup answer and unticked push shows its price | standup, push panel |
| M10 | Style rank per sprint, display only, rewards variety | HUD, debrief |
| M11 | Spot checks above 70 Cover, last stand at 90, clutch save | `suspicion` |
| M12 | Free starting pick; shop between sprints with lock, rising reroll price and interest | shop |
| M13 | Director: adds work when quiet, grants relief when swamped | `director` |
| M14 | Comeback: bounty ticket and extra Focus when behind | `comeback` |
| M15 | Class challenge code: same code, same sprints; instructor list shows the code | run setup, instructor table |
| M16 | Achievements unlock practices and Heat for later runs | `meta_unlocks`, `/api/v1/me/unlocks` |
| M17 | 5 Heat modifiers after a first win; run score bonus | run setup, debrief |
| M18 | Debrief story lines from teammates about how the run went | `story` |
| M19 | Work-in-flight lanes above the Pile | `lanesEl` |
| M20 | Demo Day timed standup (choices only, never typed text) | standup timer |
| Goal | Sprint goal: ship N fixed or reviewed tickets, or take a warning | HUD, planning, `sprint_goal` |
| M21 | Momentum meter and 3 ultimates (Protect the Sprint, Swarm, Retro Now) | HUD |

Six new tickets (`shipping_fee`, `points_balance`, `find_order`, `loyalty_discount`, `split_bill`, `stock_status`) give the seeded sprints 10 tickets to draw from. Each was checked against the interpreter.

## Tests

- `tests/test_x_mechanics.py`: 33 tests, one or more per mechanic and sprint goal, plus determinism (same seed and commands give the same event log), the scripted bot winning and losing a 3-sprint run, and the API (challenge code, server-only configure, replay after restart).
- The original M1 to M5 suites run with `experimental.enabled: false`.

## Known gaps and findings

- **Not playtested by people.** Every number is a guess. The 20 to 30 minute estimate is not measured.
- **Fixed: doing nothing used to win.** Each sprint now has a **sprint goal**: ship 1, 2, then 3 tickets that you fixed yourself or reviewed (clean or acceptable). Work that ships unreviewed at the end of a sprint does not count. Missing the goal gives a demotion warning and +10 Cover; meeting it pays +50 points. Two warnings end the run, so an idle player now loses by the end of sprint 2 (checked in the browser and in `test_GOAL_doing_nothing_loses` over 6 seeds). The goal shows in the HUD, at planning, next to the End sprint button when you are short, and on the debrief.
- **Story lines are authored**, not written by the model. The model could voice them later; it must never change state.
- **Instructors still cannot link students** to a cohort since the sign-up cohort code was removed, so the challenge-code comparison only works if students share their codes.
- Mobile layout was checked at 375 px for the build screen only.
