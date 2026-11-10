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

## Round 2: real gameplay and a compact screen

Feedback: half the screen was interface, and the game was still "click a button, wait, click another button".

### The new core loop: run a live team

During work time, GitHab shows a **team board**: your to-do list on the left and three lanes on the right, **You**, **Ines** and **Tobi**.

- **Drag a request onto a person** (or press "Give to Ines" or "Give to Tobi"). Drop it on **You** to fix it yourself in the code.
- **Teammates work in real time.** Their progress bar fills as the clock runs. Ines is fast and careful (30% mistakes); Tobi is slow and makes more mistakes (60%). Each can hold one task, so who gets what is a real decision.
- **They get stuck.** A stuck teammate stops working until you press **Unblock** (8 min of your time). Left stuck for 45 min, the request gets louder. This is the Scrum Master's real job: clearing blockers.
- **Their work comes back to check.** You know how many of the 5 changes have a mistake, not which. Find them, fix them, send it to users, or rush it out unchecked.
- **Combo.** Finishing requests on time, one after another, builds a combo that pays a growing bonus (+25% per step, up to +150%). Anything getting louder, or anything broken reaching users, breaks it.
- **Surprises.** A **production outage** (the app is broken for everyone: fix it within 70 minutes for +150 points and +0.1 rating, or lose 0.3 rating) and **urgent requests** from Marlo (less time, bonus if on time) arrive at random times. They are never shown in "Coming up".
- **Enough to do.** Three requests wait at the start of each sprint (one for each of you), and more arrive through the day, so the player is rarely waiting.

All numbers are in `content/balance.yaml` under `originals.team_board`, `originals.combo` and `originals.events`. Asking the team is now available from sprint 1 (`onboarding.unlock_sprint.delegate: 1`), because the team board is the core of the game.

### Compact screen

On a 1366 × 768 screen the game area now starts about 210 px from the top (about 70% of the height was gameplay, up from about half):

- Top bar: smaller title, smaller Log out button.
- Address bar: shorter URL, compact meters, the Stage meter removed (the roadmap shows it).
- Guide: one line for the next step and one short line for why; the step pills are gone (the roadmap shows them).
- Status chips: one slim row.
- The "GitHab · Your to-do list and the code" title bar and the "pull a tab down" tip are gone. Tabs can still be pulled out into sticky notes.

### Checked

- Scripted browser runs that only followed the glowing guide: gave work to Ines and Tobi, fixed one request themselves while the team worked, checked returned work (found and fixed a hidden mistake), and shipped. Waiting dropped to a few seconds.
- Bots over 40 seeds: the coaching-and-delegating bot wins 35, the do-it-all-yourself bot 31.
- 182 tests pass, including `test_TEAM_*`, `test_COMBO_*` and `test_EVENTS_*`.

### Not checked

- No real player has tried this version. Whether it *feels* exciting needs a playtest.
- Drag and drop was tested through its button equivalent in scripts, not with a mouse drag.
- Sprint 3 and the boss were not played in the browser.

## Round 3: stable screen, fixed tabs, calmer top strip

Feedback: clicking anything made all the icons and numbers refresh; switching tabs reloaded content and the tabs changed size; the top strip looked cramped.

### Why it kept refreshing

Measured in the browser with a mutation counter:

1. The address bar (with all the number tiles and their icons), the guide and the "pop out" bar were rebuilt on **every tab switch**, because their change check included which app was open.
2. The GitHab page was rebuilt **every game minute while idle** (4 rebuilds in 6 seconds), because countdowns such as "Due in 4 h 52 min", "in 20 min" and a stuck teammate's minutes were part of its data.
3. The guide's glow was removed and re-added on every update, which restarted its animation.
4. The unread badge sat inside each tab and made it wider, so tabs changed size whenever a badge appeared or vanished (Slackish went from 117 px to 145 px).

### What changed

- **Built once, patched in place:** the address bar, the six number tiles with their icons, the guide and the tab strip are created once. Updates only change their text, bar width or colour. A number change still tweens and shows its +/− chip, but nothing is re-created.
- **Countdowns are live text:** "Due in ...", "in N min" and "N min so far" update in place and no longer count as page data.
- **Smaller regions:** the action-card hand is its own region, separate from the status chips, and the chips ignore Points and practice use counts.
- **The glow stays put:** it moves only when the target changes, and revealing it scrolls only the page, never the whole browser frame.
- **Tabs have one fixed size:** equal width (96 to 156 px), 40 px tall, the badge floats over the corner. On phones they become 44 px icon tabs. A tab drag needs a deliberate 14 px pull, so a wobbly click is just a click. "Pop out" moved into the tab row.
- **Calmer top strip:** one tab row, one row for the address and numbers (fixed-size tiles, tabular digits), the guide with a clear "Next" label and a muted "why" line, and one row of chips with no orphaned items. Below 1240 px the numbers get tighter; below 900 px they wrap.

### Measured after

| Check | Before | After |
| --- | --- | --- |
| Elements rebuilt while idle for 8 s | 4 page rebuilds | 0 |
| 11 tab switches: meters, icons, guide, heron, tabs, address bar | rebuilt each time | the same DOM elements |
| Tab widths over all switches | 117 to 145 px | 156 px every time (150 px at 1100 px wide) |
| "Give to Ines" click | whole interface | only the GitHab page content |

182 tests pass.

### Not checked

- Moving focus: after a click inside the page, keyboard focus is lost when that page rebuilds. The page is rebuilt only when its own data changes, but a finer per-card update would fix it fully.
- Drag-and-drop with a real mouse and the sticky-note drag were not exercised beyond pop-out and put-back.
