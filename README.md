# Fix it with Scrum

A browser game. The student is a Scrum Master with a faked resume, running a bankrupt company's team (one AI Product Owner, two AI Developers) across 7 sprints. Keep **Rating above 2.0** and **Cover below 100** by choosing which demands to work, delegate, coach or defer. Most pressure comes from fixing short **ScrumScript** tickets.

Runs on one PC (RTX 5060 Ti 16 GB), no paid API. Students connect over Tailscale.

## Source of truth

`Spec/Fix it with Scrum Product and Technical Specification.md` is the single source. Everything in `docs/` and `plan/` is derived from it.

Tagging convention used in all derived docs:

| Tag | Meaning |
| --- | --- |
| **[SPEC]** | Stated in the source spec. Do not change without changing the spec. |
| **[PROPOSED]** | Needed to build, not stated in the spec. A design choice by the doc author; change freely, but record it. |
| **[OPEN]** | Unresolved question. Do not code around it silently. |

## Documents

| Doc | Read it for |
| --- | --- |
| [docs/prd.md](docs/prd.md) | Problem, users, goals, requirement IDs with acceptance tests, metrics |
| [docs/mvp-scope.md](docs/mvp-scope.md) | What ships first, what is deferred, the 4-point acceptance gate |
| [docs/userflow.md](docs/userflow.md) | Student, instructor and event flows (diagrams) |
| [docs/architecture-essentials.md](docs/architecture-essentials.md) | **Read first.** Hard facts, exact numbers, forbidden assumptions. Anti-hallucination sheet |
| [docs/architecture.md](docs/architecture.md) | Full architecture: components, state, events, data, sequences, failure modes |
| [docs/trd.md](docs/trd.md) | Stack, model, REST API, rules engine, gateway, security, performance |
| [docs/agent-spec.md](docs/agent-spec.md) | Rules for coding agents building this repo, and spec of the in-game AI teammates |
| [plan/README.md](plan/README.md) | Milestones M0 to M5, gates, test-first workflow |
| [plan/traceability.md](plan/traceability.md) | Requirement ID → test name → milestone |

## How development works (spec-driven, test-driven)

1. A requirement ID in the PRD has an acceptance statement.
2. That statement becomes a **failing test named with the ID** (`test_CODE5_push_result_table`).
3. Contract first: edit OpenAPI or a JSON Schema, watch contract tests fail, then implement.
4. Smallest code to green, then refactor.
5. A requirement is **done only when its named test is in CI and green**.

If code and spec disagree, the spec wins. If the spec is silent or wrong, change the spec first, then the test, then the code.

## Planned repo layout [PROPOSED]

```
Spec/                    source spec (read-only input)
docs/                    derived docs (this set)
plan/                    milestones + traceability
content/                 tickets/*.json tutorials/*.json teammates/*.json balance.yaml + schemas/
src/
  rules/                 ScrumScript interpreter, run reducer, scheduler (pure, no I/O)
  api/                   FastAPI app, auth, routes, OpenAPI
  gateway/               dialogue gateway (model client, validation, fallback)
  store/                 SQLAlchemy models, Alembic migrations, event store
  web/                   static HTML/CSS/JS modules (no build step)
pbl_engine/              existing E1/E2 package (imported, unchanged)
tests/                   pytest, hypothesis, contract, e2e (Playwright), load
openapi.yaml             committed contract
```

## Run it

```bash
pip install -r requirements.txt
python -m pytest                     # 128 tests (rules, API, gateway, web safety)
python tools/validate_content.py     # content schema + golden outputs
python tools/dump_openapi.py         # regenerate openapi.yaml after an API change
python tools/load_test.py            # 10-player load check (mock model)
python run_dev.py                    # http://127.0.0.1:8000 = landing page, /play/ = the game (no model: authored fallback dialogue)
```

Environment (outside the repo): `SESSION_SECRET`, `DB_PATH`, `INSTRUCTOR_CODE`, `MODEL_URL` (llama-server, 127.0.0.1), `MODEL_NAME`, `MODEL_SLOTS`. What is built and what is not: [docs/implementation-status.md](docs/implementation-status.md).

## Open questions (from the spec)

- [ ] Pilot date or course deadline
- [ ] Confirm the GPU is the 16 GB 5060 Ti
- [ ] Public Tailscale Funnel allowed, or private tailnet only
- [ ] MVP ticket set: all four samples, or three plus a separate clean ticket
- [ ] AI Assistant wrong 1 in 5 in the MVP
- [ ] Who reviews each ticket's answer key
