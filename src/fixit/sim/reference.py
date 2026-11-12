"""The numbers published in the paper (Tables 1 to 3), so every run can be shown next to what the paper reported.
Columns of EXP2: arrival rate per hour -> (M10 abandoned, M11 abandon %, M1 turn s, M4 LLM util %, M5 sandbox util %, M3 throughput /h)."""
from __future__ import annotations

EXP2 = {
    5: (0.0, 0.00, 13.0, 10.6, 8.1, 4.8), 10: (0.0, 0.00, 13.0, 23.1, 17.3, 10.5), 15: (0.0, 0.00, 13.1, 32.0, 23.9, 14.7),
    20: (0.0, 0.00, 13.3, 42.4, 32.0, 19.5), 25: (0.6, 0.10, 13.8, 54.3, 40.8, 24.7), 30: (1.5, 0.21, 15.3, 67.0, 49.2, 30.2),
    35: (3.0, 0.36, 18.6, 76.9, 57.4, 35.0), 40: (15.4, 1.65, 33.1, 86.5, 63.5, 38.9), 45: (79.7, 7.74, 68.9, 93.6, 64.6, 40.3),
    50: (246.9, 21.83, 101.4, 95.3, 61.0, 37.5), 55: (423.6, 34.24, 109.2, 95.8, 56.2, 34.5), 60: (654.2, 47.30, 113.8, 96.2, 51.1, 30.9),
    65: (818.7, 54.93, 116.0, 96.3, 48.5, 28.5), 70: (1011.6, 62.46, 117.7, 96.9, 42.4, 25.8), 75: (1221.8, 69.48, 119.2, 97.0, 36.8, 22.8),
    80: (1313.1, 71.57, 119.7, 97.2, 36.6, 22.2),
}
EXP2_COLUMNS = ("M10_abandoned", "M11_abandon_pct", "M1_turn_response_s", "M4_llm_util_pct", "M5_sandbox_util_pct", "M3_throughput_per_h")

# Table 1: baseline (10/h), stress 30/h, 45/h, 60/h, Option A (7 slots + 2), Option B (6 slots + 2, E1)
TABLE1 = {
    "scenarios": ["Exp 1 baseline (10/h)", "Exp 2 at 30/h", "Exp 2 at 45/h", "Exp 2 at 60/h (broken)", "Exp 3 Option A (7+2)", "Exp 3 Option B (6+2, E1)"],
    "M1_turn_response_s": [13.0, 15.3, 68.9, 113.8, 42.1, 28.8],
    "M2_session_min": [37.3, 38.9, 67.2, 89.9, 52.5, 45.6],
    "M3_throughput_per_h": [9.99, 30.2, 40.3, 30.9, 58.2, 59.7],
    "M4_llm_util_pct": [22.2, 67.0, 93.6, 96.2, 92.1, 87.6],
    "M5_sandbox_util_pct": [16.8, 49.2, 64.6, 51.1, 48.1, 49.0],
    "M7_llm_queue_max": [1.5, 12.2, 48.6, 53.9, 51.4, 46.4],
    "M10_abandoned": [0, 1.5, 79.7, 654.2, 0, 2.2],
    "M11_abandon_pct": [0.00, 0.21, 7.74, 47.30, 0.00, 0.15],
}

# Table 3 (60 students/h): configuration -> (llm slots, sandbox workers, total units, M11 %, M2 min, M3 /h, M4 %)
TABLE3 = [
    ("Baseline at the broken load (no E1)", 5, 1, 6, 47.66, 89.3, 30.7, 96.3, False),
    ("Option A optimum (no E1)", 7, 2, 9, 0.00, 52.5, 58.2, 92.1, False),
    ("Option A with safety margin", 8, 2, 10, 0.00, 39.6, 59.0, 81.3, False),
    ("Option B optimum (E1 budgeted context)", 6, 2, 8, 0.15, 45.6, 59.7, 87.6, True),
    ("Option B with safety margin", 7, 2, 9, 0.00, 37.0, 60.0, 75.5, True),
]

THRESHOLDS = {"abandon_pct": 5.0, "utilization_pct": 90.0, "session_min": 60.0}   # acceptance thresholds (paper, Section 4.3)
BREAK_POINT_PER_H = 45          # first rate above the 5% limit in Experiment 2
ANALYTIC_SATURATION_PER_H = 43  # c * 3600 / (N * E[S]) = 5 * 3600 / (32 * 13)
