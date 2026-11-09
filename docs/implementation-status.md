# Implementation status

Built from `Spec/`, `docs/`, `plan/`. Tests: `python -m pytest` → 128 passed (+1 timing test: `pytest -m load`).

## Done (MVP code)

| Milestone | What exists | Where |
| --- | --- | --- |
| M1 rules core | ScrumScript interpreter, run reducer (pure), scheduler (cards, escalation, calls, pings, delegation), 4 tickets, 2 tutorials, 3 teammates, 10-question assessment, `balance.yaml`, scripted bot | `src/fixit/rules/`, `content/`, `src/fixit/bot.py` |
| M2 API | Auth (Argon2id, hashed sessions, CSRF, lockout), consent, runs/commands/tick/state/debrief, assessments, instructor cohort + transcript, append-only `run_events` (DB triggers), replay after restart, idempotent `client_seq`, RFC 9457 errors, CSP | `src/fixit/api/app.py`, `src/fixit/store/db.py`, `openapi.yaml` |
| M3 gateway | Structured prompts, JSON-schema output, validation (schema, 40 words, no spoiler, no other teammate's secret), 1 retry, 2 s queue / 10 s run limits, 20/min quota, seeded authored fallback, logging, `/model/status`; off the command path | `src/fixit/gateway/` |
| M4 front end | Vanilla JS, 4 panels (TeamChat, CodeDesk, StarWall, LearnLoop), pile moves, standup, call overlay, debrief, pre/post test, instructor view. Smoke-played in the built-in browser | `src/fixit/web/` |
| M5 (partly) | `tools/load_test.py` (p95 ≈ 100 ms with 10 simulated players), content gate | `tools/` |

## Not done / not verified

- **M0 model feasibility:** needs the 5060 Ti. `tools/m0_bench.py` is written, never run. No number in this repo is a measurement of the real model; the gateway is only tested against a mock server.
- **`pbl_engine` (E1/E2) is not in this repo.** `src/fixit/engines/` are stand-ins with the stated behaviour (stage graph, token budget, process score, bootstrap gain). ASSESS-1's "matches E2's certificate" cannot be tested until the real package is available; the adapter swap point is `engines/e1.py` and `engines/e2.py`. The `POST /internal/v1/algorithm/solve` route is not implemented (its contract is unknown, and exposing it behind Funnel would be unsafe).
- **Tests the plan names but are not built:** Playwright browser E2E (`test_e2e_full_sprint` runs over HTTP, not a browser), schemathesis, ruff, mypy, Locust. Not installed here.
- **Python 3.11**, not 3.12 (what is installed).
- **Contract-first not followed for OpenAPI:** `openapi.yaml` is generated from the code and a test checks it has not drifted.
- **M5 manual items:** Tailscale Funnel/Serve, port scan, privacy checklist, answer-key review by a second person, 5-person playtest. All still open.
- Balance numbers are guesses; the bot wins with `solo`/`coach_delegate` and loses with `reckless`.
- Sprints 2 to 7, HACK-1, other perks, extra tickets: deferred per `docs/mvp-scope.md`.

## Choices the spec left open (now fixed in code)

- A second `open_card` while one is open is rejected; `hold` first.
- DoD: +5 Cover once per push with any box unticked. Ticking "tests" without a green Run Script counts as dishonest in the process log.
- Contradiction (MEM-1): an `accurate` standup answer about a ticket, later shipped as buggy or a security hole, costs +10 Cover once.
- Standup 2 begins day 2 (BUILD to STANDUP is allowed once; review requires day 2). Time past the 8-hour day lapses.
- State is rebuilt by re-applying the stored command log (`cmd` events), not by folding the derived events.
- Pushing a buggy or security-hole result is not revealed to the student until Review (public events hide it).
