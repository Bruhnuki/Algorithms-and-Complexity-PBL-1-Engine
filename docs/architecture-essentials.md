# Architecture Essentials

**Read this before writing any code or asking a model to write code.** It exists to stop invented facts. If something is not here or in the spec, it is **unknown**: ask, do not guess.

Tags: **[SPEC]** stated by source spec · **[PROPOSED]** author's design choice · **[OPEN]** unresolved.

## A. The ten decisions [SPEC]

1. **Server owns the rules; browser only draws state.** Scores, timers, escalation, push results computed in Python.
2. **Time is an input.** Game clock moves only on a command or explicit tick. 1 real second = 160 in-game seconds (8 working hours ≈ 3 real minutes). Tick is clamped server-side.
3. **Every run = append-only event log + fixed seed.** State = replay of events.
4. **The LLM never changes game state.** It only writes `{text, tone}` lines.
5. **Content is data.** Tickets, tutorials, teammates, `balance.yaml`, validated by JSON Schema in CI.
6. **ScrumScript runs in our own interpreter.** No eval, no I/O, no imports, hard step limit.
7. **E1 and E2 are pure libraries** behind existing `solve()` contract. Never touch the DB.
8. **One PC runs everything.** FastAPI + llama.cpp `llama-server` (127.0.0.1 only) + SQLite.
9. **Tailscale is the only way in.** Funnel (default) to the FastAPI port only.
10. **Every requirement ID is a test name.** OpenAPI committed; CI fails on drift.

## B. Exact numbers [SPEC]

| Thing | Value |
| --- | --- |
| Sprints | 7 (MVP: 1) |
| Sprint length | 2 in-game days |
| Day | 8 working hours |
| Real→game time | 1 s → 160 in-game s |
| Action costs (min) | read 10, patch 5, test 5, push 2, tutorial 30, answer call 15 |
| Focus < 30 | every action cost +50% |
| Lose | Rating < 2.0 · Cover ≥ 100 (“Cover 100”) · two demotion warnings |
| Demotion warning | Rating < 3.0 at Review |
| Standup answers | accurate −10 Cover, vague +5, wrong +15 |
| Contradiction (MEM-1) | +10 Cover, once |
| 3rd missed call | +3 Cover |
| Push with DoD box unticked | +5 Cover **once per push** (implemented; any number of unticked boxes) and lower process score |
| Repeat reward | ×0.7 per earlier identical good behaviour per sprint (3rd = 0.49) |
| Delegation hidden-bug rate | 45%–55% over 1,000 draws |
| Ticket size | 5–15 lines ScrumScript, 3–4 options, exactly 1 correct |
| Run Script | 5 runs per ticket, normal input only |
| Sprint 1 keywords | `function, return, if, else, =, ==` |
| Hacker events | sprints 4 and 7 (post-MVP) |
| Hacker approve good patch | +200 points, +0.1 rating |
| MVP security consequence | −0.8 rating, −150 points at Review |
| Model dialogue | ≤ 40 words; `{ "text": string, "tone": "calm"\|"pushy"\|"panicked" }` |
| Gateway timing | wait for slot ≤ 2 s; run ≤ 10 s; 1 retry on invalid; then fallback |
| Quota | ≤ 20 model calls/min/student |
| Fallback pool | ≥ 3 variants per teammate per event type |
| E1 token budget | default 3,000; cap 4,000 |
| E1 solve() limits | 2,000 segments, 32,000 tokens |
| Model | primary gpt-oss-20b MXFP4; challenger/8GB fallback Qwen3.5-9B Q4_K_M |
| Serving | ctx 20,480 split over 4 slots (5,120 each); 3 slots if no fit; reasoning effort low |
| VRAM free under load | ≥ 1 GB |
| Players | 10 concurrent; slot utilisation < 75% |
| Latency | API w/o model p95 < 150 ms; reducer < 20 ms; dialogue median 3 s, p95 8 s, hard 10 s |
| Argon2id | 19 MiB, 2 iterations, 1 lane |
| Login limit | 5 attempts/min per account and per address |

### Push result table [SPEC]

| Option effect | Run Script | Result | Points | Rating |
| --- | --- | --- | --- | --- |
| `correct` | passes | Clean | 100 × difficulty | +0.02 |
| `correct_small_flaw` | passes | Acceptable | 50 × difficulty | −0.05 (one bad review) |
| `crashes` | fails with error | Runtime error, **push blocked** | −30 | none |
| `wrong_hidden` | passes listed examples | Functional but buggy | +20 | −0.05 per review over next day; viral −0.3..−0.5 may follow |
| `security_hole` | passes listed examples | Security hole | +20 | none now; stored for attack check |

Exception: ticket flag `run_shows_failure: true` makes Run Script show the wrong result, but push is still allowed and lands as Functional but buggy.

## C. Names that must not drift

- Commands (17): `open_card flag_line select_patch run_script toggle_dod push hold triage_reorder delegate coach defer reply_standup answer_call watch_tutorial buy_perk use_assistant advance_stage`
- Card moves (5): Work, Triage, Delegate, Coach, Defer
- Stages: `PLANNING STANDUP BUILD REVIEW`
- Error codes: `ILLEGAL_COMMAND`, `ILLEGAL_TRANSITION` (others [PROPOSED] in trd.md)
- Option effects (5): `correct correct_small_flaw crashes wrong_hidden security_hole`
- Push results (5): Clean, Acceptable, Runtime error, Functional but buggy, Security hole
- Meters: Points, Rating, Cover, Focus
- Apps: TeamChat, CodeDesk, StarWall, LearnLoop (names may change before final UI; keep in content files)
- Perks: AI Assistant, Keyboard Warrior, Debug Master, Security Scan, Focus Mode
- Roles: `student`, `instructor`
- Tables: users, sessions, runs, run_events, transcript_lines, assessments, auth_events
- MVP tickets: `final_price` (wrong result), `average_rating` (runtime error), `find_user` (security hole), `total_with_tax` (build)
- Packages: engine is `pbl_engine`; existing contract `solve()`; internal route `POST /internal/v1/algorithm/solve`

## D. Forbidden assumptions (do not do these)

1. Do **not** let the LLM, the browser or a prompt decide any score, Cover, Rating, Focus or option correctness.
2. Do **not** pass student free text to the model. Students only pick from choices in the MVP.
3. Do **not** use `eval`, `exec`, `subprocess` or import on ticket/student content. Ticket code is parsed by the interpreter only.
4. Do **not** read the wall clock inside the reducer. Clock and RNG are parameters.
5. Do **not** use one shared RNG. One seeded stream **per purpose** (delegation bugs, assistant errors, ping type).
6. Do **not** store current state as truth. Truth = `run_events`.
7. Do **not** write to the DB from E1/E2 or from the reducer.
8. Do **not** expose the model server beyond 127.0.0.1, or expose `/internal/*` through Funnel.
9. Do **not** add a build step, frontend framework or bundler. Vanilla JS modules.
10. Do **not** hardcode balance numbers in code. They live in `balance.yaml`.
11. Do **not** change the E1/E2 `solve()` request/response schema.
12. Do **not** implement deferred items (HACK-1, typed edits, sprints 2–7, other perks) before the MVP gate.
13. Do **not** invent benchmark numbers. 80–90 tokens/s on the 5060 Ti is an **estimate**; M0 measures it.
14. Do **not** use real brand names in content.
15. Do **not** show model output without validation (length, spoiler, other teammate's secret).
16. Do **not** let a points total feed the process score or final grade.

## E. Known unknowns [OPEN]; ask, do not guess

- Exact balance values beyond the table above (all live in `balance.yaml`; initial values are guesses).
- Starting values of Rating, Cover, Focus, Points. [PROPOSED defaults in architecture.md §4.3]
- Ticket `difficulty` scale and the concrete ticket content/answer keys (needs reviewer).
- Escalation timing per level (message → call → meeting).
- How a sprint after the first re-enters PLANNING under E1's terminal REVIEW.
- Whether "Cover 100" means ≥ 100 (this repo treats lose at Cover ≥ 100).
- E1/E2 internals: the `pbl_engine` repo is **not in this folder**. Read it before writing the adapter; do not assume its API beyond "`solve()` with existing request/response schemas, 19 tests".
- Pilot date; Funnel vs Serve; who reviews answer keys.

## F. Definition of done for any task

1. A test named with the requirement ID exists, failed first, now passes in CI.
2. If an API changed: `openapi.yaml` changed first.
3. If content changed: schema validation passes and golden-output tests pass.
4. If `balance.yaml` changed: scripted bot still can both win and lose.
5. Docs: tag anything new as [PROPOSED] and note it.
