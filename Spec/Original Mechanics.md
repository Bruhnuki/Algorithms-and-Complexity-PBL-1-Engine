# Original Mechanics (spec-breaking)

Branch `experimental/original-mechanics`, built on top of `experimental/engagement-mechanics`. It adds the **original** versions of five research mechanics that `Spec/Engagement Research.md` section 6.0 marked "needs a spec change". They break the spec on purpose so they can be playtested against the spec-fit versions. Nothing here is on `main` or on the first experimental branch.

## How to run it

```bash
cd ".claude/worktrees/originals"
```

```bash
PORT=8003 DB_PATH=fixit_orig.db python run_dev.py
```

Open `http://localhost:8003/play/`. In PowerShell, set the variables first: `$env:PORT = "8003"; $env:DB_PATH = "fixit_orig.db"`, then `python run_dev.py`.

**Switches:** `content/balance.yaml` → `originals.<name>.enabled`. Turn any one off to compare it with the spec-fit version on the same branch. They only run when `experimental.enabled` is also true.

## The five originals

| ID | Mechanic | What it does | Spec it breaks |
| --- | --- | --- | --- |
| O1 | **Action hand** (M1 original) | Each standup deals a hand of 5 action cards from your deck (Work, Test, Delegate, Coach, Defer, Call, Learn, Assist). Each move needs the matching card; playing it discards it. A finished push draws a card. **Regroup** throws the hand away and draws a new one for 30 game minutes. Between sprints you can add cards (40 pts) or remove them (30 pts) to shape the deck. | PILE-2 (all moves always available), G1 (every card settleable in 1 to 3 actions) |
| O2 | **Change-by-change review** (M2 original) | Delegated work comes back as a submission of 5 changes. You are told how many are faulty, not which. **Test** a change (Test card, 5 min), **Ask** the author (3 min, costs that teammate's trust), or ask the **AI** (Assist card, wrong 1 time in 5). Fix a faulty change (Work card, 10 min), then **Ship it** or **Send it back**. Low trust makes that teammate's next delegations buggier. A submission still out at the review ships as it stands. | CODE-1 to CODE-3 and G3: you can review without reading code. Adds a Trust stat the spec does not have. |
| O3 | **Score multiplier** (M4 original) | Push points × (1 + process score ÷ 100 + 0.25 per honest push in a row, capped at +1.0). The multiplier uses the process score from before the push, so the preview on the push panel is exact. | PERK-1 ("Points never feed the process score"), CODE-5 fixed points, END-1's Points-vs-process gap |
| O4 | **Release train** (M7 original) | Pushes go into a release of up to 5 items. Their points wait there. **Ship the release** (5 min) to bank base points × (1 + 0.25 per extra item). If anything in it is buggy or a security hole, the bonus is lost and only base points are banked. Anything left unshipped goes out at the review. | CODE-5 (each push resolves on its own) |
| O5 | **Public leaderboard** (M15 original) | `GET /api/v1/leaderboard?seed=<code>` ranks finished runs by run score, with display names, style ranks, your best place and the median. The debrief shows it for your challenge code. | MVP out-of-scope list (leaderboards), shows display names to other students |

Typed student text (the other excluded idea) is still **not** built: it would open a prompt-injection path to the model (spec 6.5.1).

## Starting values (`balance.yaml` → `originals`)

| Section | Values |
| --- | --- |
| `action_hand` | hand 5; starter deck work 4, test 3, delegate 2, coach 1, defer 2, call 2, learn 1, assist 1; draw 1 after a push; regroup 30 min; add 40 pts, remove 30 pts |
| `change_review` | 5 changes; 1 to 2 faulty when the delegation came back bugged, 20% chance of 1 when clean; test 5 min, ask 3 min, fix 10 min, send back 2 min; trust 3 of 5; +5% bug chance per missing trust point |
| `score_multiplier` | 0.01 per process point; +0.25 per honest push in a row, cap +1.0 |
| `release_train` | +0.25 per extra item; max 5 items; ship 5 min |
| `leaderboard` | top 10 |

## Tests

`tests/test_o_originals.py` has 11 tests: switches off, determinism, winnability, each original, and the leaderboard API. All earlier suites run with the originals switched off and still pass (173 tests in total).

## Findings from the scripted bots (10 seeds, all originals on)

| Bot | Wins | Median points |
| --- | --- | --- |
| Fixes everything itself | 7 of 10 | about 3,550 |
| Coaches and delegates | 3 of 10 | about 2,130 |
| Reckless | 0 of 10 | about 50 |

- **The originals flip the Scrum lesson.** With change-by-change review, every delegation costs cards, minutes and trust, so the bot that coaches and delegates now wins less often than the one that does everything itself. The spec's goal G2 is the opposite. The cheapest levers: make Ask free of trust when trust is high, lower `faulty_if_bugged`, or give delegation a card refund.
- **Scores are about 5 times higher** than on the first experimental branch, because of the multiplier and the release bonus. Heat and shop prices were tuned for the old range.
- In a browser run, a review shipped buggy because the hand ran out of Test cards and the author's trust ran out before both faults were found. That is the intended scarcity, but it may feel harsh; playtest it.
- Not playtested by people. The leaderboard replays every finished run on each request; fine for a class, slow for thousands of runs.
