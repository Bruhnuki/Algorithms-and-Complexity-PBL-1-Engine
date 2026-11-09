# PBL Algorithm Engine
### Beginner-friendly guide for running, testing, and understanding the project

Welcome! This project contains two Python algorithm engines. 

> **What this project is:** a Python algorithm prototype that can be run from the VS Code terminal.
>
> **What it is not:** a complete website or desktop application. The current project does not include a graphical interface or a running FastAPI server. You interact with it using Python files and terminal commands.

---

## 1. What does the engine do?

There are two main algorithms. You choose which one to run by setting the `algorithm` field in a request.

| Engine | What it does | When to use it |
|---|---|---|
| **Context Chaining** (`context_chaining`) | Chooses useful project/conversation segments while staying within a token budget and following the current project stage. | When you want to decide which information should fit in an AI context window. |
| **Learning Gain** (`learning_gain`) | Calculates learning improvement from students' pre-test and post-test scores. It can also summarize process/activity events. | When you want to summarize learning results for a group of students. |

### A few terms in plain language

- **Segment:** one piece of information, such as a project update, decision, issue, or note.
- **Token budget:** the maximum number of tokens that can be selected. A token is a text-processing unit; it is not exactly the same as a word.
- **Relevance:** the importance score assigned to a segment. In the input schema, this is from `0` to `1`.
- **Stage:** the current phase of the project: Planning, Standup, Build, or Review.
- **Pre-test:** a student's score before the learning activity.
- **Post-test:** a student's score after the learning activity.
- **Normalized learning gain:** a score that describes improvement relative to the possible improvement remaining.
- **Bootstrap confidence interval:** an estimated range of plausible values for the cohort's mean individual gain, calculated by repeatedly resampling the students' gains.

---

### Open the correct folder

1. Extract `pbl_engine.zip` (right-click it → **Extract All**).
2. Open VS Code.
3. Select **File → Open Folder**.
4. Choose the extracted `pbl_engine` folder.
5. Open **Terminal → New Terminal**.

The terminal should show a path ending in `pbl_engine`. Run project commands from this folder, not from its parent folder.

---

## Understand the project folders

```text
pbl_engine/
│
├── engine/                  The actual algorithms
│   ├── context_chaining.py  Context selection algorithm
│   ├── learning_gain.py     Student learning and process calculations
│   └── solve.py             Entry point that chooses which algorithm to run
│
├── experiments/             Research experiments and comparisons
│   ├── baseline_comparison.py
│   └── regime_sweep.py
│
├── schemas/                 Rules describing valid request/response data
│
├── tests/                   Automated checks for the algorithms
│
├── benchmark.py             Runtime and workload measurements
├── run_tests.py             Runs the automated tests
└── README.md                This guide
```

**Which file should I open?**

- To understand how the algorithms work, start with `engine/`.
- To run research comparisons, use `experiments/`.
- To check whether the code is working, run `run_tests.py`.
- To measure execution time and workload, run `benchmark.py`.

You normally do not need to edit the files inside `engine/` just to run the project.

---

## First: check that the project works

In the VS Code terminal, run:

```powershell
python run_tests.py
```

The project currently includes **19 automated tests**. A passing test means that a particular expected behavior worked.

You should see lines beginning with `PASS`. If all tests pass, the test runner should report that all 19 tests passed.

If you see an error:
- Check that the terminal is in the `pbl_engine` folder.
- Check that Python is installed.
- Copy the complete error message before changing any code.

No extra Python package is required for this test runner.

---

## Run the Learning Gain engine with a 10-student example

This example uses **fictional demonstration scores** for 10 students. They are not real research participant data. Replace them with approved, properly collected data when conducting an actual study.

### Step A — create the example file

1. In VS Code's Explorer, right-click the project folder.
2. Select **New File**.
3. Name it `demo_learning_gain.py`.
4. Paste the following code and save it.

```python
import json
from engine.solve import solve

# Fictional demonstration data for 10 students.
students = [
    {"id": "S01", "pre": 45, "post": 75},
    {"id": "S02", "pre": 50, "post": 80},
    {"id": "S03", "pre": 60, "post": 85},
    {"id": "S04", "pre": 40, "post": 70},
    {"id": "S05", "pre": 55, "post": 78},
    {"id": "S06", "pre": 35, "post": 65},
    {"id": "S07", "pre": 70, "post": 90},
    {"id": "S08", "pre": 48, "post": 76},
    {"id": "S09", "pre": 52, "post": 82},
    {"id": "S10", "pre": 42, "post": 72},
]

request = {
    "job_id": "cohort-demo-10",
    "algorithm": "learning_gain",
    "input": {
        "max_score": 100,
        "students": students,
        "bootstrap_B": 1000,
        "seed": 7
    }
}

response = solve(request)
print(json.dumps(response, indent=4))
```

### Step B — run the example

In the terminal, enter:

```powershell
python demo_learning_gain.py
```

The result is printed as JSON (a structured text format). Look for these fields inside `result.cohort`:

| Output field | Meaning |
|---|---|
| `n_students` | Number of student records processed. |
| `mean_individual_gain` | Average of the students' individual normalized gains. |
| `class_gain` | Normalized gain calculated from the cohort's average pre-test and post-test scores. |
| `ci95` | The lower and upper ends of the 95% bootstrap confidence interval for the mean individual gain. |
| `effect_detected` | `true` when the lower end of that interval is above zero. |
| `warnings` | Notes about special cases, such as a very small sample or a gain that cannot be calculated. |

**Important:** `mean_individual_gain` and `class_gain` are different calculations. Do not treat them as interchangeable. With only 8–10 students, the confidence interval should be interpreted cautiously. The code itself adds a `small_sample_ci_unreliable` warning when fewer than five usable individual gains remain; even with 8–10, a small cohort limits how widely results can be generalized.

### Change the number of students

To test 8 students, remove two student records from the `students` list. To test 9, remove one. Keep each student's `id`, `pre`, and `post` fields.

Scores must be between `0` and `max_score`. In this example, the maximum score is 100.

---

## Run the Context Chaining engine

This engine selects segments that fit within a token budget. It also checks which project stages are allowed to contribute information to the current stage.

### Step A — create the example file

Create a new file named `demo_context_chaining.py` and paste:

```python
import json
from engine.solve import solve

request = {
    "job_id": "context-demo-01",
    "algorithm": "context_chaining",
    "input": {
        "current_stage": "BUILD",
        "token_budget": 1000,
        "mode": "auto",
        "segments": [
            {
                "id": "planning-goal",
                "tokens": 180,
                "relevance": 0.95,
                "stage": "PLANNING",
                "pinned": True
            },
            {
                "id": "standup-update",
                "tokens": 220,
                "relevance": 0.75,
                "stage": "STANDUP"
            },
            {
                "id": "build-decision",
                "tokens": 300,
                "relevance": 0.90,
                "stage": "BUILD"
            },
            {
                "id": "old-planning-note",
                "tokens": 250,
                "relevance": 0.40,
                "stage": "PLANNING"
            },
            {
                "id": "review-feedback",
                "tokens": 200,
                "relevance": 0.85,
                "stage": "REVIEW"
            }
        ]
    }
}

response = solve(request)
print(json.dumps(response, indent=4))
```

### Step B — run it

```powershell
python demo_context_chaining.py
```

Look for these fields inside `result`:

| Output field | Meaning |
|---|---|
| `selected_segment_ids` | IDs of the segments selected by the algorithm. |
| `total_relevance` | Combined relevance score of the selected segments. |
| `tokens_used` | Total tokens consumed by the selected segments. |
| `candidates` | Number of eligible segments considered. |
| `mode` | Whether exact DP or greedy selection was used. |
| `dp_cells` | Number of DP cells processed; greedy mode reports zero. |
| `est_cells` | Estimated DP workload in `auto` mode. |
| `abs_gap_bound` | Greedy mode's additive upper bound on the gap from the optimal value. |

### What do the three modes mean?

Set the `mode` field to one of these:

| Mode | Meaning |
|---|---|
| `auto` | Default. Uses exact DP if estimated DP cells are at most 2,000,000; otherwise uses greedy. |
| `exact` | Forces the exact Dynamic Programming algorithm. |
| `greedy` | Forces the faster density-based greedy algorithm. |

The exact algorithm maximizes total relevance among eligible segments within the budget. Greedy sorts segments by relevance per token, then also checks the best single segment.

### Project stages and allowed transitions

The engine recognizes these stages:

1. `PLANNING`
2. `STANDUP`
3. `BUILD`
4. `REVIEW`

Allowed stage changes are:

```text
PLANNING → STANDUP → BUILD → REVIEW
                  ↑     |
                  └─────┘
```

More precisely:
- `PLANNING` can move to `STANDUP`.
- `STANDUP` can move to `BUILD`.
- `BUILD` can move to `STANDUP` or `REVIEW`.
- `REVIEW` cannot move to another stage.

The current stage also controls which segments are eligible. A segment from a future stage is not eligible yet.

A segment with `"pinned": true` is always included. Pinned segments count toward the token budget. If pinned segments alone exceed the budget, the engine returns an `INFEASIBLE` error.

---

## Run the research experiments

These commands run the experiments already included in the project. Run them from the main `pbl_engine` folder.

### A. Compare the selection strategies

```powershell
python -m experiments.baseline_comparison
```

This compares:
- **Exact DP:** the optimal reference solution.
- **Recent-first:** selects newer eligible segments first.
- **Density-greedy:** prioritizes high relevance per token.

The output includes:
- `value / DP value`: alternative solution value divided by the DP value. A result near `1.0` means it is close to DP for that instance.
- `mean`: average ratio across the generated instances.
- `min`: lowest ratio observed.
- `critical-segment recall`: proportion of the experiment's flagged critical segments selected by each method.

This experiment generates synthetic/randomized segment data. 

### B. Test different segment sizes

```powershell
python -m experiments.regime_sweep
```

This compares Greedy with exact DP under three generated segment-size ranges:
- Small: 20–300 tokens.
- Large: 500–1,500 tokens.
- Very large: 1,000–3,000 tokens.

Read the columns as follows:

| Column | Meaning |
|---|---|
| `mean OPT` | Average total relevance from exact DP. |
| `greedy/DP mean` | Average greedy value divided by DP value. |
| `worst` | Lowest greedy-to-DP ratio observed in that regime. |
| `mean bound` | Average additive gap bound reported by Greedy. |
| `bound holds` | Whether the checked DP-minus-Greedy gap stayed within the reported bound for all trials. |
| `DP ms` | Average runtime of exact DP in milliseconds. |

A ratio of `0.98` means Greedy achieved 98% of the DP value on average. It does **not** mean Greedy is guaranteed to achieve 98% on every possible dataset.

### C. Measure the benchmark

```powershell
python benchmark.py
```

This reports runtime and DP workload for different input sizes. Results depend on your computer, Python version, and system activity. Re-run on the computer used for your final evaluation.

---

## How to read a result from the engine

The `solve()` function returns a response with this general structure:

```json
{
  "job_id": "example-01",
  "algorithm": "learning_gain",
  "engine_version": "1.1.0",
  "status": "ok",
  "result": {},
  "metrics": {
    "runtime_ms": 1.234
  }
}
```

This is a simplified illustration of the response structure; actual `result` fields depend on the selected algorithm.

- `status: "ok"` means the request was processed successfully.
- `status: "error"` means the request could not be processed. Read `error.code` and `error.message`.
- `runtime_ms` is the time spent processing the request, in milliseconds.

Common error codes:

| Error code | Meaning |
|---|---|
| `MALFORMED_REQUEST` | A required field is missing or the request has the wrong structure. |
| `UNKNOWN_ALGORITHM` | The `algorithm` name is not recognized. |
| `VALIDATION_ERROR` | A value is invalid, such as an unknown stage or out-of-range score. |
| `LIMIT_EXCEEDED` | The request exceeds a configured resource limit. |
| `INFEASIBLE` | Pinned segments alone exceed the token budget. |
| `ILLEGAL_TRANSITION` | The requested stage change is not allowed. |
| `INTERNAL_ERROR` | An unexpected error occurred inside the engine. |

---

## Important limits and research notes

The dispatcher in `engine/solve.py` applies these limits:

| Item | Current limit |
|---|---:|
| Context segments per request | 2,000 |
| Token budget | 32,000 |
| Students per request | 10,000 |
| Bootstrap resamples | 100–10,000 |
| Process event records | 100,000 |
| Process categories | 32 |

Other important notes:

- The Learning Gain engine expects scores on the same scale, from zero to `max_score`.
- A student whose pre-test and post-test both equal the maximum score has an undefined normalized gain; that gain is excluded from the individual mean and confidence interval.
- `effect_detected` is based on whether the calculated 95% interval's lower endpoint is above zero. It is not, by itself, proof of causation.
- The process-event summary is optional. It is only calculated when `process_events` is included in the Learning Gain input.
- The experiment scripts use generated data and fixed random seeds. They are for algorithm evaluation, not a substitute for real participant data.
- Runtime measurements vary across computers. Report the hardware and software environment when presenting benchmark results.
- The current project is a Python engine prototype. The FastAPI snippet in the earlier project notes is a sketch, not an implemented or tested server.

---

## Quick command reference

Run these commands from the `pbl_engine` folder:

| What you want to do | Command |
|---|---|
| Check Python | `python --version` |
| Run all automated tests | `python run_tests.py` |
| Run the runtime benchmark | `python benchmark.py` |
| Compare DP, recent-first, and greedy | `python -m experiments.baseline_comparison` |
| Compare greedy across segment-size regimes | `python -m experiments.regime_sweep` |
| Run your 10-student example | `python demo_learning_gain.py` |
| Run your context selection example | `python demo_context_chaining.py` |

If `python` does not work but `py` does, replace `python` with `py`.

---

## If something goes wrong

**“python is not recognized”**
- Install Python and enable **Add Python to PATH**, or try the `py` command.

**“No module named experiments” or “No module named engine”**
- The terminal is probably not in the main `pbl_engine` folder. Open that folder in VS Code and try again.

**The example file cannot be found**
- Make sure you saved `demo_learning_gain.py` or `demo_context_chaining.py` directly inside the main `pbl_engine` folder.

**The output says `status: error`**
- Read the error code and message. Check spelling, required fields, stage names, score ranges, and token budget.

**A benchmark takes longer than expected**
- Benchmark times vary. Let it finish, and avoid running several heavy tasks at once.

---

## Suggested first-time walkthrough

If you are new to the project, follow this order:

1. Run `python --version`.
2. Run `python run_tests.py`.
3. Create and run `demo_learning_gain.py`.
4. Create and run `demo_context_chaining.py`.
5. Run `python -m experiments.baseline_comparison`.
6. Run `python -m experiments.regime_sweep`.
7. Run `python benchmark.py`.

Once these work, you have successfully navigated both engines, tested the project, and reproduced its included algorithm experiments.

**You do not need to understand every line of Python to run the project.** Start by changing only the example inputs (student scores, segment relevance, token counts, and budget), then observe how the outputs change.
