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
