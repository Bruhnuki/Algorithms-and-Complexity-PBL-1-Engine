# M3: Dialogue gateway

**Goal:** teammate lines from the local model, validated, with authored fallback, such that the model can never affect game state and can be off without breaking anything.

## Prerequisite
M0 result recorded (model, slots, schema-constraint syntax verified against the installed server).

## Tests first (all against the **mock model server** with modes `ok slow dead invalid_json spoiler secret`)

| Test | Req |
| --- | --- |
| `test_TEAM1_model_down_fallback` | TEAM-1 |
| `test_TEAM1_timeout_fallback` (> 10 s → fallback; slot wait > 2 s → fallback) | TEAM-1 |
| `test_TEAM1_schema_invalid_retry_once_then_fallback` | TEAM-1 |
| `test_TEAM1_no_spoiler` | TEAM-1 |
| `test_TEAM1_no_secret_leak` | TEAM-1 |
| `test_TEAM1_max_40_words` | TEAM-1 |
| `test_TEAM1_quota_20_per_minute` | TEAM-1 |
| `test_TEAM1_fallback_pool_ge_3_per_teammate_event` | TEAM-1 |
| `test_TEAM1_fallback_choice_seeded_replayable` | TEAM-1 |
| `test_TEAM1_state_untouched_by_model` (events minus transcript identical with model on/off) | arch 4.4 |
| `test_TEAM1_input_has_no_student_text` | gateway §1 |
| `test_TEAM1_log_fields` (model, prompt tokens, latency, source) | gateway §7 |
| `test_MEM1_e1_segments_within_budget_3000_cap_4000` | MEM-1 |
| `test_MEM1_pinned_persona_and_dod_always_included` | MEM-1 |
| `test_MEM1_contradiction_prompt_uses_stored_answer` | MEM-1 |
| `test_TEAM1_dialogue_off_command_path` (command returns without waiting on model) | arch 5 |
| `test_model_status_endpoint` (queue depth, last latency) | TEAM-1 |

## Build order
1. Mock model server (`tests/mock_model.py`).
2. Gateway: request builder (structured), client, schema re-validation, validators, retry, fallback chooser, quota, semaphore = slots.
3. Persona and fallback content for 3 teammates × 6 event types × ≥ 3 variants.
4. E1 segment selection wired per stage.
5. Transcript persistence + `/model/status`.
6. Live smoke test against real llama-server (manual, recorded in M0 file).

## Gate
All above green with mock; full-sprint bot passes with mock modes `ok` **and** `dead`; real-server smoke shows valid JSON and p50 < 3 s with 5 concurrent callers.

## Out of M3
Fine-tuning, voice, multi-turn standup grilling.
