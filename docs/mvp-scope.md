# MVP Scope

Source: spec section 2.

**The MVP is one complete sprint**, playable end to end by a logged-in student, with every consequence loop (Points, Rating, Cover, Focus, standup memory) working and testable. It adds only what the stack requires: login, transcript logging, model gateway.

## In / deferred

| Area | In the MVP | Deferred |
| --- | --- | --- |
| Content | 4 tickets: wrong result (`final_price`), runtime error (`average_rating`), security hole (`find_user`), build ticket (`total_with_tax`) | Remaining ≈ 28 tickets |
| Sprint | 1 sprint, 2 in-game days: Planning, Standup, Build, Standup, Review (SPRINT-1) | Sprints 2–7, difficulty ramp, language growth |
| Apps | 4 panels on one screen: TeamChat, CodeDesk, StarWall, LearnLoop; no browser-tab chrome | Fake browser with tabs |
| Cards | Build ticket, Fix ticket, Help call, Problem report, Status demand (PILE-1..4) | Surprise meetings as full card type |
| Meters | Points, Rating, Cover, Focus (METER-1, METER-2, TIME-1) | n/a |
| Standups | 2 standups with scored question + memory contradiction (STAND-1, MEM-1) | Multi-turn grilling |
| Perks | AI Assistant only (PERK-1) | Keyboard Warrior, Debug Master, Security Scan, Focus Mode |
| Tutorials | 2 (one code concept, one Scrum idea) (TUT-1) | ≈ 12 total |
| Security consequence | Shipped security hole resolved at Review by **scripted attack check**: −0.8 rating, −150 points | Interactive hacker event (HACK-1) |
| Dialogue | Local model writes lines; authored fallback on timeout (TEAM-1) | Fine-tuning, voice |
| Accounts | Register, login, sessions, roles (AUTH-1, AUTH-2) | MFA, password-reset email |
| Scoring | E1 memory, E2 process score + learning gain, ≈ 10-question pre/post (PROC-1, ASSESS-1) | Dashboards beyond transcript list |
| Instructor | Read-only cohort run list with transcript and process score (INSTR-1) | Exports, charts |

**Out of scope for MVP:** typed code edits, multiplayer, mobile layout, leaderboards, streaks, authoring tools, real brand names.

## MVP requirement set

In: AUTH-1, AUTH-2, PILE-1 (sprint 1 density), PILE-2, PILE-3, PILE-4, CODE-1..5, METER-1, METER-2, TIME-1, SPRINT-1, STAND-1, MEM-1, TEAM-1, PERK-1 (AI Assistant), TUT-1 (2 tutorials), PROC-1, END-1, INSTR-1 (list + transcript), ASSESS-1.
Out: HACK-1.

## MVP acceptance gate

Ships only when all four hold:

1. Every MVP requirement ID has a passing automated test.
2. A scripted bot completes a full sprint on a fixed seed and reaches the **same final Rating, Cover and process score on every run**.
3. The sprint completes with the model server stopped (fallback dialogue only).
4. Five human playtesters finish a sprint in **6 to 10 real minutes**, and ≥ 4 of 5 call it "stressful but fair".

## Ambiguity to resolve [OPEN]

The design note says the MVP is "three sample tickets plus one clean ticket" but lists four samples, one a build ticket. This scope uses **all four samples** and treats the build ticket as the clean-push path. Confirm with the author.

## Cut rule

Anything not in the left column above is not built until the gate passes. If a task needs a deferred item, stop and ask.
