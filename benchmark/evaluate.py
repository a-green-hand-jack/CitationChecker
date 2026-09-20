#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_predictions(path: Path) -> dict[str, dict]:
    if path.is_file() and path.suffix == ".jsonl":
        rows = load_jsonl(path)
        return {row["task_id"]: row for row in rows}
    if path.is_file() and path.suffix == ".json":
        obj = json.loads(path.read_text(encoding="utf-8"))
        rows = obj if isinstance(obj, list) else obj.get("predictions", [])
        return {row["task_id"]: row for row in rows}
    if path.is_dir():
        out = {}
        for report in path.rglob("citation-report.json"):
            data = json.loads(report.read_text(encoding="utf-8"))
            task_id = data.get("task_id") or report.parents[2].name
            citations = data.get("citations", [])
            if citations:
                item = citations[0]
                out[task_id] = {
                    "task_id": task_id,
                    "reference_status": item.get("reference_status"),
                    "support": item.get("support"),
                }
        return out
    raise SystemExit(f"Unsupported predictions path: {path}")


def accuracy(correct: int, total: int) -> float:
    return correct / total if total else 0.0


def main() -> int:
    p = argparse.ArgumentParser(description="Evaluate CitationChecker on the controlled ICLR 2026 benchmark")
    p.add_argument("predictions", type=Path, help="JSONL/JSON predictions or directory containing citation-report.json files")
    p.add_argument("--gold", type=Path, default=Path(__file__).with_name("cases.jsonl"))
    args = p.parse_args()

    gold = load_jsonl(args.gold)
    preds = load_predictions(args.predictions)

    ref_ok = support_ok = exact_ok = 0
    missing = []
    by_mutation = defaultdict(lambda: [0, 0])
    ref_confusion = Counter()
    support_confusion = Counter()

    for case in gold:
        tid = case["task_id"]
        public_id = case.get("public_task_id", tid)
        pred = preds.get(public_id) or preds.get(tid)
        if not pred:
            missing.append(tid)
            by_mutation[case["mutation_type"]][1] += 1
            continue
        gr = case["gold_reference_status"]
        gs = case["gold_support"]
        pr = pred.get("reference_status")
        ps = pred.get("support")
        rok = pr == gr
        sok = ps == gs
        ref_ok += int(rok)
        support_ok += int(sok)
        exact_ok += int(rok and sok)
        by_mutation[case["mutation_type"]][0] += int(rok and sok)
        by_mutation[case["mutation_type"]][1] += 1
        ref_confusion[(gr, pr)] += 1
        support_confusion[(gs, ps)] += 1

    n = len(gold)
    print(f"tasks: {n}")
    print(f"predictions found: {n - len(missing)}")
    print(f"reference-status accuracy: {accuracy(ref_ok, n):.3f} ({ref_ok}/{n})")
    print(f"support-label accuracy:    {accuracy(support_ok, n):.3f} ({support_ok}/{n})")
    print(f"overall exact match:       {accuracy(exact_ok, n):.3f} ({exact_ok}/{n})")
    print("\nby mutation type (exact match):")
    for kind in sorted(by_mutation):
        ok, total = by_mutation[kind]
        print(f"  {kind:26s} {accuracy(ok, total):.3f} ({ok}/{total})")
    print("\nreference confusion (gold -> predicted):")
    for (g, p_), count in sorted(ref_confusion.items(), key=lambda x: (str(x[0][0]), str(x[0][1]))):
        print(f"  {g} -> {p_}: {count}")
    print("\nsupport confusion (gold -> predicted):")
    for (g, p_), count in sorted(support_confusion.items(), key=lambda x: (str(x[0][0]), str(x[0][1]))):
        print(f"  {g} -> {p_}: {count}")
    if missing:
        print("\nmissing predictions:")
        for tid in missing:
            print(f"  {tid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
