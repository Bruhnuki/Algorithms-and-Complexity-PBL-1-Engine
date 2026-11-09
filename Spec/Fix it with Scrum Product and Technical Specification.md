# Fix it with Scrum: Product and Technical Specification

Nov 9, 2026 · @akemi

## 0. Decisions and assumptions

This spec builds the new game design (the pile of demands, ScrumScript tickets, Rating, Cover and Focus) on top of your two engines. Where you gave no preference, the defaults below apply; each can be changed without rewriting the rest.

| Decision | Default taken | Why | Change if |
| --- | --- | --- | --- |
| GPU | RTX 5060 Ti with 16 GB VRAM | The 8 GB card cannot hold the recommended model | You have the 8 GB card: use the fallback model in the TRD |
| Student access | One PC runs everything; students reach it through Tailscale Funnel (public HTTPS, no install) | Least friction for 8 to 10 pilot students | You prefer private access: use Tailscale Serve and invite students to the tailnet |
| Teammate dialogue | LLM-written, with authored fallback lines; the model never changes game state | Keeps scoring deterministic and testable; the game works if the model is down | You want fully authored dialogue |
| Patching | Pick-a-patch only (3 to 4 options); typed edits are post-MVP | Cheap to grade; each wrong option maps to a bug type | You want typed edits as a late perk |
| AI Assistant perk | Wrong about 1 time in 5, seeded and switchable by a config flag | Teaches distrust of tools; flag keeps tests deterministic | You want it always right |
| Balance numbers | All meter values live in one config file (balance.yaml) | The design says they are guesses until playtested | n/a |
| Code execution | ScrumScript runs in a small interpreter written for this project; no AI-written or student-written Python is ever executed | Removes the need for a container sandbox | You add typed edits later: re-evaluate the interpreter limits |
| Engines E1 and E2 | Imported as a Python library behind the existing solve() contract; the HTTP route stays internal | One machine, so a separate service adds latency without isolation benefit | You deploy the engine on another host |
| Spec format | One Doc; acceptance criteria use IDs reused as test names | Easy to review and comment | You want markdown files for the repo |

## 1. PRD (Product Requirements)

**Product.** Fix it with Scrum is a browser game in which the student is a Scrum Master with a faked resume, running a bankrupt company's team of one AI Product Owner and two AI Developers across 7 sprints. The student must keep Rating above 2.0 and Cover below 100 by choosing which demands to work, delegate, coach or drop. Most of the pressure comes from fixing short ScrumScript tickets.

### 1.1 Problem and users

| User | Need | How the game serves it |
| --- | --- | --- |
| Student (algorithms or software-engineering course) | Practice Scrum behaviour (Definition of Done, blockers, coaching, review) and read code for bugs, in a low-stakes setting | A chaotic, timed Pile of demands where honest process beats grinding |
| Instructor | See what students did, not only what they scored | Transcripts and the process score per student |
| Project team (researchers) | Evidence of learning for the pilot of 8 to 10 students | E2 learning gain from a pre/post test plus logged process events |

### 1.2 Goals and non-goals

**Goals**

1. G1: The game feels messy and stressful but fair: every card can be settled in one to three actions.
2. G2: Doing everything yourself pays fastest but lowers the process score, so the Scrum lesson is built into the incentives.
3. G3: The player learns to read short code and to tell five kinds of bug apart, including a security hole that tests do not reveal.
4. G4: The pilot can show a pre/post learning gain through the existing E2 engine.
5. G5: The whole game runs on one local RTX 5060 Ti PC with no paid API.

**Non-goals for v1:** typing free-form code, multiplayer or multi-student teams, mobile layout, real company brands, a general-purpose Scrum platform.

### 1.3 Functional requirements

Every requirement has an ID and a testable acceptance statement. IDs are reused in the test plan (section 7).

| ID | Requirement | Acceptance test |
| --- | --- | --- |
| AUTH-1 | Students and instructors register and log in with email and password; passwords stored with Argon2id | Plaintext password never appears in DB or logs; wrong password returns the same generic error as unknown email |
| AUTH-2 | Server-side sessions with idle and absolute timeouts; roles student and instructor | A student token cannot read another student's run (403) |
| PILE-1 | The Pile shows demand cards, each with sender, deadline timer, payoff and penalty | A new run in sprint 1 shows about 2 live cards, sprint 4 about 5, sprint 7 8 or more |
| PILE-2 | One card is worked at a time; moves are Work, Triage, Delegate, Coach, Defer | Starting a second card while one is open is rejected or switches with the Focus penalty |
| PILE-3 | An ignored card never disappears; it escalates (louder message, then call, then meeting) | After its deadline, a card is still present with escalation level +1 |
| PILE-4 | Delegated cards return later; about half carry a hidden bug that needs re-review | Over 1,000 simulated delegations, the hidden-bug rate is between 45% and 55% |
| CODE-1 | CodeDesk opens a ticket with a short doc, 5 to 15 lines of ScrumScript, hover glossary and concept tag | Every ticket in the content pack validates against the ticket schema |
| CODE-2 | Fix tickets: flag a line, pick one of 3 to 4 replacement lines. Build tickets: fill a blank from a tray | Exactly one option per ticket is right; each wrong option maps to a named bug type |
| CODE-3 | Run Script gives 5 runs per ticket with plain-English pass or fail on the doc's examples; normal input only | A security-hole ticket passes all runs while still containing the hole |
| CODE-4 | Definition of Done checklist (tests pass, matches doc, no security concern); push is allowed with boxes unticked at a Cover cost | Pushing with a box unticked adds +5 Cover and lowers the process score |
| CODE-5 | Every push resolves to exactly one of five results (Clean, Acceptable, Runtime error, Functional but buggy, Security hole) with the stated point and rating effects | Table-driven test over all five results matches the design numbers |
| METER-1 | Points, Rating, Cover and Focus follow the meter rules; repeat rewards shrink 30% per repeat in a sprint | The 3rd identical clean push in a sprint earns 49% of the first |
| METER-2 | Lose conditions: Rating below 2.0, Cover 100, or two demotion warnings | Each condition ends the run with the matching ending |
| TIME-1 | One in-game day is 8 working hours; actions cost in-game time (read 10 min, patch 5, test 5, push 2, tutorial 30) | A day cannot fit more than 8 hours of actions; Focus below 30 raises every cost by 50% |
| SPRINT-1 | A sprint is 2 in-game days run through Planning, Standup, Build, Standup, Review using the E1 stage machine | An illegal stage jump is refused with ILLEGAL\_TRANSITION |
| STAND-1 | Each standup a teammate asks about the player's last push; the player picks accurate, vague or wrong; Cover changes by -10, +5 or +15 | An accurate reply is offered only if the concept is unlocked |
| MEM-1 | Teammates remember earlier answers within the E1 token budget; a later contradiction adds +10 Cover | Replaying a contradicted bluff adds exactly +10 once |
| TEAM-1 | Teammate chat and standup dialogue are generated by the local model in character, with canned fallbacks | With the model stopped, the game stays fully playable using authored lines |
| HACK-1 | Hacker events in sprints 4 and 7 target the oldest shipped security hole, with an attack meter, patch waves, Refresh cost and Approve, Request changes, Fix yourself | Approving a bad patch speeds the meter; approving a good one ends the event with +200 points and +0.1 rating |
| PERK-1 | Toolbox perks bought with Points: AI Assistant, Keyboard Warrior, Debug Master, Security Scan, Focus Mode | Points never feed the process score or final grade |
| TUT-1 | LearnLoop tutorials unlock a concept for the whole run; unknown concepts show ??? | Watching a tutorial costs 30 in-game minutes and removes ??? on tagged lines |
| PROC-1 | The process score is computed by E2 from logged behaviours: holding standups, clearing blockers, honest Definition of Done, reviewing before pushing, coaching | Doing everything yourself yields a lower process score than coaching and delegating with review, given equal Points |
| END-1 | Debrief after sprint 7 or on a loss shows Rating, Cover, process score and the gap between them | Debrief renders for all four endings |
| INSTR-1 | Instructors see their own cohort's transcripts, process scores and pre/post gain | An instructor cannot see another cohort |
| ASSESS-1 | A pre-test and post-test (about 10 questions) feed E2 learning gain with a bootstrap interval | Output matches E2's certificate for a fixed seed |

### 1.4 Success metrics

| Metric | Target |
| --- | --- |
| Campaign length | About 45 minutes for 7 sprints |
| Pilot learning | Median pre/post gain larger than a reading-only control |
| Teammate reply latency on the 5060 Ti | Median under 3 s, 95th percentile under 8 s with 5 students playing at once |
| Fairness | Every card settleable in 3 or fewer actions in a scripted playtest |
| Resilience | Game completes a full run with the model server switched off |

## 2. MVP Scope

The MVP is one complete sprint, playable end to end by a logged-in student, with every consequence loop (points, rating, cover, focus, standup memory) working and testable. It follows the design's MVP line and adds only what the stack requires: login, transcript logging and the model gateway.

| Area | In the MVP | Deferred |
| --- | --- | --- |
| Content | 4 tickets: wrong result (final\_price), runtime error (average\_rating), security hole (find\_user), build ticket (total\_with\_tax) | The remaining tickets, about 28 in the full game |
| Sprint | 1 sprint of 2 in-game days: Planning, Standup, Build, Standup, Review (SPRINT-1) | Sprints 2 to 7, difficulty ramp, language growth |
| Apps | 4 panels on one screen (TeamChat, CodeDesk, StarWall, LearnLoop); no browser-tab chrome | Fake browser with tabs |
| Cards | Build ticket, Fix ticket, Help call, Problem report, Status demand (PILE-1 to PILE-4) | Surprise meetings as a full card type |
| Meters | Points, Rating, Cover, Focus (METER-1, METER-2, TIME-1) | n/a |
| Standups | 2 standups with a scored question and memory contradiction (STAND-1, MEM-1) | Multi-turn standup grilling |
| Perks | AI Assistant only (PERK-1) | Keyboard Warrior, Debug Master, Security Scan, Focus Mode |
| Tutorials | 2 (one code concept, one Scrum idea) (TUT-1) | About 12 total |
| Security consequence | Shipped security hole is resolved at Review by a scripted attack check: -0.8 rating and -150 points | Interactive hacker event with attack meter and patch waves (HACK-1) |
| Dialogue | Local model writes teammate lines; authored fallback if it times out (TEAM-1) | Model fine-tuning, voice |
| Accounts | Register, login, sessions, student and instructor roles (AUTH-1, AUTH-2) | MFA, password reset email |
| Scoring | E1 teammate memory, E2 process score and learning gain, pre/post test of about 10 questions (PROC-1, ASSESS-1) | Instructor dashboards beyond a transcript list |
| Instructor | Read-only list of cohort runs with transcript and process score (INSTR-1) | Exports, charts |

**Out of scope for the MVP:** typed code edits, multiplayer, mobile layout, leaderboards, streaks, authoring tools, any real brand names.

### MVP acceptance gate

The MVP ships only when all four hold:

1. Every requirement ID listed as MVP above has a passing automated test.
2. A scripted bot completes a full sprint on a fixed seed and reaches the same final Rating, Cover and process score on every run.
3. The full sprint also completes with the model server stopped (fallback dialogue only).
4. Five human playtesters finish a sprint in 6 to 10 real minutes, and at least 4 of 5 describe it as stressful but fair.

**Note on the design doc:** it says the MVP is "the three sample tickets plus one clean ticket" but lists four samples, one of them a build ticket. This spec uses all four samples as the MVP set and treats the build ticket as the clean-push path. Tell me if you meant something different.

## 3. User Flow

&#91;embedded content: student session flow · 6 stages, 1 loop, plus the inside of Build\]

A student logs in, consents and takes the pre-test, then plays sprints of Planning, Standup, Build, Standup and Review until the sprints run out or a lose condition fires. Inside Build, the student picks one card from the Pile and chooses one of five moves; working a code card is a six-step sequence ending in a push.

### 3.1 Event flows

| Flow | Steps | Requirement |
| --- | --- | --- |
| Standup question | A teammate asks about the last push; the student picks accurate (only if the concept is unlocked), vague or wrong; Cover changes by -10, +5 or +15; the answer is stored as memory | STAND-1, MEM-1 |
| Ringing call | A call pops over the current card with a timer; answer for 15 in-game minutes and sometimes get a clue, or ignore it; the third missed call adds 3 Cover | PILE-3, METER-1 |
| Ping | A clue, noise or trap arrives in TeamChat; a trap ("just push it") tempts the student to skip the Definition of Done | CODE-4 |
| Delegate | The card leaves the student, returns later, and about half carry a hidden bug that must be reviewed | PILE-4 |
| Coach | A help call is answered by teaching the fix: slower now, fewer calls later, higher process score | PROC-1 |
| Review | Reviews, then posts, then rating resolve in that order; points tally; the Toolbox opens; Rating under 3.0 gives a warning | METER-1, METER-2 |
| Instructor | Log in, open a cohort, see runs with process scores, open a transcript | INSTR-1 |
| Hacker event (post-MVP) | Alert, attack meter, patch waves with Refresh, review each patch, encourage a teammate | HACK-1 |

## 4. Architecture Essentials

Ten decisions carry the whole design. If one of them is wrong, the later sections need rework; everything else is detail.

1. **The server owns the rules; the browser only draws state.** Scores, timers, card escalation and push results are computed in Python. Consequence: a modified browser cannot cheat, and every rule is unit-testable without a UI.
2. **Time is an input, not a side effect.** The game clock moves only when the server receives a command or an explicit tick (the browser sends real elapsed seconds, scaled to in-game time: 8 working hours is about 3 real minutes). Consequence: a test bot can play a sprint in milliseconds with the same result as a human.
3. **Every run is an append-only event log with a fixed random seed.** State is rebuilt by replaying events. Consequence: instructor transcripts, the E2 process score and bug reproduction all come from one source.
4. **The language model never changes game state.** It writes teammate chat and standup lines from a fixed JSON schema. Points, Cover, Rating and every choice are scored by rules and by the engines. Consequence: scoring is deterministic and the game still plays with the model off.
5. **Content is data.** Tickets, tutorials, teammate scripts and every balance number live in versioned files validated by JSON Schema. Consequence: playtest tuning needs no code change, and a bad ticket fails CI.
6. **ScrumScript runs in our own tiny interpreter.** No Python eval, no file or network access, a hard step limit. Consequence: no container sandbox is needed, and security-hole tickets are modelled as data flags the interpreter and Security Scan can read.
7. **Engines E1 and E2 are pure libraries behind their existing solve() contract.** E1 chooses which past chat segments fit each prompt's token budget; E2 computes process score and learning gain. They never touch the database.
8. **One PC runs everything.** FastAPI serves the HTML and the REST API; llama.cpp's server runs the model on the 5060 Ti and listens on localhost only; SQLite holds data. Consequence: the model is reachable only through the backend, which adds auth, quotas and a concurrency limit.
9. **Tailscale is the only way in.** Students reach the app over a Tailscale HTTPS address; nothing else on the PC is exposed. Consequence: no router port-forwarding, and a Tailscale outage is the same as a site outage.
10. **Spec-driven means every requirement ID is a test name.** AUTH-1, CODE-5 and so on appear in test files; the REST contract is an OpenAPI document and CI fails if code and contract disagree.

## 5. Architecture

&#91;embedded content: deployment architecture · one PC, one public edge, one internal model\]

Browsers reach the FastAPI backend only through Tailscale. The backend is the single process that touches the database, the engines and the model server, so authentication, quotas and limits are enforced in one place.

### 5.1 Lifecycle of one command that needs dialogue

1. The browser POSTs a command with a `client_seq` to the backend.
2. The backend checks the session, CSRF header and role, runs the reducer, and appends the new events to `run_events`.
3. If an event needs a teammate line (ping, call, standup), the gateway asks E1 for the memory segments that fit the token budget for the current stage.
4. The gateway sends a chat request to the model server with the JSON-schema constraint and a 10 s limit.
5. The line is validated for length and spoilers; any failure uses an authored fallback line.
6. The line is saved to `transcript_lines` with its source and latency; the browser receives it on its next state poll.

### 5.2 Trust boundaries

| Boundary | What crosses it | Control |
| --- | --- | --- |
| Internet to the PC | HTTPS requests to the app port | Tailscale edge, login, rate limits, CSRF, CSP |
| Backend to model server | Structured dialogue requests | Localhost only, per-user quota, fixed slot count, timeout |
| Backend to engines | Numeric tuples from events | In-process call, solve() input limits (2,000 segments, 32,000 tokens) |
| Backend to database | Parameterised SQL | Only the backend holds the file path |

## 6. TRD (Technical Requirements)

The stack is plain HTML with a Python REST backend, one local model on the 5060 Ti, and Tailscale as the only ingress. Requirement IDs from the PRD are cited so each technical choice traces to a test.

### 6.1 Stack

| Layer | Choice | Notes |
| --- | --- | --- |
| Front end | Static HTML, CSS and vanilla JavaScript modules; no build step | Served by FastAPI; state fetched by polling GET state every second; the page holds no rules |
| Backend | Python 3.12, FastAPI, Uvicorn, Pydantic v2 | OpenAPI 3.1 generated from the code and checked against a committed contract file |
| Database | SQLite in WAL mode through SQLAlchemy 2 and Alembic | Fits one PC and 10 players; the same code can point at PostgreSQL later |
| Passwords | argon2-cffi, Argon2id at OWASP minimum (19 MiB, 2 iterations, 1 lane) | AUTH-1 |
| Engines | The existing pbl\_engine package (E1, E2), imported in-process | Keeps the solve() request and response schemas unchanged |
| Rules engine | New package: ScrumScript interpreter, run reducer, scheduler | Pure Python, no I/O; see 6.4 |
| Model server | llama.cpp llama-server, bound to 127.0.0.1, OpenAI-compatible chat endpoint | Chosen over vLLM because the vLLM build reported for the 5060 Ti is still a nightly |
| Ingress | Tailscale Funnel to the FastAPI port; model server never exposed | Alternative: Tailscale Serve for tailnet-only access |
| Tests | pytest, hypothesis, httpx, jsonschema, Playwright, schemathesis | See section 7 |

### 6.2 Local model selection

**Recommendation: gpt-oss-20b in its native MXFP4 format as the primary model, with Qwen3.5-9B (Q4\_K\_M) as the challenger.** The game needs short in-character lines and valid JSON, not code generation, so the winning trait is speed with room left for several simultaneous players. gpt-oss-20b is the only candidate in the sources that is both fully resident in 16 GB and the fastest, and it has an Apache 2.0 licence and a 128K context. The cost is that it leaves little VRAM spare and may sound flatter in character than Qwen, which is why the challenger stays in the bake-off (section 7, milestone M0).

| Model | Fits 16 GB fully? | Speed seen (RTX 4080, not your card) | Verdict |
| --- | --- | --- | --- |
| [gpt-oss-20b](https://www.glukhov.org/post/2026/01/choosing-best-llm-for-ollama-on-16gb-vram-gpu/) (MXFP4, about 14 GB) | Yes | 140 tokens/s | Primary |
| Qwen3.5-9B (Q4\_K\_M, 6.6 GB) | Yes, with about 9 GB spare for cache | 91 tokens/s | Challenger; also the 8 GB fallback |
| Ministral-3-14B | Yes | 70 tokens/s | Not chosen: slower, no clear gain here |
| Qwen3-14B | Yes | 62 tokens/s | Not chosen: slower |
| Qwen3-Coder-30B | No, 25% runs on CPU | 57 tokens/s | Rejected: spills to CPU and code generation is not needed |
| [Qwen3.6-27B](https://www.morphllm.com/best-ollama-models) (17 GB) | No | not measured | Rejected: larger than 16 GB |
| [Gemma 4 31B-A4B](https://aiweekly.co/alerts/google-gemma-4-31b-confirmed-on-rtx-5060-ti-16gb) | Reported yes, NVFP4 | no figures published | Rejected for the MVP: one unverified post, needs an unstable vLLM nightly |

**Read this table with care.** The speeds come from a single third-party benchmark run on an RTX 4080 (19K-token context, Ollama 0.17.7), which has roughly 1.6 times the memory bandwidth of a 5060 Ti. I expect about 80 to 90 tokens/s for gpt-oss-20b on your card, but that is my estimate, not a measurement. Milestone M0 measures it before anything else is built.

**Serving settings (starting point).**

- All layers on the GPU; total context 20,480 tokens split across 4 parallel slots (5,120 each, enough for the E1 budget plus the reply).
- Reasoning effort set to low so short replies are not preceded by long hidden thinking.
- Output constrained to the dialogue JSON schema (6.5).
- Keep the model GPU for the model only: drive the monitor from the motherboard graphics, or the weights will not leave enough memory for the cache. Aim for at least 1 GB of VRAM free under load.
- If the 4-slot cache does not fit, use 3 slots before shrinking context.

**Capacity estimate.** The simulation report found that the LLM call limit was the first bottleneck. Here the same law applies: utilization = calls per second × seconds per call ÷ slots. With 10 students each triggering one dialogue call about every 30 s (0.33 calls/s), 3 s per call and 4 slots, utilization is about 25%. Even a 3 times higher call rate stays under 75%. This is an estimate to confirm in M0 and again in a 10-user load test.

**If you have the 8 GB card:** gpt-oss-20b will not fit. Use Qwen3.5-9B at Q4\_K\_M with 2 slots and a short context, or a smaller model chosen by the same bake-off. Expect weaker in-character lines, so lean on the authored fallback pool.

### 6.3 REST API (v1)

All bodies are JSON. Errors use RFC 9457 problem details with a stable `code`. State-changing calls need the session cookie plus a CSRF header. Every command carries a `client_seq`, so a retry returns the earlier result instead of applying twice.

| Method and path | Purpose | Requirement |
| --- | --- | --- |
| POST /api/v1/auth/register, /login, /logout | Account and session lifecycle | AUTH-1, AUTH-2 |
| GET /api/v1/me | Current user and role | AUTH-2 |
| POST /api/v1/runs | Start a run; the server picks the seed and content version | PILE-1 |
| GET /api/v1/runs/{id}/state?since=seq | The visible game state plus events after `seq` | PILE-1, METER-1 |
| POST /api/v1/runs/{id}/commands | Apply one player command (list below) | PILE-2, CODE-2 to CODE-5 |
| POST /api/v1/runs/{id}/tick | Report elapsed real milliseconds; the server clamps and scales it | TIME-1 |
| GET /api/v1/runs/{id}/debrief | Final meters, process score and the gap between them | END-1 |
| POST /api/v1/assessments/{pre or post} | Submit about 10 answers | ASSESS-1 |
| GET /api/v1/instructor/cohorts/{id}/runs | Cohort runs with process scores | INSTR-1 |
| GET /api/v1/instructor/runs/{id}/transcript | Event log and dialogue | INSTR-1 |
| GET /healthz and GET /api/v1/model/status | Liveness; model queue depth and last latency | TEAM-1 |
| POST /internal/v1/algorithm/solve | Existing E1 and E2 contract; not routed through Tailscale Funnel | PROC-1, MEM-1 |

**Commands:** open\_card, flag\_line, select\_patch, run\_script, toggle\_dod, push, hold, triage\_reorder, delegate, coach, defer, reply\_standup, answer\_call, watch\_tutorial, buy\_perk, use\_assistant, advance\_stage. Each command has a Pydantic schema and is rejected with `ILLEGAL_COMMAND` when the current state does not allow it (for example, `push` with no open card).

### 6.4 Rules engine

**Run reducer.** `apply(state, command, clock, rng) -> (state, events)` is a pure function. The clock is passed in, and the random generator is seeded per run and per purpose (delegation bugs, assistant errors, ping type), so adding one random draw in a feature does not shift another's results.

**Time.** One real second advances 160 in-game seconds (8 working hours in 3 real minutes). Actions occupy the player for their in-game cost; a call or standup that arrives while busy forces a switch and costs Focus. All costs and rates are read from balance.yaml.

**Stage machine.** The sprint uses E1's allowed transitions: PLANNING to STANDUP to BUILD, BUILD back to STANDUP or on to REVIEW, REVIEW terminal. Any other jump returns `ILLEGAL_TRANSITION`.

**Push result.** Each replacement or tray option in a ticket file carries one `effect` label, so the result is a lookup, never a judgement:

| Option effect | Run Script | Push result | Points | Rating |
| --- | --- | --- | --- | --- |
| correct | Passes | Clean | 100 × difficulty | +0.02 |
| correct\_small\_flaw | Passes | Acceptable | 50 × difficulty | -0.05 (one bad review) |
| crashes | Fails with an error | Runtime error, push blocked | -30 | none |
| wrong\_hidden | Passes the listed examples | Functional but buggy | +20 | -0.05 per review over the next day; a viral post of -0.3 to -0.5 may follow |
| security\_hole | Passes the listed examples | Security hole | +20 | none now; stored for the attack check |

Repeat rewards are scaled by 0.7 for each earlier identical good behaviour in the sprint (a third clean push earns 49% of the first).

**ScrumScript interpreter.** It parses the 5 to 15 line tickets using the sprint's allowed keyword set (sprint 1: function, return, if, else, =, ==), evaluates the doc's examples, and stops at a fixed step limit. It has no imports, no I/O and no way to name Python objects. Property tests check that any generated program ends within the step limit and never raises an unhandled exception.

### 6.5 Dialogue gateway (model access)

Only the backend talks to the model. The gateway is the one place that turns a game event into a prompt and a reply into a validated line.

1. **Input is structured, never student text.** The student only picks from choices, so the model receives the event type (ping clue, ping noise, ping trap, help call, standup question, status demand), the teammate's persona sheet, and E1-selected memory segments built from past events. This removes the prompt-injection path in the MVP.
2. **Context budget.** E1 selects which memory segments fit a token budget (default 3,000, cap 4,000 as in the simulation report) and the current stage controls which segments are eligible. Pinned segments are the persona sheet and the Definition of Done.
3. **Output is a JSON object** `{ "text": string, "tone": "calm" | "pushy" | "panicked" }`, enforced by the server's schema constraint and re-validated in Python. Text is at most 40 words.
4. **Validation before display.** Reject a line that contains the text of the correct patch (no spoilers), names a different teammate's secret, or exceeds the length limit. A rejected line triggers one retry, then the authored fallback.
5. **Timeouts and queueing.** A request waits for a free slot for at most 2 s and runs for at most 10 s. On timeout, the gateway returns a fallback line from the authored pool (at least 3 variants per teammate and event type) and logs `source: fallback`.
6. **Per-user quota.** A student may trigger at most 20 model calls per minute; excess events use fallback lines.
7. **Logging.** Every call logs model name, prompt token count, latency and source (llm or fallback) with the transcript line.

### 6.6 Data model and content files

| Table | Key columns |
| --- | --- |
| users | id, email, display\_name, password\_hash, role, cohort\_id, consent\_at |
| sessions | id\_hash, user\_id, created\_at, last\_seen\_at, expires\_at |
| runs | id, user\_id, seed, content\_version, balance\_version, status, ending |
| run\_events | run\_id, seq, game\_time, type, payload JSON (append-only) |
| transcript\_lines | run\_id, seq, speaker, text, source (llm or fallback), latency\_ms |
| assessments | id, user\_id, kind (pre or post), score, max\_score |
| auth\_events | id, user\_id, kind, ip\_hash, created\_at |

Current game state is never stored as the source of truth: it is the replay of `run_events`, cached per run in memory and rebuilt on restart. The E2 process score is computed from the same events.

**Content files** (JSON or YAML, validated by JSON Schema in CI): `tickets/*.json` (doc, ScrumScript source, options each with an `effect` label and bug type, concept tag, difficulty, `run_shows_failure` flag), `tutorials/*.json`, `teammates/*.json` (persona sheet and fallback lines), `balance.yaml` (all meter numbers, costs, rates, perk prices). A teaching ticket sets `run_shows_failure: true`: Run Script exposes the wrong result, but a push is still allowed and lands as Functional but buggy.

### 6.7 Security requirements

Because Funnel makes the app reachable from the public internet, treat it as a public site.

| Area | Requirement | Verified by |
| --- | --- | --- |
| Login | Generic error for wrong email or password; at most 5 attempts per minute per account and per address; temporary lockout | Automated brute-force test |
| Sessions | Random ids stored hashed; cookie HttpOnly, Secure, SameSite=Lax; idle and absolute timeouts; logout invalidates server-side | Cookie header test |
| Requests | HTTPS only through Tailscale; CSRF header on state changes; parameterised queries; Content Security Policy; output encoding of all dialogue text | Header and XSS tests |
| Authorization | Student reads only own runs; instructor reads only own cohort | AUTH-2 and INSTR-1 tests |
| Model server | Bound to 127.0.0.1; unreachable from the tailnet and the internet | Port scan from another device |
| Tailscale | Funnel exposes only the app port; instructor and admin routes also require a tailnet-only path or an instructor role; ACL tag on the PC | Manual checklist in M5 |
| Privacy | Consent screen before first run; transcripts kept only for the pilot period; compliance check under the Data Privacy Act of 2012 (RA 10173) | Checklist signed before the pilot |
| Secrets | Session key and DB path in an environment file outside the repo | Repo secret scan |

### 6.8 Performance budget

| Item | Target |
| --- | --- |
| API request without model (95th percentile) | Under 150 ms |
| Run reducer per command | Under 20 ms |
| E1 context build | Up to 130 ms (measured in Milestone 1) |
| E2 process score | About 3 ms for 10 students |
| Dialogue line, median and 95th percentile | 3 s and 8 s, hard stop at 10 s |
| Concurrent players supported | 10, with model slot utilization under 75% |
| Free VRAM under load | At least 1 GB |

## 7. Development Plan

&#91;embedded content: development roadmap · 6 milestones, 6 gates, then post-MVP\]

The order puts the riskiest unknown first: M0 proves the 5060 Ti can serve the dialogue within budget before any game code depends on it. Each milestone closes only when its gate passes. Calendar dates are not set because team availability is unknown; give me a pilot date and I will size the milestones against it.

### 7.1 Test-driven workflow

1. Turn each requirement's acceptance statement (section 1.3) into a failing test named with its ID, for example `test_CODE5_push_result_table`.
2. Write the smallest code that passes it, then refactor with the test green.
3. Change contracts first: edit the OpenAPI file or a JSON Schema, watch the contract tests fail, then implement.
4. CI runs on every push: ruff, mypy, content validation, the existing 19 engine tests, unit and property tests, API and contract tests, and a Playwright smoke test.
5. Any change to `balance.yaml` reruns the scripted bot to confirm a sprint can still be both won and lost.
6. A requirement counts as done only when its named test is in CI and green.

### 7.2 Test plan

| Layer | Tool | What it proves | Example |
| --- | --- | --- | --- |
| Rules | pytest, hypothesis | Meters stay in range; repeat rewards shrink by 0.7; lose conditions fire | `test_METER1_repeat_reward`, `test_METER2_lose_rating` |
| Interpreter | pytest, hypothesis | Any generated program ends within the step limit; each ticket option gives its golden output | `test_CODE3_security_ticket_passes_runs` |
| Content | JSON Schema in CI | Every ticket has exactly one correct option and valid effect labels | `test_CODE2_one_correct_option` |
| Engines | Existing pbl\_engine tests | E1 and E2 stay green and match their contract | 19 existing tests |
| API and contract | httpx, schemathesis | Code matches OpenAPI; illegal commands return `ILLEGAL_COMMAND` | `test_PILE2_illegal_second_card` |
| Determinism | pytest | The same seed and commands give an identical event-log hash | `test_bot_replay_hash` |
| Dialogue | Mock model server | Schema valid; zero spoilers; slow or dead model falls back | `test_TEAM1_model_down_fallback` |
| Security | pytest | Brute-force lockout, cookie flags, CSRF, XSS in names, cross-user access denied | `test_AUTH2_cross_user_403` |
| End to end | Playwright | A full sprint plays in the browser, with and without the model | `test_e2e_full_sprint` |
| Load | Locust or a script | 10 virtual players keep latency and slot use inside the budget | `test_load_10_players` |
| Playtest | 5 people | Length 6 to 10 minutes; stressful but fair | Questionnaire |

### 7.3 Risks

| Risk | Mitigation |
| --- | --- |
| gpt-oss-20b sounds flat in character | Bake-off in M0 against Qwen3.5-9B; authored fallback pool; persona sheets with example lines |
| 14 GB of weights leaves too little VRAM for 4 slots | Run the display off the motherboard graphics; drop to 3 slots; shorten context |
| Funnel makes the home PC publicly reachable | Minimal app surface, rate limits, model on localhost only; switch to Tailscale Serve and invite students if needed |
| Balance numbers are guesses | All in `balance.yaml`; scripted bot checks winnability; playtest tuning |
| The design is large (7 sprints, about 28 tickets) | MVP gate in section 2; everything else is deferred |
| The PC sleeps or reboots during a pilot session | Disable sleep, auto-start services, run a health check before each session |
| A teaching ticket has a wrong answer key | Golden-output tests plus a second person reviewing each ticket |
| Four app names clash with real products | Check before the final interface; names stay in content files |

## Open questions

- [ ] Pilot date or course deadline, so milestones can be sized against it
- [ ] Confirm the 5060 Ti is the 16 GB card (the 8 GB card changes the model)
- [ ] Confirm students may use a public Funnel address, or whether the pilot must stay on a private tailnet
- [ ] Confirm the MVP ticket set: all four samples, or three plus a separate clean ticket
- [ ] Should the AI Assistant be wrong about 1 time in 5 in the MVP, as assumed here
- [ ] Who reviews each ticket's answer key before it ships

## Sources

Pages opened on 2026-11-09. Speed figures are from a third-party run on an RTX 4080, not a 5060 Ti.

- [Comparing LLMs performance on Ollama on 16GB VRAM GPU](https://www.glukhov.org/post/2026/01/choosing-best-llm-for-ollama-on-16gb-vram-gpu/) (tokens per second and VRAM fit for 14 models; table updated 2026-03-09)
- [Best Ollama Models (2026)](https://www.morphllm.com/best-ollama-models) (model sizes, context, licence; last verified 2026-10-16)
- [Google Gemma 4 31B Confirmed on RTX 5060 Ti 16GB](https://aiweekly.co/alerts/google-gemma-4-31b-confirmed-on-rtx-5060-ti-16gb) (single unverified community report, mid-May 2026)
- Your project files: the Fix it with Scrum proposal, the Casinto simulation report, the Group 4 Milestone 1 proposal, the pbl\_engine repository, and the game design note dated 2026-11-09
