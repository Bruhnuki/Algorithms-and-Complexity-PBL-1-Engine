# Agent Spec

Two meanings of "agent" matter here, so this doc has two parts:

- **Part A**: rules for **coding agents** (Claude Code etc.) that build this repo. Purpose: stop hallucination, enforce spec- and test-driven work.
- **Part B**: spec for the **in-game AI teammates** (Product Owner, two Developers) and the dialogue gateway that drives them.

Tags: **[SPEC]**, **[PROPOSED]**, **[OPEN]**.

---

# Part A: Coding-agent contract

## A1. Read order (mandatory at session start)
1. `docs/architecture-essentials.md`
2. The PRD rows for the requirement IDs in the task
3. `plan/` milestone file for the current milestone
4. Only then, the code

## A2. Loop for every task
1. **Identify IDs.** Name the requirement ID(s). No ID → no task; propose a spec change first.
2. **Red.** Write the failing test named `test_<ID>_<behaviour>`. Run it; show it fail for the right reason.
3. **Contract first.** API change → edit `openapi.yaml` / JSON Schema first; contract tests must fail before implementation.
4. **Green.** Smallest code to pass. No extra features.
5. **Refactor** with tests green.
6. **Gate.** `ruff`, `mypy`, content validation, full test suite.
7. **Report.** What changed, which tests, anything skipped, any [PROPOSED] introduced.

## A3. Anti-hallucination rules
- Never invent: endpoints, event names, error codes, balance numbers, ticket content, library APIs, `pbl_engine` internals. If not in spec/essentials, mark **[PROPOSED]** in docs and ask when it affects a public contract.
- Verify before using a library API: read installed version / docs. Do not assume flags (e.g. llama-server options) — check `--help` of the installed build.
- Read `pbl_engine` source before writing the adapter. It is not in this repo's docs.
- Benchmarks are estimates until M0 measures them. Never write an estimate as a measured fact.
- If the spec contradicts itself or is silent, stop and ask (see essentials §E). Do not choose silently.
- Do not paraphrase numbers from memory: copy from `balance.yaml` / essentials.

## A4. Hard prohibitions (from essentials §D)
LLM/browser deciding state · student text to model · eval/exec on content · wall clock or global RNG in reducer · state stored as truth · DB access from E1/E2/reducer · exposing model or `/internal/*` · build step/frontend framework · hardcoded balance numbers · altering `solve()` schema · building deferred features · unvalidated model output · points feeding process score.

## A5. Definition of done
Named test in CI and green · contract/schema updated first · golden outputs pass for any content change · scripted bot still wins and loses after balance change · docs updated with tags.

## A6. Scope control
- MVP list in `docs/mvp-scope.md` is the only buildable surface until the gate passes.
- Prefer deleting/reusing over adding. No speculative abstractions. One implementation behind each interface until a second is needed.
- Commit granularity: one requirement ID (or one sub-behaviour) per commit; message starts with the ID.

## A7. Subagent / delegation rules [PROPOSED]
- Delegate only read-only research (e.g. "how does `pbl_engine.solve` validate input?") or independent test-writing for a single ID.
- Never delegate an edit of `rules/` and `content/` to the same agent at once (answer-key review needs a second reader).
- Every ticket answer key needs a **second human** reviewer ([OPEN]: who). An agent may draft, never approve.

## A8. Prompt template for implementing a requirement [PROPOSED]
```
Implement <ID> from docs/prd.md.
Read first: docs/architecture-essentials.md, plan/<milestone>.md.
1. Write failing test test_<ID>_... (show failure).
2. Update openapi.yaml/schema first if a contract changes.
3. Minimal implementation. No other requirements.
4. Run: ruff, mypy, pytest. Report results.
Do not change: solve() schema, balance numbers outside balance.yaml.
Stop and ask if the spec is silent on something a public contract depends on.
```

---

# Part B: In-game AI teammates

## B1. Cast [SPEC: one PO + two Developers; names/personalities PROPOSED]

| Teammate | Role | Persona sheet fields [PROPOSED] |
| --- | --- | --- |
| Product Owner | Sends status demands, priority pressure | name, role, voice, pet peeves, **secret**, example lines |
| Developer 1 | Pings clues/noise, asks standup questions | same |
| Developer 2 | Help calls, traps ("just push it") | same |

Each has a **secret** (the gateway must never leak teammate A's secret in teammate B's line, [SPEC] validation rule). Names stay in `content/teammates/*.json`; no real brands.

## B2. What the agents may and may not do

| May | May not |
| --- | --- |
| Write one in-character line per event (≤ 40 words) | Change Points, Rating, Cover, Focus |
| Pick a tone: calm, pushy, panicked | Decide whether a patch is correct |
| Reference remembered answers supplied by E1 | See student free text (none exists in MVP) |
| Hint at clues **without** stating the correct patch | Reveal the correct patch text |
| | Reveal another teammate's secret |
| | Call tools, run code, browse |

The model has **no tools**. It receives a prompt and returns JSON.

## B3. Event types the gateway handles [SPEC]
`ping_clue`, `ping_noise`, `ping_trap`, `help_call`, `standup_question`, `status_demand`.

Event → meaning:
- `ping_clue`: helpful hint toward the bug, no spoiler.
- `ping_noise`: harmless chatter.
- `ping_trap`: tempts skipping the Definition of Done ("just push it").
- `help_call`: asks the student to help; answerable by coaching.
- `standup_question`: asks about the player's last push.
- `status_demand`: PO presses for progress.

Whether a ping is clue/noise/trap is chosen by the **rules engine** (seeded `ping_type` stream), not by the model.

## B4. Request contract [PROPOSED shape]

```json
{
  "event_type": "standup_question",
  "teammate_id": "dev1",
  "persona": { "...persona sheet..." },
  "memory": [ { "seg_id": "…", "text": "…" } ],     // E1-selected, ≤ budget
  "facts": { "ticket_title": "…", "concept": "…", "player_choice": null },
  "constraints": { "max_words": 40 }
}
```
`facts` contain only data from game state, never student-typed text. `player_choice` is an enum from choices.

## B5. Response contract [SPEC]
```json
{ "text": "string (≤ 40 words)", "tone": "calm" | "pushy" | "panicked" }
```
Enforced by schema constraint at the server and re-validated in Python.

## B6. Validation and fallback [SPEC]
1. Schema valid. 2. ≤ 40 words. 3. Does not contain the correct patch text (normalised substring check on option with effect `correct`). 4. Does not contain another teammate's secret. 5. Output encoded on render.
Fail → one retry → authored fallback (≥ 3 variants per teammate per event type, chosen by seeded stream so replays match). Log `source: llm|fallback`, model name, prompt tokens, latency.

## B7. Memory (E1) [SPEC]
- E1 chooses which past segments fit the token budget (default 3,000, cap 4,000) for the stage.
- Pinned: persona sheet and Definition of Done.
- Past standup answers are stored as segments; contradiction detection is **rules-side** (compare the player's later claim to the stored answer), adds +10 Cover once (MEM-1). The model is told the remembered answer for in-character reaction only.

## B8. Prompt sketch [PROPOSED]
System: "You are <name>, <role> at a failing company. Voice: <voice>. Reply as JSON only: {text, tone}. ≤ 40 words. Stay in character. Never state the correct code fix. Never mention <list of other teammates' secrets>."
User: event type + facts + memory. Reasoning effort low. No student text.

## B9. Test plan for agents [SPEC test names / PROPOSED details]

| Test | Proves |
| --- | --- |
| `test_TEAM1_model_down_fallback` | Dead model → full sprint on authored lines |
| `test_TEAM1_timeout_fallback` | Slow model (> 10 s) → fallback |
| `test_TEAM1_no_spoiler` | Mock returning the correct patch is rejected, retried, then fallback |
| `test_TEAM1_no_secret_leak` | Another teammate's secret rejected |
| `test_TEAM1_schema_invalid_retry` | Bad JSON → 1 retry → fallback |
| `test_TEAM1_quota` | 21st call in a minute uses fallback |
| `test_MEM1_contradiction_once` | Replayed bluff adds exactly +10 once |
| `test_TEAM1_fallback_pool_size` | ≥ 3 variants per teammate per event type |
| `test_TEAM1_state_untouched` | Model output never alters meters (events identical with model on/off except transcript) |

Mock model server: tiny local HTTP stub speaking the OpenAI-compatible chat endpoint, with modes `ok`, `slow`, `dead`, `invalid_json`, `spoiler`, `secret`.

## B10. Bake-off (M0) [SPEC milestone; criteria PROPOSED]
Compare gpt-oss-20b vs Qwen3.5-9B on: tokens/s, p50/p95 latency at 4 slots, VRAM free, JSON validity rate, in-character quality (human 1–5 on 20 lines), spoiler rate. Winner recorded in `plan/M0-model-feasibility.md`.

## B11. AI Assistant perk (player-facing tool) [SPEC]
Wrong ≈ 1 in 5 using seeded `assistant_error` stream; config flag `ASSISTANT_FLAKY` off makes it always right (tests). It is **rules-side** (picks from ticket options), not the LLM.
