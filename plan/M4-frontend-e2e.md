# M4: Front end and MVP bot gate

**Goal:** a student plays one full sprint in the browser; the headless bot and the browser agree.

## Scope
Static HTML/CSS/vanilla JS modules, no build step, no rules in the page. 4 panels on one screen: TeamChat, CodeDesk, StarWall, LearnLoop (names may change; keep labels in content). Screens: login/register, consent, pre-test, game, debrief, post-test, instructor list + transcript.

## Tests first

| Test | Req |
| --- | --- |
| `test_e2e_full_sprint` (Playwright, model mock `ok`) | SPRINT-1 |
| `test_e2e_full_sprint_model_off` (mock `dead`) | TEAM-1 |
| `test_e2e_login_consent_pretest_flow` | AUTH-1, ASSESS-1 |
| `test_e2e_cannot_open_other_students_run` | AUTH-2 |
| `test_e2e_pile_shows_cards_with_timers` | PILE-1 |
| `test_e2e_dod_unticked_push_shows_cover_cost` | CODE-4 |
| `test_e2e_runtime_error_blocks_push_message` | CODE-5 |
| `test_e2e_standup_accurate_hidden_if_locked` | STAND-1 |
| `test_e2e_debrief_renders_four_endings` | END-1 |
| `test_e2e_instructor_sees_only_own_cohort` | INSTR-1 |
| `test_e2e_dialogue_text_is_escaped` (injected `<script>` in a fallback fixture) | spec 6.7 |
| `test_e2e_csp_blocks_inline_script` | spec 6.7 |
| `test_UI_no_rules_in_js` (static check: no balance constants / scoring logic in `src/web`) | arch 4.1 |
| `test_bot_vs_browser_same_final_meters` (same seed, same command list) | MVP gate 2 |

## Build order
1. State renderer (pure function of state JSON → DOM) and polling loop (1 s `GET state?since=`), tick sender with real elapsed ms.
2. CodeDesk: ticket doc, numbered lines, flag, option picker, Run Script results, DoD checklist, Push.
3. Pile + move menu (Work, Triage, Delegate, Coach, Defer), call overlay with timer.
4. TeamChat (render with `textContent` only), standup prompt with 3 answers (accurate hidden if locked).
5. StarWall (Rating/ratings feed), LearnLoop (2 tutorials, `???` on locked concepts).
6. Meters bar (Points, Rating, Cover, Focus), clock, stage indicator.
7. Debrief, post-test, instructor views.
8. Accessibility basics [PROPOSED]: keyboard focus, contrast, labels.

## Gate
Playwright suite green in CI with model `ok` and `dead`; bot and browser reach identical final Rating, Cover, process score on a fixed seed; no console errors; no inline script (CSP).

## Out of M4
Mobile layout, fake browser tabs, hacker event UI.
