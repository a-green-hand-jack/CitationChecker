from __future__ import annotations

import json
from pathlib import Path

REFERENCE_STATUSES = {"VERIFIED", "NOT_FOUND", "METADATA_MISMATCH", "UNVERIFIABLE"}
SUPPORT_STATUSES = {
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "UNSUPPORTED",
    "INSUFFICIENT_EVIDENCE",
}
EVIDENCE_DEPTHS = {"FULLTEXT", "ABSTRACT", "METADATA", "NONE"}


def verify_report(markdown_path: Path) -> tuple[bool, list[str], dict | None]:
    errors: list[str] = []
    markdown_path = markdown_path.resolve()
    if not markdown_path.exists():
        return False, [f"missing report: {markdown_path}"], None

    json_path = markdown_path.with_suffix(".json")
    if not json_path.exists():
        errors.append(f"missing companion JSON: {json_path}")
        return False, errors, None

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, [f"invalid JSON: {exc}"], None

    citations = data.get("citations")
    if not isinstance(citations, list):
        errors.append("top-level 'citations' must be a list")
        citations = []

    required = {"citation", "claim", "reference_status", "support", "evidence_depth", "reason"}
    for i, item in enumerate(citations):
        if not isinstance(item, dict):
            errors.append(f"citations[{i}] must be an object")
            continue
        missing = sorted(required - item.keys())
        if missing:
            errors.append(f"citations[{i}] missing: {', '.join(missing)}")
        if item.get("reference_status") not in REFERENCE_STATUSES:
            errors.append(f"citations[{i}].reference_status invalid")
        if item.get("support") not in SUPPORT_STATUSES:
            errors.append(f"citations[{i}].support invalid")
        if item.get("evidence_depth") not in EVIDENCE_DEPTHS:
            errors.append(f"citations[{i}].evidence_depth invalid")

    summary = data.get("summary")
    if not isinstance(summary, dict):
        errors.append("top-level 'summary' must be an object")
    else:
        if summary.get("total_citations") != len(citations):
            errors.append("summary.total_citations must equal len(citations)")

    md = markdown_path.read_text(encoding="utf-8", errors="replace")
    if "# Citation Audit Report" not in md:
        errors.append("markdown report must contain '# Citation Audit Report'")

    return not errors, errors, data
