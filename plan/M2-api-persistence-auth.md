# M2: API, persistence, auth

**Goal:** the M1 rules playable over REST by an authenticated user, with an append-only event store and instructor read access.

## Contract first
Write `openapi.yaml` for every route in `docs/trd.md` §3 (including problem-details schema with `code`). Add contract test (generated-vs-committed diff) and schemathesis run. Both red until routes exist.

## Tests first

| Test | Req |
| --- | --- |
| `test_contract_openapi_matches_code` | spec 4.10 |
| `test_AUTH1_password_never_in_db_or_logs` | AUTH-1 |
| `test_AUTH1_argon2id_params` (19 MiB, 2 it, 1 lane) | AUTH-1 |
| `test_AUTH1_generic_error_wrong_pw_vs_unknown_email` (identical body, status, similar timing) | AUTH-1 |
| `test_AUTH2_cross_user_403` | AUTH-2 |
| `test_AUTH2_idle_and_absolute_timeout` | AUTH-2 |
| `test_AUTH2_logout_invalidates_server_side` | AUTH-2 |
| `test_SEC_cookie_flags` (HttpOnly, Secure, SameSite=Lax) | spec 6.7 |
| `test_SEC_csrf_required_on_state_change` | spec 6.7 |
| `test_SEC_bruteforce_lockout` (5/min per account and per address) | spec 6.7 |
| `test_SEC_xss_in_display_name_encoded` | spec 6.7 |
| `test_PILE2_illegal_second_card` (HTTP: `ILLEGAL_COMMAND` problem body, no events written) | PILE-2 |
| `test_SPRINT1_illegal_transition_http` | SPRINT-1 |
| `test_cmd_idempotent_client_seq` (retry returns same result; mismatch → 409) | spec 6.3 |
| `test_state_replay_rebuild_after_restart` | spec 6.6 |
| `test_run_events_append_only` (UPDATE/DELETE rejected) | arch 8 |
| `test_tick_clamped_and_scaled` | TIME-1 |
| `test_END1_debrief_all_four_endings_http` | END-1 |
| `test_ASSESS1_pre_post_submit_and_gain` | ASSESS-1 |
| `test_INSTR1_cohort_isolation` | INSTR-1 |
| `test_INSTR1_transcript_list_and_open` | INSTR-1 |
| `test_perf_api_p95_150ms_no_model` | spec 6.8 |

## Build order
1. `openapi.yaml` + problem-details model.
2. Alembic baseline migration (7 tables + `cohorts` [PROPOSED]).
3. Event store + replay + per-run lock + cache.
4. Auth (register, login, logout, `/me`), sessions (hashed ids), CSRF, rate limit, auth_events.
5. Runs + commands + tick + state + debrief routes (call `rules`).
6. Assessments + instructor routes.
7. `/healthz`, `/model/status` (stub value until M3).
8. `/internal/v1/algorithm/solve` mounted but **excluded from public router**; test that it is not reachable via the public path.

## Gate
OpenAPI contract tests, schemathesis, all AUTH/INSTR/SEC tests green; p95 < 150 ms without model; consent timestamp required before first run [PROPOSED test `test_PRIV_consent_required_before_run`].

## Out of M2
Model calls, UI.
