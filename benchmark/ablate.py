#!/usr/bin/env python3
"""Run a paired full vs no-paper-search ablation on the same neutral tasks."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def metrics(cases: list[dict], pred_path: Path, run_dir: Path) -> dict:
    predictions = {row["task_id"]: row for row in rows(pred_path)} if pred_path.exists() else {}
    by_mutation: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    exact = ref = support = 0
    failures = len(cases) - len(predictions)
    tool_calls = tokens = latency = 0
    for case in cases:
        tid = case.get("public_task_id", case["task_id"])
        pred = predictions.get(tid)
        if pred:
            rok = pred.get("reference_status") == case["gold_reference_status"]
            sok = pred.get("support") == case["gold_support"]
            ref += int(rok); support += int(sok); exact += int(rok and sok)
            by_mutation[case["mutation_type"]][0] += int(rok and sok)
        by_mutation[case["mutation_type"]][1] += 1
        receipt = run_dir / tid / "receipt.json"
        if receipt.exists():
            data = json.loads(receipt.read_text())
            summary = data.get("trajectory_summary", {})
            tool_calls += sum(summary.get("tool_counts", {}).values())
            tokens += summary.get("usage", {}).get("total", 0)
            latency += data.get("elapsed_seconds", 0)
    n = len(cases)
    return {
        "tasks": n, "predictions": len(predictions), "failures": failures,
        "reference_accuracy": ref / n if n else 0, "support_accuracy": support / n if n else 0,
        "joint_exact": exact / n if n else 0,
        "by_mutation": {key: {"exact": value[0], "tasks": value[1], "accuracy": value[0] / value[1] if value[1] else 0} for key, value in sorted(by_mutation.items())},
        "tool_calls": tool_calls, "model_tokens": tokens, "elapsed_seconds": latency,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=HERE / "runs" / "ablation")
    parser.add_argument("--per-mutation", type=int, default=1)
    parser.add_argument("--provider", default="apex-deepseek")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--thinking", default="medium")
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--max-tokens", type=int, default=90000)
    parser.add_argument("--max-output-tokens", type=int, default=4096)
    args = parser.parse_args()
    cases = rows(HERE / "cases.jsonl")
    selected: list[dict] = []
    for mutation in ("none", "metadata_corruption", "hallucinated_reference", "reference_swap"):
        selected.extend([case for case in cases if case["mutation_type"] == mutation][: args.per_mutation])
    if not selected:
        parser.error("selection is empty")
    ids = ",".join(case.get("public_task_id", case["task_id"]) for case in selected)
    args.out.mkdir(parents=True, exist_ok=True)
    modes = {"full": [], "no-paper-search": ["--disable-paper-search"]}
    result = {"schema_version": 1, "paired_task_ids": [case.get("public_task_id", case["task_id"]) for case in selected], "configuration": {
        "provider": args.provider, "model": args.model, "thinking": args.thinking, "max_steps": args.max_steps, "max_tokens": args.max_tokens,
        "max_output_tokens": args.max_output_tokens, "same_task_set": True,
    }, "modes": {}}
    for mode, extra in modes.items():
        mode_dir = args.out / mode
        mode_dir.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, str(HERE / "run.py"), "--task-ids", ids, "--out", str(mode_dir), "--provider", args.provider,
               "--model", args.model, "--thinking", args.thinking, "--max-steps", str(args.max_steps), "--max-tokens", str(args.max_tokens),
               "--max-output-tokens", str(args.max_output_tokens), *extra]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        (mode_dir / "launcher.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
        result["modes"][mode] = {"run_exit": proc.returncode, "metrics": metrics(selected, mode_dir / "predictions.jsonl", mode_dir)}
    (args.out / "ablation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if all(data["run_exit"] == 0 and data["metrics"]["predictions"] == len(selected) for data in result["modes"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
