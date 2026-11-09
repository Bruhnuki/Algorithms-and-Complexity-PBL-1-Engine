# Traceability

Requirement → primary tests → milestone. `MVP`: Y/N. A requirement is done only when **all** its listed tests are in CI and green.

| ID | MVP | Milestone | Tests (prefix `test_`) |
| --- | --- | --- | --- |
| AUTH-1 | Y | M2 | `AUTH1_password_never_in_db_or_logs`, `AUTH1_argon2id_params`, `AUTH1_generic_error_wrong_pw_vs_unknown_email`, `SEC_bruteforce_lockout` |
| AUTH-2 | Y | M2 | `AUTH2_cross_user_403`, `AUTH2_idle_and_absolute_timeout`, `AUTH2_logout_invalidates_server_side`, `SEC_cookie_flags`, `SEC_csrf_required_on_state_change` |
| PILE-1 | Y | M1 | `PILE1_card_density_by_sprint`, `e2e_pile_shows_cards_with_timers` |
| PILE-2 | Y | M1, M2 | `PILE2_illegal_second_card` (rules + HTTP) |
| PILE-3 | Y | M1 | `PILE3_ignored_card_escalates_never_disappears` |
| PILE-4 | Y | M1 | `PILE4_hidden_bug_rate_45_55` |
| CODE-1 | Y | M1 | `CODE1_all_tickets_validate_schema` |
| CODE-2 | Y | M1 | `CODE2_one_correct_option`, `CODE2_wrong_options_have_bug_type`, `INTERP_golden_outputs_all_options` |
| CODE-3 | Y | M1 | `CODE3_security_ticket_passes_runs`, `CODE3_five_runs_plain_english`, `INTERP_terminates_property` |
| CODE-4 | Y | M1, M4 | `CODE4_unticked_box_adds_5_cover`, `e2e_dod_unticked_push_shows_cover_cost` |
| CODE-5 | Y | M1, M4 | `CODE5_push_result_table`, `CODE5_runtime_error_blocks_push`, `CODE5_run_shows_failure_still_pushable`, `e2e_runtime_error_blocks_push_message` |
| METER-1 | Y | M1 | `METER1_repeat_reward` |
| METER-2 | Y | M1 | `METER2_lose_rating`, `METER2_lose_cover`, `METER2_lose_two_warnings` |
| TIME-1 | Y | M1, M2 | `TIME1_day_cap_8h`, `TIME1_low_focus_cost_plus_50pct`, `tick_clamped_and_scaled` |
| SPRINT-1 | Y | M1, M2, M4 | `SPRINT1_illegal_transition`, `SPRINT1_illegal_transition_http`, `e2e_full_sprint` |
| STAND-1 | Y | M1, M4 | `STAND1_accurate_only_if_unlocked`, `STAND1_cover_deltas`, `e2e_standup_accurate_hidden_if_locked` |
| MEM-1 | Y | M1, M3 | `MEM1_contradiction_adds_10_once`, `MEM1_e1_segments_within_budget_3000_cap_4000`, `MEM1_pinned_persona_and_dod_always_included`, `MEM1_contradiction_prompt_uses_stored_answer` |
| TEAM-1 | Y | M3, M4 | `TEAM1_model_down_fallback`, `TEAM1_timeout_fallback`, `TEAM1_schema_invalid_retry_once_then_fallback`, `TEAM1_no_spoiler`, `TEAM1_no_secret_leak`, `TEAM1_max_40_words`, `TEAM1_quota_20_per_minute`, `TEAM1_fallback_pool_ge_3_per_teammate_event`, `TEAM1_state_untouched_by_model`, `e2e_full_sprint_model_off` |
| HACK-1 | **N** | Post-MVP | (not built; MVP uses `MVP_attack_check_minus_0_8_minus_150`) |
| PERK-1 | Y (AI Assistant) | M1 | `PERK1_ai_assistant_wrong_1_in_5_seeded`, `PERK1_flag_off_always_right`, `PERK1_points_not_in_process_score` |
| TUT-1 | Y (2) | M1, M4 | `TUT1_costs_30min_unlocks_concept` |
| PROC-1 | Y | M1 | `PROC1_solo_scores_lower_than_coach_delegate` |
| END-1 | Y | M1, M2, M4 | `END1_four_endings_have_debrief_data`, `END1_debrief_all_four_endings_http`, `e2e_debrief_renders_four_endings` |
| INSTR-1 | Y | M2, M4 | `INSTR1_cohort_isolation`, `INSTR1_transcript_list_and_open`, `e2e_instructor_sees_only_own_cohort` |
| ASSESS-1 | Y | M1, M2 | `ASSESS1_matches_e2_certificate_fixed_seed`, `ASSESS1_pre_post_submit_and_gain` |

## Cross-cutting tests

| Concern | Test | Milestone |
| --- | --- | --- |
| Determinism | `bot_replay_hash`, `rng_streams_independent`, `state_replay_rebuild_after_restart` | M1, M2 |
| Contract | `contract_openapi_matches_code`, schemathesis | M2 |
| Append-only log | `run_events_append_only` | M2 |
| Idempotency | `cmd_idempotent_client_seq` | M2 |
| Performance | `E1_context_build_under_130ms`, `perf_api_p95_150ms_no_model`, `load_10_players` | M1, M2, M5 |
| Front end safety | `e2e_dialogue_text_is_escaped`, `e2e_csp_blocks_inline_script`, `UI_no_rules_in_js` | M4 |
| MVP gate | `bot_vs_browser_same_final_meters` | M4 |
| Privacy | `PRIV_consent_required_before_run` | M2 |
| Engines | the existing 19 `pbl_engine` tests | every CI run |

## Coverage check
Every row in `docs/prd.md` §4 appears above. Keep this file in sync: adding a requirement means adding its row **before** its test.
