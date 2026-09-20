#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def main() -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Run CitationChecker over the micro benchmark")
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--thinking")
    parser.add_argument("--out", type=Path, default=here / "runs")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    cases = [json.loads(x) for x in (here / "cases.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    if args.limit:
        cases = cases[: args.limit]
    args.out.mkdir(parents=True, exist_ok=True)
    predictions = []

    for i, case in enumerate(cases, 1):
        tid = case["task_id"]
        task = here / "tasks" / f"{tid}.md"
        run_dir = args.out / tid
        cmd = [
            "citationchecker", "check", str(task), "--out", str(run_dir),
            "--provider", args.provider, "--model", args.model,
        ]
        if args.thinking:
            cmd += ["--thinking", args.thinking]
        print(f"[{i}/{len(cases)}] {tid}")
        proc = subprocess.run(cmd, check=False)
        report = run_dir / "workspace" / "output" / "citation-report.json"
        if proc.returncode != 0 or not report.exists():
            print(f"  failed (exit={proc.returncode})")
            continue
        data = json.loads(report.read_text(encoding="utf-8"))
        citations = data.get("citations", [])
        if not citations:
            print("  no citation item in report")
            continue
        item = citations[0]
        predictions.append({
            "task_id": tid,
            "reference_status": item.get("reference_status"),
            "support": item.get("support"),
        })

    pred_path = args.out / "predictions.jsonl"
    pred_path.write_text("\n".join(json.dumps(x) for x in predictions) + ("\n" if predictions else ""), encoding="utf-8")
    print(f"predictions: {pred_path}")
    print(f"score with: python {here / 'evaluate.py'} {pred_path}")
    return 0 if len(predictions) == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
