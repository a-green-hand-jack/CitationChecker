import importlib.util
import json
from pathlib import Path


def test_missing_usage_remains_unknown_and_failures_stay_in_denominator(tmp_path):
    path = Path(__file__).resolve().parents[1] / "benchmark/ablate.py"
    spec = importlib.util.spec_from_file_location("ablate_under_test", path)
    ablate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ablate)
    cases = [{"task_id": f"case-{i}", "mutation_type": "none",
              "gold_reference_status": "VERIFIED", "gold_support": "SUPPORTED"} for i in (1, 2)]
    predictions = tmp_path / "predictions.jsonl"
    predictions.write_text(json.dumps({"task_id": "case-1", "reference_status": "VERIFIED", "support": "SUPPORTED"}) + "\n")
    for i, usage in ((1, 10), (2, None)):
        folder = tmp_path / f"case-{i}"
        folder.mkdir()
        (folder / "receipt.json").write_text(json.dumps({"trajectory_summary": {"usage": {"total": usage}}, "elapsed_seconds": 1}))
    result = ablate.metrics(cases, predictions, tmp_path)
    assert result["joint_exact"] == 0.5 and result["failures"] == 1
    assert result["model_tokens"] is None and result["known_model_tokens"] == 10
    assert result["unknown_usage_tasks"] == 1
