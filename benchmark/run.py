#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import json
import subprocess
import os
import sys
from pathlib import Path


DEFAULT_PROVIDER = os.environ.get("CITATIONCHECKER_PROVIDER", "apex-deepseek")
DEFAULT_MODEL = os.environ.get("CITATIONCHECKER_MODEL", "deepseek-v4-flash")


def _run_case(case: dict, *, index: int, total: int, args: argparse.Namespace, here: Path) -> tuple[int, dict | None, str]:
    tid = case.get("public_task_id", case["task_id"])
    task = here / "tasks" / tid / "main.tex"
    run_dir = args.out / tid
    cmd = [
        sys.executable, "-m", "citation_checker.cli", "check", str(task), "--out", str(run_dir),
        "--provider", args.provider, "--model", args.model,
        "--max-steps", str(args.max_steps), "--max-tokens", str(args.max_tokens),
        "--max-output-tokens", str(args.max_output_tokens),
    ]
    if args.thinking:
        cmd += ["--thinking", args.thinking]
    if args.disable_paper_search:
        cmd += ["--disable-paper-search"]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    report = run_dir / "workspace" / "output" / "citation-report.json"
    if proc.returncode != 0 or not report.exists():
        detail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "no runner output"
        return index, None, f"{tid}: failed (exit={proc.returncode}; {detail})"
    data = json.loads(report.read_text(encoding="utf-8"))
    citations = data.get("citations", [])
    if not citations:
        return index, None, f"{tid}: no citation item in report"
    item = citations[0]
    prediction = {
        "task_id": tid,
        "reference_status": item.get("reference_status"),
        "support": item.get("support"),
    }
    return index, prediction, f"{tid}: done"


def main() -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Run CitationChecker over the controlled ICLR 2026 benchmark")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--thinking")
    parser.add_argument("--out", type=Path, default=here / "runs")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=1, help="Concurrent CitationChecker tasks (default: 1)")
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--max-tokens", type=int, default=90000)
    parser.add_argument("--max-output-tokens", type=int, default=4096)
    parser.add_argument("--disable-paper-search", action="store_true")
    parser.add_argument("--task-ids", help="Comma-separated neutral task IDs; default runs cases in file order")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be at least 1")

    cases = [json.loads(x) for x in (here / "cases.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    if args.limit:
        cases = cases[: args.limit]
    if args.task_ids:
        wanted = set(filter(None, (x.strip() for x in args.task_ids.split(","))))
        cases = [case for case in cases if case.get("public_task_id", case["task_id"]) in wanted]
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "run_config.json").write_text(json.dumps({
        "provider": args.provider, "model": args.model, "thinking": args.thinking,
        "max_steps": args.max_steps, "max_tokens": args.max_tokens,
        "max_output_tokens": args.max_output_tokens, "paper_search_enabled": not args.disable_paper_search,
        "task_ids": [case.get("public_task_id", case["task_id"]) for case in cases],
    }, indent=2) + "\n", encoding="utf-8")
    indexed_predictions: dict[int, dict] = {}
    print(f"running {len(cases)} cases with {args.workers} worker(s)")
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(_run_case, case, index=i, total=len(cases), args=args, here=here)
            for i, case in enumerate(cases)
        ]
        for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
            index, prediction, message = future.result()
            if prediction is not None:
                indexed_predictions[index] = prediction
            print(f"[{completed}/{len(cases)}] {message}", flush=True)

    predictions = [indexed_predictions[i] for i in range(len(cases)) if i in indexed_predictions]

    pred_path = args.out / "predictions.jsonl"
    pred_path.write_text("\n".join(json.dumps(x) for x in predictions) + ("\n" if predictions else ""), encoding="utf-8")
    print(f"predictions: {pred_path}")
    print(f"score with: python {here / 'evaluate.py'} {pred_path}")
    return 0 if len(predictions) == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
