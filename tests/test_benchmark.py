from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from citation_checker.runtime.main import build_parser

ROOT = Path(__file__).resolve().parents[1]


def test_benchmark_has_ten_real_papers_and_controlled_mutations():
    manifest = json.loads((ROOT / "benchmark/corpus/manifest.json").read_text())
    rows = [json.loads(x) for x in (ROOT / "benchmark/cases.jsonl").read_text().splitlines() if x.strip()]
    assert len(manifest["papers"]) == 10
    assert len(rows) == 40
    assert {r["paper_id"] for r in rows} == {p["slug"] for p in manifest["papers"]}
    assert sum(r["construction"] == "positive" for r in rows) == 10
    assert sum(r["construction"] == "negative" for r in rows) == 30
    assert {r["mutation_type"] for r in rows if r["construction"] == "negative"} == {
        "metadata_corruption",
        "hallucinated_reference",
        "reference_swap",
    }
    for row in rows:
        task = ROOT / "benchmark/tasks" / row["task_id"]
        assert (task / "main.tex").exists()
        assert (task / "references.bib").exists()

    for paper in manifest["papers"]:
        assert (ROOT / paper["local_pdf"]).exists()
        assert (ROOT / paper["local_source_archive"]).exists()
        assert (ROOT / paper["local_source_dir"]).is_dir()


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


def test_check_defaults_to_deepseek_v4_flash():
    args = build_parser().parse_args(["check", "benchmark/tasks/atlas-transfer-scaling-valid/main.tex", "--dry-run"])
    assert args.provider == "apex-deepseek"
    assert args.model == "deepseek-v4-flash"
