# Scrum Learning Mode

The shipped game (`balance.calm.enabled: true`) teaches Scrum first. Set it to `false` for the arcade version the older tests cover.

## What changed from the arcade game
- **No timers.** No real-time clock, no due dates, no escalation ("getting louder"), calls never expire, no speed-fix bar, combos, outages, bug waves, spot checks, bosses, director, action cards, release train, leaderboard or speed/energy skills.
- **Stable Sprint Backlog.** Every item of the sprint is on the list from Planning. One teammate asks for help mid-sprint (an impediment).
- **Safe first sprint.** No strikes and no game over in Sprint 1.
- **Five Scrum events per sprint** as real screens: Sprint Planning, Daily Scrum, Work, Sprint Review, Retrospective (new `RETRO` stage).
- **Guided scenes** (`content/scrum_guide.json`): one question per moment. A wrong answer explains why and lets you retry; first-try results are shown in the debrief.
- **Consequences that teach:** coaching a help call permanently lowers that developer's mistake chance; each send with an unticked Done box adds hidden "debt" to everyone's mistake chance until honest sends pay it back; the Retrospective grants one free practice, with evidence from the sprint highlighted.

## First project: "The Checkout Fix"
Sprint 1 goal: *Customers see the correct price at checkout* (coupon, tax, shipping). Sprint 2: loyalty rewards. Sprint 3: customer data stays private (security in the Definition of Done).

| Sprint | Scrum ideas covered |
| --- | --- |
| 1 | Product Backlog (Product Owner owns the order), Sprint Goal, Developers forecast the Sprint Backlog, Daily Scrum purpose, impediments, Increment and Definition of Done, inspect and adapt, Retrospective |
| 2 | Backlog refinement, outcome-based goal, protecting the Sprint from mid-sprint scope, Not Done means not Done |
| 3 | Quality in the Definition of Done, courage and transparency under pressure, the three pillars |

All numbers are in `content/balance.yaml` under `calm:`. Beats, answers and feedback are data in `scrum_guide.json`; the server checks answers and never sends the answer key to the browser.

## Assessment
`content/assessment.json` (v2): 7 scenario questions on Scrum roles and events, 3 on code and security.

## Tester feedback round (Game Tester Remarks.docx)
- **Less on screen.** Learning mode hides the To do / With you / With the team / Back to check / Done counters, the Sprint Goal chip, Teamwork score, Suspicion and strikes. Only the App rating, Points and Energy stay. ToobYou and Amazin' appear from Sprint 2. Suspicion and strikes no longer exist in this mode; only the app rating can end a run.
- **Flow first.** The welcome flow now shows the five Scrum moments before the game. Sprint 1 has a mandatory 8-step tutorial that cannot be skipped. Each step gives a Scrum definition, its purpose, how it works in the game, and exactly what to do; the rest of the screen is locked until the step is read and done. The "new idea" popups are off in learning mode.
- **Clearer order.** The Sprint Backlog is empty during Planning and the Retrospective and fills when the Sprint begins. Day 1 cannot be ended before you start on an item. Finishing a sprint asks for confirmation and lists what is done and not done.
- **No completion codes.** The game is self-study, not a class session, so there are no codes to hand in. "Finish the Sprint" still asks for confirmation.
- **Rating matches reviews.** Play Storey always shows ten reviews whose average is the app rating (one decimal, the same number as the top bar).
- **Graphic, not text.** The Retrospective shows each developer's chance of a mistake as a bar, with chips for coaching and skipped checks.
- **No purple confusion.** Evidence hints in the Retrospective are blue; the Help request tag is yellow.
- A vague or untrue Daily Scrum answer now adds the same hidden "debt" as a skipped Done box.

## Later changes
- **Tutorial:** 8 mandatory steps (Sprint Planning, Daily Scrum, Transparency, Sprint Backlog, Definition of Done, Timeboxing, Sprint Review, Retrospective), each with Definition / Purpose / In this game / Your turn.
- **Fonts:** in the game, regular text is DM Sans 400 (self-hosted in `web/fonts`, loaded by `game-font.css`); bold text and the landing page keep the original font.
- **Challenge codes and the leaderboard are removed** (API field, route, screens and tests). Runs always get a random seed.

## Onboarding rework
- **Order:** intro (what the program is, the team, a Sprint flowchart) → consent → "What is the main Sprint?" flowchart (shown once) → New run → tutorial (first time only) → real Sprint 1 with its scenes.
- **Tutorial = a practice Sprint.** It is its own throwaway run (`tutorial: true` on `POST /runs`, hidden from the instructor list) with no Scrum scenes, so nothing can interrupt it. 13 steps, each: Herb talks in short bubbles ("Next", then "Got it"), then you do the real action on the one highlighted control. A single dimmer with a spotlight cut-out covers everything else and blocks clicks; page scroll is locked; the box always stays inside the window and narrows before it would cover the control; text is 18px or larger.
- **First run cannot be skipped.** Returning players can use "Replay the tutorial" on the New run screen, which adds a "Skip tutorial" button.
- **The 10-question quiz is gone** (client, API routes, table model, content file, instructor "gain" column).

## Tester round 2 (Game Tester Remarks-2)
- **Trust = success rate.** Each teammate has one number (percent, starts at 80). It is the chance work you give them succeeds. Giving a teammate work is instant: it either finishes the item (counts toward the Grade and Sprint Goal) or sends it straight back to you. Every offload costs that teammate 2 points. Coaching a help request +5, a fully honest send +2 for both, a send with an unticked Done box -4 for both. In the practice Sprint the roll is forced to 100%.
- **Daily Scrum answers** show their numbers: honest +3 rating, +3 trust; vague 0 rating, -5 trust, small hidden problem; lie +10 rating, -15 trust, big hidden problem. Rating points are on a 0-100 scale (1 point = 0.05 stars). Trust changes go to the teammate who asks. A hidden problem costs rating at the Sprint Review (vague -3, lie -12), so the lie only wins in the short term. Your reply appears in #team-chat.
- **Grade replaces Points** (0-100%: Done work as a share of everything the project can earn). **Energy is gone** from learning mode, and so is anything for sale (Amazin' tab, AI Assistant, the Sustainable Pace practice).
- **Live feed.** Nothing is in GitHab before Work. The first item arrives when Work starts and then one new item every 60 real seconds (all at once on day 2 and in the practice Sprint). This is the one real-time element; items have no deadline or penalty.
- **Practice Sprint uses its own problems** (`practice_*` tickets, never dealt in real Sprints), so nothing stale carries into Sprint 1. It validates the clicked line and the chosen fix against the item, and Herb coaches wrong answers.
- **Hints:** only the big stage buttons (Begin the Sprint, Start the work day, End the day, ...) ever glow. The drag-and-drop hint animation is removed.
