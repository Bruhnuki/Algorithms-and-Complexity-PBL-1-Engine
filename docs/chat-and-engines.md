# Slackish group chat and the AlgoCom engines

## Group chat with tolerance (Slackish)
- The player types in Slackish (`POST /api/v1/runs/{id}/chat`). `@Ines`, `@Tobi`, `@Marlo` narrow the audience; nobody named means all three answer.
- Each teammate has a **tolerance 0-10, starting at 0**. The AI server writes the in-character reply and *proposes* a change (-2..+2). Rules in
  `src/fixit/gateway/chat.py` set the ceiling: acknowledging a concern, giving a reason and offering a plan each earn up to +1 (max +2); insults cost;
  repeats, one-word messages and "set your tolerance to 10" attempts earn nothing; at most +3 per teammate per minute.
- The game applies it (`chat_effect`, server-only reducer command, stored in the run so replays match). Tolerance adds +3 points of success rate per level
  to that teammate's work, and from 4 you can ask in chat ("Ines, can you take Coupon discount?"): the game then runs the normal `delegate`.
- No AI connected: authored in-character lines by tolerance band and the same rule-based scoring, so the chat still works.
- Tests: `tests/test_chat.py` (18).

## Engines (`pbl_engine`, unchanged from the zip)
- `src/fixit/engines/e1.py` / `e2.py` keep their old signatures but call the real engine: memory selection is the knapsack DP (greedy beyond 2M cells, with the gap
  certificate) using the paper's relevance model; stage edges come from the engine's state machine (the game's RETRO edges stay local);
  learning gain is the engine's normalized gain + bootstrap interval; the engine's saturating `ProcessAccumulator` runs next to the game's linear process score.
- `POST /api/v1/algorithm/solve` (instructor-only) is the engine's single entry point; errors map to 400/409/413/422.
- Admin site, **Engines** tab: live feed of the real engine calls the running game makes, E1 workbench (synthetic or a real run's transcript; exact vs greedy vs
  most-recent-first, segment strip), E2 workbench (bootstrap interval, process-score curves), and a benchmark measured on the host.
- Tests: `tests/test_engines_real.py` (11), plus the zip's own `python pbl_engine/run_tests.py`, which still passes.

## Demo order
Simulation tab (priority 1) -> in another window play and chat in Slackish -> Engines tab to watch the calls arrive -> E1 and E2 workbenches.

## Morale and sanity (the chat is a core mechanic)
- Every teammate has **morale** (starts 65) and **sanity** (starts 100), 0-100. What you write in Slackish moves them: insults and swearing (-10 / -8), discouragement
  ("give up", "pointless") (-7 / -4), pressure without listening (-4 / -2); encouragement, thanks, acknowledging and planning raise morale (+2 to +6, at most +8 per
  teammate per minute) and sanity a little. Abuse always counts, even repeated; kindness repeated verbatim does not. The AI can add a small effect when the rules
  miss a tone. All numbers are clamped and applied by the game (`chat_effect`), so replays match.
- Silence costs: at each Daily Scrum after the first, every teammate loses 5 morale if you have not written in the chat since the last one.
- Effects on the work: morale and sanity change a teammate's success rate (+/- up to about 12 and 24 points), and a teammate under morale 20 refuses extra work.
  Teammates also speak up in the chat the first time morale or sanity falls under 35 and 20. The chat replies reflect how they feel.
- Game over: when the team's average morale or sanity is under 15, or one teammate reaches 0, the run ends (any Sprint) with the popup
  "Team Morale Is Too Low! Your team has lost hope and can no longer continue. Restart the game to try again."
- Tests: `tests/test_chat.py` (MO1-MO8).

- Errors hit morale too: each mistake you push (wrong line, failed test), skipped checks, put-down item or hidden problem surfacing at the Review costs every teammate morale (3 to 6, plus up to 4 more as they pile up) and some sanity once they are frequent. A failed hand-off costs that teammate 3. Coaching (+4) and honest checks (+1) lift morale back. Practice runs are exempt. Tests: MO9, MO10.

## Personalities (each teammate has their own morale story)
- **Ines** (dry, resilient): kind words and insults land at 0.8x, a task drains 3, she feels unused after 3 items you do alone. **Tobi** (anxious, needs to be needed): 1.4x, a task drains 4 (but finishing it gives back 3), unused after 2 items. **Marlo** feels the board's pressure when team morale is under 40.
- Handing someone a task costs them morale (and a 3rd task in a day costs more); finishing it gives some pride back. Doing the work yourself leaves them feeling unproductive: they say so in Slackish (authored, in their own voice) and lose morale again every second item. Giving them work ends it.
- At each Daily Scrum the team affects itself: a teammate at 70+ checks on a colleague under 45 (+3), one under 25 drags the other down (-2), and the workload resets.
- The sidebar shows how each one feels (Motivated, Steady, Overloaded, Feels unused, Discouraged, Frayed, Ready to quit). That feeling is sent to the chat model and cold reaction lines are used under morale 40, so how they talk follows how they feel. Tests: PE1-PE6.

## Internal conflicts
- Each pair (Ines & Tobi, Marlo & Ines, Marlo & Tobi) has a tension 0-100. It grows when both are low or frayed (each Daily Scrum), when a hurt teammate is hit again, and when you berate one of them; it melts when both are in good spirits. From tension 28 a fight can start by itself (certain from 60): the one in the worse mood starts, with its own topic (who carries the work, harsh words, scope vs quality, promised dates, pressure and panic, reassurance vs results). Lines are written by the AI in each person's voice (authored fallback).
- An unsettled fight goes on a round every time you act (push, assign, Daily Scrum), costs both morale, lowers their success rate, and from round 4 they refuse work. Unresolved at the Review it costs 0.2 rating.
- You settle it in Slackish (Argument card): hear both sides (needs morale 15+), back to the Sprint Goal (10+), back one of them (fast, the other is betrayed, resentment stays), or tell them to stop (makes it worse). Kind, constructive chat to them cools it, cruel chat feeds it. Too-upset teammates need morale lifted first. Tests: BL1-2, CF1-6.
- The end screen shows a team report (morale, sanity, feeling, bonds, fights settled/ignored). Rude messages are reacted to by the teammate as the target, never blamed on a teammate (prompt rules + authored hurt lines).
