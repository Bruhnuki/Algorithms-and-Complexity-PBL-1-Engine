# Gameplay Design: Two Hats

Proposed fun layer for the existing sprint loop. Nothing here is in the source spec (`Fix it with Scrum Product and Technical Specification.md`) yet, so every item is tagged **[PROPOSED]**. Change freely, but record what changed.

## 1. Premise (unchanged)

The company goes bankrupt and lays off the Tech Lead and developers. The player is the Scrum Master. Their résumé was exaggerated, so management assumes they can code. They are not promoted and keep the Scrum Master role, but they must also review the team's work. They are doing two jobs, one of them badly.

## 2. Core idea: two hats, one clock [PROPOSED]

Every request has a **Scrum side** (unblock someone, protect the sprint, facilitate) and a **code side** (review the work). Switching between them costs Focus. The player can never fully verify code, so the game is about **reading clues and deciding under uncertainty**, not about coding.

The honest strategy is the real Scrum Master strategy: ask questions, coach the team, and protect the sprint. Bluffing is the tempting shortcut.

## 3. Mechanics

### 3.1 Review as detective work [PROPOSED]
- Each submission has hidden quality (clean, small flaw, buggy, security hole).
- Clues the player can read: test results, the doc versus the diff, how confident the author sounds, and the AI Assistant's opinion (it can be wrong).
- The player approves, rejects, or asks a question.
- After release, public reviews (Play Storey) and the rating change **reveal what the player missed**. This reveal is the main feedback loop and the main teaching moment.

### 3.2 Honesty versus bluffing [PROPOSED]
| Choice | Short term | Long term |
| --- | --- | --- |
| Bluff ("looks good to me") | Rating holds | Cover rises, a caught contradiction costs more |
| Admit ("I don't know, explain it") | small Rating cost | Cover falls, teammate trust and skill rise |

Teaches psychological safety and why bluffing in a standup backfires.

### 3.3 Trust and coaching [PROPOSED]
Each teammate (Marlo the Product Owner, Ines and Tobi the Developers) has **trust** and **skill**.
- **Coach:** slow now, fewer reviews needed later. This is the Scrum Master's real job, and it pays off over sprints.
- **Delegate:** fast now, risky if skill is low.
- Trust changes how honest and how pushy a teammate's messages are.

### 3.4 Learning as power-ups [PROPOSED]
Videos in the learning app unlock "lenses" that reveal more clues. Example: one lens highlights an if/else condition. This works like a Duolingo skill path and extends the existing tutorials.

### 3.5 Chaos events [PROPOSED]
Each event teaches one idea:

| Event | Scrum idea |
| --- | --- |
| Scope creep mid-sprint | Protect the sprint goal, negotiate with the Product Owner |
| Production outage | Prioritise, do not panic-push |
| "Deploy on Friday" request | Saying no, Definition of Done |
| Burned-out developer | Sustainable pace |
| Hacker | Security (extends the existing attack check) |

### 3.6 Retro choice [PROPOSED]
After each sprint the player picks **one improvement** that changes the next sprint (for example more Focus, a clearer Definition of Done, or one extra tutorial unlocked). The retrospective becomes a mechanic instead of a lecture.

## 4. Level shape [PROPOSED]
Seven sprints, like Duolingo units. Each adds one Scrum event and one kind of chaos. Sprints 3 and 7 are boss sprints: a security audit and a demo day.

## 5. Mapping to what already exists
| Existing | Used for |
| --- | --- |
| Pile and its moves (Work, Hold, Delegate, Coach, Defer) | Scrum-side decisions; Coach and Delegate gain real consequences via trust |
| Rating, Cover, Focus, Points, Warnings | Unchanged meters; honesty versus bluffing acts on Cover and Rating |
| Standups with contradiction check | Honest answers, tied to the learning unlocks |
| Scripted attack check | Becomes one chaos event |
| AI Assistant perk | One of the review clues, and it can be wrong |
| Play Storey app | Where the post-release reveal is shown |

## 6. Suggested build order [PROPOSED]
1. **Review reveal** (3.1): the biggest fun gain for the least work. Needs hidden quality already in tickets plus a reveal event after release.
2. **Trust and coaching** (3.3): new state per teammate and new consequences for Coach and Delegate.
3. **Retro choice** (3.6): a small choice screen between sprints.
4. **Chaos events** (3.5) and **lenses** (3.4).
5. **More sprints** (section 4).

## 7. Open questions [OPEN]
- Does trust show as a number, a mood, or both?
- How many clues per submission before it stops being fun and becomes a checklist?
- Does asking a question cost game time, Focus, or both?
- Should the reveal be immediate or delayed until the sprint review?
- Balance numbers are untested. Any value added for these mechanics must go in `content/balance.yaml`, not the front end, and needs a five-person playtest.
