# Development Plan

Source: spec section 7. Order puts the riskiest unknown first: **M0 proves the 5060 Ti can serve dialogue within budget before game code depends on it.** Each milestone closes only when its gate passes. No calendar dates: team availability and pilot date are unknown [OPEN].

M0 and its purpose, M1's E1 timing measurement and M5's Tailscale checklist are [SPEC]; the content of M1 to M5 is a [PROPOSED] decomposition.

| # | Milestone | Outcome | Gate (all must pass) |
| --- | --- | --- | --- |
| [M0](M0-model-feasibility.md) | Model feasibility | Measured tokens/s, latency, VRAM at 4 slots; model chosen | Dialogue p50 < 3 s, p95 < 8 s, VRAM free ≥ 1 GB, JSON valid |
| [M1](M1-rules-core.md) | Rules core | Interpreter, reducer, scheduler, content pack, E1/E2 adapter; headless bot plays a sprint | Rules/interpreter/content tests green; bot replay hash stable; E1 context ≤ 130 ms |
| [M2](M2-api-persistence-auth.md) | API, persistence, auth | Event store, REST, auth, roles, instructor read | OpenAPI contract tests green; AUTH/INSTR tests green |
| [M3](M3-dialogue-gateway.md) | Dialogue gateway | Model client, validation, fallback, quota, logging | All TEAM-1/MEM-1 tests green with mock model; sprint plays with model off |
| [M4](M4-frontend-e2e.md) | Front end + MVP bot | 4-panel UI, full sprint in browser | Playwright full sprint with and without model; bot reaches identical final meters |
| [M5](M5-hardening-pilot.md) | Hardening + pilot readiness | Security, Tailscale, load, playtest | MVP acceptance gate (docs/mvp-scope.md) all 4 hold; privacy checklist signed |
| Post-MVP | Sprints 2–7, HACK-1, other perks, ~24 more tickets, dashboards | | Separate plan |

Traceability: [traceability.md](traceability.md).

## Test-driven workflow [SPEC 7.1]

1. Acceptance statement → failing test named with its ID, e.g. `test_CODE5_push_result_table`.
2. Smallest code to pass, refactor green.
3. Contract first: edit OpenAPI/JSON Schema, watch contract tests fail, implement.
4. CI on every push: ruff, mypy, content validation, existing 19 engine tests, unit + property, API + contract, Playwright smoke.
5. `balance.yaml` change → rerun scripted bot: a sprint must still be **both won and lost**.
6. A requirement is done only when its named test is in CI and green.

## Rules for every milestone [PROPOSED]

- Start by writing that milestone's failing tests (list in each file). Commit them red first.
- Do not start milestone N+1 code until N's gate passes, except M0 tasks that only read.
- Any new unknown goes in `docs/architecture-essentials.md` §E as **[OPEN]**.

## CI skeleton (set up at start of M1) [PROPOSED]

```
ruff check . && ruff format --check .
mypy src/rules src/gateway
python -m tools.validate_content        # JSON Schema + golden outputs
pytest pbl_engine/tests                 # existing 19
pytest tests/unit tests/property tests/api tests/contract
schemathesis run openapi.yaml ...       # M2+
playwright test                         # M4+
```
