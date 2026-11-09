# TRD: Technical Requirements

Source: spec section 6 and 7. Tags: **[SPEC]** default, **[PROPOSED]** added here.

## 1. Stack [SPEC]

| Layer | Choice | Notes |
| --- | --- | --- |
| Front end | Static HTML, CSS, vanilla JS modules; no build step | Served by FastAPI; polls `GET state` every 1 s; no rules in page |
| Backend | Python 3.12, FastAPI, Uvicorn, Pydantic v2 | OpenAPI 3.1 generated, diffed against committed `openapi.yaml` |
| Database | SQLite (WAL) via SQLAlchemy 2 + Alembic | Same code can point at PostgreSQL later |
| Passwords | argon2-cffi, Argon2id, 19 MiB, 2 iterations, 1 lane | AUTH-1 |
| Engines | existing `pbl_engine` (E1, E2) in-process | `solve()` schemas unchanged |
| Rules engine | New package: ScrumScript interpreter, run reducer, scheduler | Pure Python, no I/O |
| Model server | llama.cpp `llama-server`, 127.0.0.1, OpenAI-compatible chat | Not vLLM (nightly build for 5060 Ti) |
| Ingress | Tailscale Funnel to FastAPI port | Alt: Serve (tailnet only) |
| Tests | pytest, hypothesis, httpx, jsonschema, Playwright, schemathesis | Section 9 |
| Lint/type [PROPOSED] | ruff, mypy (strict on `rules/`) | In CI per spec 7.1 |

## 2. Local model [SPEC]

**Primary: gpt-oss-20b, native MXFP4 (≈ 14 GB).** Challenger and 8 GB fallback: Qwen3.5-9B Q4_K_M (6.6 GB). Rejected: Ministral-3-14B, Qwen3-14B (slower), Qwen3-Coder-30B (spills to CPU), Qwen3.6-27B (> 16 GB), Gemma 4 31B-A4B (unverified, needs unstable vLLM).

Benchmarks in the spec are from an **RTX 4080** (≈ 1.6× 5060 Ti bandwidth), not the target card. Expected 80–90 tok/s is an estimate. **M0 measures it.**

Serving settings (starting point):
- All layers on GPU; total ctx 20,480 across 4 slots (5,120 each). 3 slots if cache does not fit, before shrinking context.
- Reasoning effort **low**.
- Output constrained to dialogue JSON schema.
- Drive monitor from motherboard graphics; ≥ 1 GB VRAM free under load.
- 8 GB card: Qwen3.5-9B Q4_K_M, 2 slots, short context; lean on fallback pool.

[PROPOSED] llama-server invocation sketch (verify flags against installed build in M0):
`llama-server -m <model.gguf> --host 127.0.0.1 --port 8080 -ngl 99 -c 20480 -np 4`
Schema constraint via the chat request's `response_format` JSON schema (or `json_schema` field, per build).

Capacity: utilisation = λ × t ÷ slots. 0.33/s × 3 s ÷ 4 ≈ 25%.

## 3. REST API v1 [SPEC]

All bodies JSON. Errors RFC 9457 problem details with stable `code`. State-changing calls need session cookie **plus CSRF header**. Every command has `client_seq`; retry returns earlier result.

| Method + path | Purpose | Req |
| --- | --- | --- |
| POST /api/v1/auth/register, /login, /logout | Account + session lifecycle | AUTH-1, AUTH-2 |
| GET /api/v1/me | User + role | AUTH-2 |
| POST /api/v1/runs | Start run; server picks seed + content version | PILE-1 |
| GET /api/v1/runs/{id}/state?since=seq | Visible state + events after seq | PILE-1, METER-1 |
| POST /api/v1/runs/{id}/commands | Apply one player command | PILE-2, CODE-2..5 |
| POST /api/v1/runs/{id}/tick | Report elapsed real ms; server clamps and scales | TIME-1 |
| GET /api/v1/runs/{id}/debrief | Final meters, process score, the gap | END-1 |
| POST /api/v1/assessments/{pre\|post} | Submit ≈ 10 answers | ASSESS-1 |
| GET /api/v1/instructor/cohorts/{id}/runs | Cohort runs + process scores | INSTR-1 |
| GET /api/v1/instructor/runs/{id}/transcript | Event log + dialogue | INSTR-1 |
| GET /healthz, GET /api/v1/model/status | Liveness; model queue depth, last latency | TEAM-1 |
| POST /internal/v1/algorithm/solve | Existing E1/E2 contract; **not** via Funnel | PROC-1, MEM-1 |

### Commands [SPEC names; payloads PROPOSED]

| Command | Payload | Legal when |
| --- | --- | --- |
| open_card | card_id | stage BUILD; no card open (or switch rule) |
| flag_line | line_no | card is Fix ticket, open |
| select_patch | option_id | line flagged (Fix) / blank (Build) |
| run_script | , | patch selected; runs_used < 5 |
| toggle_dod | box: tests\|matches_doc\|no_security | work open |
| push | , | card open with patch selected |
| hold | , | card open (park, keep state) |
| triage_reorder | ordered card_ids | stage BUILD |
| delegate | card_id | card open or in pile |
| coach | card_id | card is help call |
| defer | card_id | any live card |
| reply_standup | answer: accurate\|vague\|wrong | standup pending |
| answer_call | , | call ringing |
| watch_tutorial | tutorial_id | enough day time |
| buy_perk | perk_id | Review/Toolbox open; points ≥ price |
| use_assistant | , | perk owned |
| advance_stage | , | legal per E1 graph |

Request envelope [PROPOSED]: `{ "client_seq": int, "type": "<command>", "payload": {...} }`.

### Error codes
[SPEC]: `ILLEGAL_COMMAND`, `ILLEGAL_TRANSITION`. [PROPOSED]: `UNAUTHENTICATED` (401), `FORBIDDEN` (403), `NOT_FOUND` (404), `VALIDATION_ERROR` (422), `RATE_LIMITED` (429), `LOCKED_OUT` (429), `DUPLICATE_SEQ_MISMATCH` (409, same seq different body), `DAY_FULL`, `MODEL_UNAVAILABLE` (never surfaced to player; internal).

Cross-user access returns 403 per AUTH-2 test.

## 4. Rules engine [SPEC]

- `apply(state, command, clock, rng) -> (state, events)`; pure.
- 1 real s = 160 in-game s. Costs/rates from `balance.yaml`. A call/standup arriving while busy forces a switch and costs Focus.
- Stage machine from E1: PLANNING→STANDUP→BUILD; BUILD→STANDUP|REVIEW; REVIEW terminal; else `ILLEGAL_TRANSITION`.
- Push result table: see [architecture-essentials §B](architecture-essentials.md).
- Repeat rewards ×0.7 per earlier identical good behaviour in sprint.
- Interpreter: sprint-1 keywords `function return if else = ==`; fixed step limit; no imports/I/O/host objects; property tests.

## 5. Dialogue gateway [SPEC]

1. **Input structured, never student text.** Event type (ping clue/noise/trap, help call, standup question, status demand), persona sheet, E1 segments.
2. **Context budget.** E1 selects segments in budget (default 3,000; cap 4,000); stage controls eligibility; pinned: persona sheet + Definition of Done.
3. **Output** `{"text": string, "tone": "calm"|"pushy"|"panicked"}`; server schema constraint + Python re-validation; ≤ 40 words.
4. **Validation.** Reject: contains correct-patch text; names another teammate's secret; too long. One retry, then authored fallback.
5. **Timeouts/queue.** ≤ 2 s slot wait, ≤ 10 s run. Timeout → fallback (≥ 3 variants per teammate per event type), `source: fallback`.
6. **Quota.** ≤ 20 calls/min/student; excess → fallback.
7. **Logging.** model name, prompt tokens, latency, source with transcript line.

Dialogue prompt contract: see [agent-spec.md Part B](agent-spec.md).

## 6. Data and content [SPEC]

Tables: see [architecture.md §8](architecture.md). Source of truth for state: `run_events` replay.

Content files (JSON/YAML + JSON Schema in CI):

| File | Contents |
| --- | --- |
| `tickets/*.json` | doc, ScrumScript source, options each with `effect` + bug type, concept tag, difficulty, `run_shows_failure` |
| `tutorials/*.json` | concept, text, cost (30 min), unlocks |
| `teammates/*.json` | persona sheet, fallback lines per event type |
| `balance.yaml` | all meter numbers, costs, rates, perk prices, step limit |

Ticket schema [PROPOSED fields]:

```json
{
  "id": "final_price", "kind": "fix|build", "difficulty": 1,
  "concept": "if_else", "title": "...", "doc": "...",
  "examples": [{"input": [..], "expected": ..}],   // 5 runs
  "source": ["line1", "..."],                      // 5-15 lines
  "buggy_line": 3,                                 // fix tickets
  "blank": null,                                   // build tickets
  "options": [{"id":"a","text":"...","effect":"correct","bug_type":null}],
  "run_shows_failure": false,
  "glossary": {"==": "..."}
}
```
Rules: 5–15 source lines; 3–4 options; exactly one `correct`; every non-correct option names a `bug_type`; `effect` in the five labels.

## 7. Security [SPEC]

Funnel makes the app a public site.

| Area | Requirement | Verified by |
| --- | --- | --- |
| Login | Generic error; ≤ 5 attempts/min per account and per address; temp lockout | Brute-force test |
| Sessions | Random ids stored hashed; cookie HttpOnly, Secure, SameSite=Lax; idle + absolute timeouts; logout invalidates server-side | Cookie header test |
| Requests | HTTPS only; CSRF header on state changes; parameterised queries; CSP; output-encode all dialogue | Header + XSS tests |
| Authorization | Student reads own runs; instructor own cohort | AUTH-2, INSTR-1 tests |
| Model server | 127.0.0.1; unreachable from tailnet/internet | Port scan from other device |
| Tailscale | Funnel exposes only app port; instructor/admin routes need tailnet-only path or instructor role; ACL tag on PC | M5 manual checklist |
| Privacy | Consent before first run; transcripts kept only for pilot; Data Privacy Act 2012 (RA 10173) check | Signed checklist before pilot |
| Secrets | Session key + DB path in env file outside repo | Repo secret scan |

[PROPOSED] extras: `auth_events` logs login success/fail by `ip_hash`; password min length 10; idle timeout 30 min, absolute 8 h; CSP `default-src 'self'`; dialogue rendered with `textContent` only.

## 8. Performance budget [SPEC]

| Item | Target |
| --- | --- |
| API w/o model p95 | < 150 ms |
| Reducer per command | < 20 ms |
| E1 context build | ≤ 130 ms (measured M1) |
| E2 process score | ≈ 3 ms for 10 students |
| Dialogue median / p95 / hard | 3 s / 8 s / 10 s |
| Concurrent players | 10, slot util < 75% |
| Free VRAM under load | ≥ 1 GB |

## 9. Test strategy [SPEC]

Workflow, layers and examples as in spec 7.1–7.2.

| Layer | Tool | Proves | Example |
| --- | --- | --- | --- |
| Rules | pytest, hypothesis | Meters in range; ×0.7; lose conditions | `test_METER1_repeat_reward`, `test_METER2_lose_rating` |
| Interpreter | pytest, hypothesis | Terminates in step limit; golden outputs | `test_CODE3_security_ticket_passes_runs` |
| Content | JSON Schema in CI | One correct option, valid effects | `test_CODE2_one_correct_option` |
| Engines | existing tests | E1/E2 green, contract | 19 existing |
| API/contract | httpx, schemathesis | Code matches OpenAPI; illegal → `ILLEGAL_COMMAND` | `test_PILE2_illegal_second_card` |
| Determinism | pytest | Same seed+commands → identical event-log hash | `test_bot_replay_hash` |
| Dialogue | mock model server | Schema valid; no spoilers; dead model → fallback | `test_TEAM1_model_down_fallback` |
| Security | pytest | Lockout, cookies, CSRF, XSS, cross-user denied | `test_AUTH2_cross_user_403` |
| E2E | Playwright | Full sprint, with and without model | `test_e2e_full_sprint` |
| Load | Locust or script | 10 players inside budget | `test_load_10_players` |
| Playtest | 5 people | 6–10 min; stressful but fair | Questionnaire |

CI per push: ruff, mypy, content validation, 19 engine tests, unit + property, API + contract, Playwright smoke. `balance.yaml` change reruns scripted bot (must still win **and** lose).

Naming: `AUTH-1` → `test_AUTH1_<what>`. One requirement may have several tests; each starts with its ID.

## 10. Non-functional / ops [PROPOSED]

- Config via env file outside repo: `SESSION_SECRET`, `DB_PATH`, `MODEL_URL`, `MODEL_NAME`, `ASSISTANT_FLAKY` (bool), `MODEL_SLOTS`.
- Disable PC sleep; auto-start services; pre-session health check script.
- Migrations via Alembic only.
