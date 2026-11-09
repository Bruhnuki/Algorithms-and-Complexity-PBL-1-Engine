# M1: Rules core

**Goal:** a pure-Python game that a headless bot can play for one sprint, deterministically. No web, no DB, no model.

## Scope
`src/rules/` (interpreter, reducer, scheduler), `content/` (4 tickets, 2 tutorials, 3 teammates, `balance.yaml`, schemas), E1/E2 adapter, scripted bot.

## Prerequisite
Read the `pbl_engine` repo; record the real `solve()` request/response shape and E1 stage machine API in `docs/architecture-essentials.md` §E. Run its 19 tests.

## Tests first (write red, in this order)

| Order | Test | Req |
| --- | --- | --- |
| 1 | `test_CODE1_all_tickets_validate_schema` | CODE-1 |
| 2 | `test_CODE2_one_correct_option` + `test_CODE2_wrong_options_have_bug_type` | CODE-2 |
| 3 | `test_INTERP_golden_outputs_all_options` (every option of every ticket) | CODE-2/3 |
| 4 | `test_INTERP_terminates_property` (hypothesis, any program ≤ step limit, never raises) | CODE-3 |
| 5 | `test_CODE3_security_ticket_passes_runs` | CODE-3 |
| 6 | `test_CODE3_five_runs_plain_english` | CODE-3 |
| 7 | `test_CODE4_unticked_box_adds_5_cover` | CODE-4 |
| 8 | `test_CODE5_push_result_table` (all 5 effects, numbers from spec) | CODE-5 |
| 9 | `test_CODE5_runtime_error_blocks_push` | CODE-5 |
| 10 | `test_CODE5_run_shows_failure_still_pushable` | CODE-5 |
| 11 | `test_METER1_repeat_reward` (3rd clean = 49%) | METER-1 |
| 12 | `test_METER2_lose_rating`, `_lose_cover`, `_lose_two_warnings` | METER-2 |
| 13 | `test_TIME1_day_cap_8h`, `test_TIME1_low_focus_cost_plus_50pct` | TIME-1 |
| 14 | `test_SPRINT1_illegal_transition` (every illegal pair) | SPRINT-1 |
| 15 | `test_PILE1_card_density_by_sprint` (sprint 1 ≈ 2) | PILE-1 |
| 16 | `test_PILE2_illegal_second_card` | PILE-2 |
| 17 | `test_PILE3_ignored_card_escalates_never_disappears` | PILE-3 |
| 18 | `test_PILE4_hidden_bug_rate_45_55` (1,000 delegations) | PILE-4 |
| 19 | `test_STAND1_accurate_only_if_unlocked`, `test_STAND1_cover_deltas` | STAND-1 |
| 20 | `test_MEM1_contradiction_adds_10_once` | MEM-1 |
| 21 | `test_PERK1_ai_assistant_wrong_1_in_5_seeded`, `_flag_off_always_right` | PERK-1 |
| 22 | `test_PERK1_points_not_in_process_score` | PERK-1 |
| 23 | `test_TUT1_costs_30min_unlocks_concept` | TUT-1 |
| 24 | `test_PROC1_solo_scores_lower_than_coach_delegate` | PROC-1 |
| 25 | `test_ASSESS1_matches_e2_certificate_fixed_seed` | ASSESS-1 |
| 26 | `test_END1_four_endings_have_debrief_data` | END-1 |
| 27 | `test_bot_replay_hash` (same seed + commands → same event-log hash) | essentials A2 |
| 28 | `test_rng_streams_independent` (extra draw in one stream does not move another) | spec 6.4 |
| 29 | `test_MVP_attack_check_minus_0_8_minus_150` | MVP scope |
| 30 | `test_E1_context_build_under_130ms` | spec 6.8 |

## Build order
1. Schemas + balance.yaml + 4 tickets (author: draft; **second human reviews answer keys**, [OPEN] who).
2. Interpreter + golden tests.
3. Reducer: meters, push table, DoD, repeat factor, time.
4. Scheduler: cards, escalation, calls, delegation, pings.
5. Stage machine via E1; standup + memory (rules side).
6. E1/E2 adapter; process-log mapping.
7. Scripted bot (`tools/bot.py`): policies `solo`, `coach_delegate`, `random_seeded`; must be able to win and lose.

## Gate
- All M1 tests green in CI; ruff, mypy strict on `src/rules`.
- Bot plays a full sprint; same final Rating, Cover, process score across 100 runs on a fixed seed.
- E1 context build ≤ 130 ms.
- Coverage on `src/rules` ≥ 90% [PROPOSED].

## Out of M1
HTTP, DB, real model, UI.
