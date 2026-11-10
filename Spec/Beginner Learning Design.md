# Beginner Learning Design

Branch `experimental/original-mechanics`. Goal: someone who has never programmed, used GitHub or heard of Scrum can start playing, always knows what to do next and why, and learns how a software team works by doing it.

## The problem

Playtesting feedback, even from an IT student: too many technical terms, too many mechanics at once, no clear next step. The game made sense to its developers, not to its players.

## What changed

### 1. One idea at a time (`content/balance.yaml` → `onboarding`)

Mechanics switch on sprint by sprint. Players are never shown a mechanic before it is taught.

| Sprint | What the player learns | What is switched on |
| --- | --- | --- |
| 1 | The basics: to-do list, standup, reading code, testing, the Done checklist, sending a fix to users, calls, helping a teammate | Fix it myself, test, checklist, send, standup, calls, help, later |
| 2 | Teamwork: asking the team, checking their work, good team habits | Ask the team, change-by-change review, practices (one free), coming up, work lanes, style rank, the director |
| 3 | Advanced systems and a boss | Action cards, releases, teamwork multiplier, momentum and special moves |

Each sprint's unlock is set in `onboarding.unlock_sprint`. `onboarding.enabled: false` turns everything on from the first minute (used by the mechanic tests). The planning screen says what the next sprint will teach.

### 2. A guide that always says the next step, and why

The bar under the address bar now shows **Next step**, one action in plain words, and **Why** it matters in a real team. The button for that step glows. If the step is in another app, the guide says "Open Slackish, then: …" and the tab glows. The guide follows the game state (`guide()` in `app.js`), from starting the sprint to clicking the wrong line, testing, ticking the checklist and sending the fix.

If a player clicks a line that is not the bug, the game now says "line 3 is not the broken one. Read the description again and click the line that doesn't match it", and the guide changes to "That line looks fine: click a different one". Before, it said "flag the line that is wrong first".

### 3. Plain language everywhere, and tap-to-explain words

| Before | Now |
| --- | --- |
| Pile, Issues | To-do list |
| Cover | Suspicion |
| Focus | Energy |
| Warnings | Strikes (shown only once you have one) |
| Process score | Teamwork score |
| Push (send it live) | Send to users |
| Run Script | Test my fix |
| Definition of Done, "Matches the doc" | Done checklist, "It does what the description says" |
| Work, Delegate, Coach, Defer, Hold | Fix it myself, Ask the team, Help them, Later, Put it down |
| Accurate, Vague, Wrong | Explain honestly, Keep it vague, Make something up |
| `fix from Ines (Dev) · pile · due 379.6 min · escalation: message` | `Bug from Ines (Developer) · Due in 6 h 19 min · reward +100 points · ignore it and Suspicion +3` |
| "escalated" | "Getting louder: they called you" |

Underlined words (meters, card types, Done checklist, Sprint goal and so on) open a one-line explanation when tapped or focused with the keyboard. All words live in `src/fixit/web/guide.js` → `TERMS`.

### 4. Learn by doing: "New idea" cards

A short card appears the **first time** a concept matters, never before and never twice: the to-do list, the first standup, the first bug, reading code, the first test, the Done checklist, the first fix reaching users, the first call, help requests, escalation, rising Suspicion, the sprint review, then each sprint-2 and sprint-3 mechanic as it unlocks. The game clock pauses while a card is open. Cards live in `guide.js` → `CONCEPTS`; which ones a player has seen is remembered in the browser per player.

### 5. Shorter welcome, scoring moved into the game

The welcome is now: hello, the story, the team, how a round works, pick a project. The scoring tables were removed from the start (they listed 8 rules with numbers before the player had seen anything). They now live in ToobYou → **How scoring works**, next to the **Word book**, a list of every word in the game in everyday language. A test still checks the scoring numbers against `balance.yaml` (`test_guide_scoring_copy_matches_balance`).

## Checked

- A scripted browser run that only clicked the glowing element went from the first screen through sprint 1 into sprint 2. Every step had a guide and a glowing target, including recovering from wrong lines.
- 375 px phone width: no sideways scrolling, word explanations stay on screen.
- 179 tests pass, including `test_ONBOARD_*` for the sprint-by-sprint unlocks.

## Not done or not checked

- Not tested with real beginners. The wording is a first draft; `guide.js` is the one file to edit.
- Sprint 3 (action cards, releases, the boss) was not played through in the browser.
- The main game (`main`) and the first experimental branch do not have these changes.
- The landing page still uses some of the old words.
