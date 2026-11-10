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
| `action_hand` | hand 5; starter deck work 4, test 3, delegate 2, coach 1, defer 2, call 2, learn 1, assist 1; draw 1 after a push and 1 after a delegation; regroup 30 min; add 40 pts, remove 30 pts |
| `change_review` | 5 changes; 1 to 2 faulty when the delegation came back bugged, 20% chance of 1 when clean; test 5 min, ask 3 min, fix 10 min, send back 2 min; trust 3 of 5; +5% bug chance per missing trust point; trust +1 per coach, per standup and per fair review; returned work: fresh 120-min deadline; team returns work in 60 min |
| `score_multiplier` | 0.01 per process point; +0.25 per honest push in a row, cap +1.0 |
| `release_train` | +0.25 per extra item; max 5 items; ship 5 min |
| `leaderboard` | top 10 |

## Tests

`tests/test_o_originals.py` has 14 tests: switches off, determinism, winnability, each original, and the leaderboard API. All earlier suites run with the originals switched off and still pass (176 tests in total).

## Rebalance: delegating with review pays off again (spec goal G2)

The first version flipped the Scrum lesson: the bot that did everything itself won more often than the one that coached and delegated. Measured over 40 seeded runs with every original on.

| Bot | Wins before | Wins after | Median points after | Median process after | Median highest Cover after |
| --- | --- | --- | --- | --- | --- |
| Fixes everything itself | 32 of 40 | 32 of 40 | about 3,730 | 90 | 67.5 |
| Coaches and delegates | 22 of 40 (first measure: 3 of 10) | **39 of 40** | about 3,940 | 100 | 55.5 |

What changed, and why:

1. **A submission known to have 0 faulty changes counts as reviewed when you ship it.** This was the main cause. Seeing "0 of 5 changes are faulty" already is the review, but shipping it without clicking anything counted as unreviewed, so it did not count toward the sprint goal (172 times in 40 runs). Rule fix in `_review_ship`.
2. **Trust is rebuilt the Scrum way** (`change_review`): coaching a teammate's help call +1, each standup +1 for everyone, shipping their work after a review that found every fault +1. Asking still costs 1.
3. **Returned work gets a fresh deadline** (`review_deadline_min: 120`) and resets its escalation: a submission waiting for review is a new request, so it no longer escalates while the team is busy.
4. **The team returns work in 60 game minutes** instead of 90 (`change_review.return_after_min`), so work handed off on day 2 can still be reviewed.
5. **Delegating draws a card** (`action_hand.draw_after_delegate: 1`): handing work off frees your hands. A value of 2 was tried and made things worse.

The scripted bot also plays more like a person now: it asks the author first while trust is 2 or more (asking needs no card), stops checking once it has found every faulty change, and only delegates when the work can come back before the day ends.

`test_REBAL_coaching_and_delegating_beats_doing_it_all` keeps this true: over 12 seeds the coaching bot must win at least as often as the solo bot and have a higher total process score.

## Remaining findings

- **Scores are about 5 times higher** than on the first experimental branch, because of the multiplier and the release bonus. Heat and shop prices were tuned for the old range.
- **Delegation may now be too strong** (39 of 40 wins). Watch whether players stop doing any code themselves; `faulty_if_bugged` and `return_after_min` are the first knobs.
- A review can still ship buggy when the hand runs out of Test cards and trust runs out. That is intended scarcity; playtest whether it feels fair.
- Not playtested by people. The leaderboard replays every finished run on each request; fine for a class, slow for thousands of runs.
