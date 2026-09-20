from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REFERENCE_STATUSES = {"VERIFIED", "NOT_FOUND", "METADATA_MISMATCH", "UNVERIFIABLE"}
SUPPORT_STATUSES = {
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "UNSUPPORTED",
    "INSUFFICIENT_EVIDENCE",
}
EVIDENCE_DEPTHS = {"FULLTEXT", "ABSTRACT", "METADATA", "NONE"}
SUMMARY_FIELDS = {
    "total_citations", "verified", "not_found", "metadata_mismatch", "unverifiable",
    "supported", "partially_supported", "unsupported", "insufficient_evidence",
}


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_summary_counts(summary: dict[str, Any], citations: list[dict[str, Any]], errors: list[str]) -> None:
    expected = {
        "verified": sum(item.get("reference_status") == "VERIFIED" for item in citations),
        "not_found": sum(item.get("reference_status") == "NOT_FOUND" for item in citations),
        "metadata_mismatch": sum(item.get("reference_status") == "METADATA_MISMATCH" for item in citations),
        "unverifiable": sum(item.get("reference_status") == "UNVERIFIABLE" for item in citations),
        "supported": sum(item.get("support") == "SUPPORTED" for item in citations),
        "partially_supported": sum(item.get("support") == "PARTIALLY_SUPPORTED" for item in citations),
        "unsupported": sum(item.get("support") == "UNSUPPORTED" for item in citations),
        "insufficient_evidence": sum(item.get("support") == "INSUFFICIENT_EVIDENCE" for item in citations),
    }
    for key, value in expected.items():
        if key in summary and summary.get(key) != value:
            errors.append(f"summary.{key} must equal the corresponding citation count")


def verify_report(markdown_path: Path) -> tuple[bool, list[str], dict | None]:
    errors: list[str] = []
    markdown_path = markdown_path.resolve()
    if not markdown_path.exists():
        return False, [f"missing report: {markdown_path}"], None

    json_path = markdown_path.with_suffix(".json")
    if not json_path.exists():
        return False, [f"missing companion JSON: {json_path}"], None

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, [f"invalid JSON: {exc}"], None
    if not isinstance(data, dict):
        return False, ["top-level JSON value must be an object"], None

    citations_value = data.get("citations")
    if not isinstance(citations_value, list):
        errors.append("top-level 'citations' must be a list")
        citations: list[dict[str, Any]] = []
    else:
        citations = [item for item in citations_value if isinstance(item, dict)]

    required = {"citation", "claim", "reference", "reference_status", "support", "evidence_depth", "reason"}
    seen_ids: set[str] = set()
    for i, item in enumerate(citations_value if isinstance(citations_value, list) else []):
        if not isinstance(item, dict):
            errors.append(f"citations[{i}] must be an object")
            continue
        missing = sorted(required - item.keys())
        if missing:
            errors.append(f"citations[{i}] missing: {', '.join(missing)}")
        for field in ("citation", "claim", "reference", "reason"):
            if field in item and not _nonempty_string(item.get(field)):
                errors.append(f"citations[{i}].{field} must be a non-empty string")
        identifier = item.get("citation")
        if isinstance(identifier, str) and identifier.strip():
            if identifier in seen_ids:
                errors.append(f"citations[{i}].citation must be unique")
            seen_ids.add(identifier)
        if item.get("reference_status") not in REFERENCE_STATUSES:
            errors.append(f"citations[{i}].reference_status invalid")
        if item.get("support") not in SUPPORT_STATUSES:
            errors.append(f"citations[{i}].support invalid")
        if item.get("evidence_depth") not in EVIDENCE_DEPTHS:
            errors.append(f"citations[{i}].evidence_depth invalid")
        if "evidence_artifact" in item and not _nonempty_string(item.get("evidence_artifact")):
            errors.append(f"citations[{i}].evidence_artifact must be a non-empty string when present")

    summary = data.get("summary")
    if not isinstance(summary, dict):
        errors.append("top-level 'summary' must be an object")
    else:
        missing_summary = sorted(SUMMARY_FIELDS - summary.keys())
        if missing_summary:
            errors.append(f"summary missing: {', '.join(missing_summary)}")
        expected_total = len(citations_value) if isinstance(citations_value, list) else 0
        if summary.get("total_citations") != expected_total:
            errors.append("summary.total_citations must equal len(citations)")
        _check_summary_counts(summary, citations, errors)

    md = markdown_path.read_text(encoding="utf-8", errors="replace")
    if "# Citation Audit Report" not in md:
        errors.append("markdown report must contain '# Citation Audit Report'")

    return not errors, errors, data
