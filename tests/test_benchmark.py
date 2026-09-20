from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_benchmark_has_12_balanced_tasks():
    rows = [json.loads(x) for x in (ROOT / "benchmark/cases.jsonl").read_text().splitlines() if x.strip()]
    assert len(rows) == 12
    assert sum(r["construction"] == "positive" for r in rows) == 6
    assert sum(r["construction"] == "negative" for r in rows) == 6
    assert {r["mutation_type"] for r in rows if r["construction"] == "negative"} == {
        "metadata_corruption",
        "reference_swap",
        "claim_strength_corruption",
    }
    for row in rows:
        assert (ROOT / "benchmark/tasks" / f"{row['task_id']}.md").exists()


def test_perfect_predictions_score_one():
    result = subprocess.run(
        [sys.executable, str(ROOT / "benchmark/evaluate.py"), str(ROOT / "benchmark/example_predictions.jsonl")],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "reference-status accuracy: 1.000" in result.stdout
    assert "support-label accuracy:    1.000" in result.stdout
    assert "overall exact match:       1.000" in result.stdout
