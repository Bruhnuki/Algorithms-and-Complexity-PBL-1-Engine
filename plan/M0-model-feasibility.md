# M0: Model feasibility

**Why first:** if the 5060 Ti cannot serve dialogue inside budget, the design changes (more authored lines, smaller model). Nothing else depends on this being guessed.

## Scope
Stand up `llama-server` on 127.0.0.1, measure, pick a model. No game code.

## Test-first tasks
Write the measurement script and its pass/fail asserts **before** running anything.

| # | Task | Output |
| --- | --- | --- |
| 1 | Confirm GPU is the 16 GB card ([OPEN]). Record `nvidia-smi` | note in this file |
| 2 | Move display to motherboard graphics; record idle VRAM | note |
| 3 | Install llama.cpp build; read `--help` (do not assume flags) | note |
| 4 | Serve gpt-oss-20b MXFP4: all layers GPU, ctx 20,480, 4 slots, reasoning low | running server |
| 5 | Script `tools/m0_bench.py`: send 200 dialogue requests built from stub persona + 3,000-token memory, with the `{text,tone}` JSON schema; 1, 4, 8 concurrent | CSV: tokens/s, latency p50/p95, JSON valid %, VRAM free |
| 6 | Repeat for Qwen3.5-9B Q4_K_M | CSV |
| 7 | Human rating of 20 lines per model (1–5, in character), spoiler check | table |
| 8 | If 4 slots do not fit: retry 3 slots, then shorter ctx | note |
| 9 | Decide, record in "Result" below | decision |

## Asserts the script must enforce
- p50 latency < 3 s, p95 < 8 s at the expected load (5 concurrent students ≈ 5 parallel calls max)
- VRAM free ≥ 1 GB under load
- JSON valid rate = 100% with schema constraint (any failure is a bug to investigate)
- 10-user capacity model: utilisation = calls/s × s/call ÷ slots < 75% at 3× the base rate

## Gate
All asserts pass for the chosen model. Also: server unreachable from another device on the tailnet (port scan), because it binds 127.0.0.1.

## Result (fill in)
- GPU: 
- Chosen model / quant / slots / ctx:
- Measured tokens/s (not the 4080 numbers):
- p50 / p95 latency:
- VRAM free under load:
- Decision date:

## If it fails
Order of fallbacks: 3 slots → shorter ctx → Qwen3.5-9B → smaller model → lean on authored fallback pool. The game must already work with the model off (TEAM-1), so failure is degrade, not block.
