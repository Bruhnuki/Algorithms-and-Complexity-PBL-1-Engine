# Modeling and Simulation (admin demo)

The paper's discrete-event model (AnyLogic) is implemented natively in `src/fixit/sim/` and run from the admin site:
sign in as an instructor, open the **Simulation** tab.

## Paper -> code
| Paper block | Code |
|---|---|
| Source (Poisson, `user_arrival_rate`/h) | `Simulation._arrival` in `model.py` |
| Auth pool (tri 0.05/0.10/0.25 s, login ok 0.94, retry tri 10/20/40 s) | pool `auth`, `login_success_prob` |
| Think tri 20/45/90 s, E1 buildContext tri 0.001/0.05/0.13 s | `think`, `budgeted_context` |
| LLM pool (tri 4/10/25 s, 3/8/20 s with E1, abandon after 120 s) | pool `llm`, `patience_seconds` |
| Sandbox pool (tri 20/40/90 s, abandon after 300 s, revise tri 2/4/8 min, 3rd attempt passes) | pool `sandbox`, `max_attempts` |
| E2 score | final delay, then exit |
| Personas lazy 34 turns / 0.70, perfectionist 30 / 0.80 | `SimParams` |
| Metrics M1-M11, warm-up 1800 s, 24 h | `Simulation.metrics`, `_warmup` |

`des.py` is the event engine (heap future-event list, FIFO pools with time-weighted busy/queue integrals, patience timeouts).
Same model as the paper, different RNG: results match statistically, not run for run.

## What the admin can do
- **Run live**: simulated time advances in real time at an adjustable speed; change LLM slots, sandbox workers, E1 and arrival rate while it runs.
- **Experiment 1** baseline, **Experiment 2** stress sweep (5-80/h), **Experiment 3** Option A vs B at 60/h, **Validate** (12 checks: utilization law, Little's law, saturation 43/h, ...). Each shows "this run vs paper"; CSV export.
- **Measure this deployment**: times the real Argon2 verify, the real interpreter and the connected AI server and fills the model with them.

## Results vs paper
| | paper | this implementation |
|---|---|---|
| Turn response / session | 13.0 s / 37.3 min | 13.0 s / 37.3 min |
| Baseline LLM / sandbox util | 22.2% / 16.8% | ~22.8% / ~18% |
| Break point | 45/h | 45/h |
| Abandonment at 60/h | 47.3% | 48-49% |
| Option A / B | 7+2 / 6+2 | 7+2 / 6+2 |

Known difference: LLM utilization saturates at ~99-100% past the break point (paper 96-97%).

## Demo script
1. Sign in with the instructor code printed by `Start Fix it with Scrum.bat`. 2. Simulation -> Experiment 1 (smooth). 3. Experiment 2 (break at 45/h). 4. Run live with "Launch day", then Apply LLM 5 -> 8, sandbox 1 -> 2, E1 on and watch the queue drain. 5. Experiment 3 and Validate.

Tests: `tests/test_sim.py`.
