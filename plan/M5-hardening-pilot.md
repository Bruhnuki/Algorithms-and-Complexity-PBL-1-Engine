# M5: Hardening and pilot readiness

**Goal:** safe to expose over Tailscale to 8–10 students; MVP acceptance gate proven.

## Tests / checks first

| Check | Type | Req |
| --- | --- | --- |
| `test_load_10_players` (10 virtual players, full sprint; API p95 < 150 ms w/o model; dialogue p50 < 3 s, p95 < 8 s; slot util < 75%) | automated | spec 6.8 |
| VRAM free ≥ 1 GB during load | automated + `nvidia-smi` log | spec 6.8 |
| Port scan from another device: only app port reachable; llama-server and `/internal/*` unreachable | manual script | spec 6.7 |
| Funnel exposes only the app port; instructor/admin routes need tailnet-only path or instructor role; ACL tag on PC | **manual checklist** | spec 6.7 |
| Repo secret scan clean; secrets only in env file outside repo | automated | spec 6.7 |
| Brute-force, cookie, CSRF, XSS re-run against the public URL | automated | spec 6.7 |
| Soak: 45-min campaign equivalent (bot x 3 sprints [PROPOSED]) no memory growth beyond budget | script | |
| PC resilience: sleep disabled, services auto-start after reboot, health-check script passes | manual | spec 7.3 |
| Privacy checklist (consent screen, retention limited to pilot, RA 10173) **signed** | document | spec 6.7 |
| Content: every ticket's answer key reviewed by a second person, signed in ticket metadata | manual | spec 7.3 [OPEN who] |
| Name clash check on the four app names | manual | spec 7.3 |

## Playtest (MVP gate 4)
5 people, one sprint each. Record real minutes (target 6–10) and questionnaire "stressful but fair" (≥ 4 of 5). Tune only `balance.yaml`; after each change rerun scripted bot (win **and** lose still possible) and `test_bot_replay_hash` for the new fixed hash.

Questionnaire [PROPOSED]: stressful? fair? any card unsettleable in ≤ 3 actions? which bug type was unclear? standup question clear?

## Decide: Funnel vs Serve [OPEN]
Default Funnel. If students may not use a public address, switch to Tailscale Serve and invite them; no code change expected. Re-run port scan after switching.

## Final MVP gate (from docs/mvp-scope.md)
1. Every MVP requirement ID has a passing automated test in CI.
2. Scripted bot: identical final Rating, Cover, process score every run on fixed seed.
3. Full sprint completes with model server stopped.
4. 5 playtesters: 6–10 min, ≥ 4/5 "stressful but fair".

All four → MVP shipped; pilot can start (pre-test → play → post-test, E2 gain).

## Pilot ops [PROPOSED]
Pre-session: run health check, confirm model status, confirm Funnel URL, disable sleep. Post-session: export nothing (exports deferred); transcripts retained only for pilot period, then purge.
