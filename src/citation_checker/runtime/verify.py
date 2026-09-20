"""Mechanical artifact validation, not a scientific citation verifier."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REFERENCE_STATUSES = {"VERIFIED", "NOT_FOUND", "METADATA_MISMATCH", "UNVERIFIABLE"}
SUPPORT_STATUSES = {"SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "INSUFFICIENT_EVIDENCE"}
EVIDENCE_DEPTHS = {"FULLTEXT", "ABSTRACT", "METADATA", "NONE"}
SUMMARY_FIELDS = {"total_citations"} | {item.lower() for item in REFERENCE_STATUSES | SUPPORT_STATUSES}


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def verify_report(markdown_path: Path) -> tuple[bool, list[str], dict | None]:
    errors = []
    markdown_path = markdown_path.resolve()
    json_path = markdown_path.with_suffix(".json")
    if not markdown_path.is_file() or not json_path.is_file():
        return False, ["missing Markdown report or companion JSON"], None
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        md = markdown_path.read_text(encoding="utf-8")
    except (OSError, ValueError, UnicodeError) as exc:
        return False, [f"unreadable report: {exc}"], None
    if not isinstance(data, dict):
        return False, ["top-level JSON value must be an object"], None
    if not _nonempty_string(data.get("manuscript")):
        errors.append("manuscript must be a non-empty string")
    citations = data.get("citations")
    if not isinstance(citations, list):
        errors.append("citations must be a list")
        citations = []
    seen = set()
    for i, item in enumerate(citations):
        if not isinstance(item, dict):
            errors.append(f"citations[{i}] must be an object")
            continue
        for field in ("citation", "claim", "reference", "reason"):
            if not _nonempty_string(item.get(field)):
                errors.append(f"citations[{i}].{field} must be a non-empty string")
        identifier = item.get("citation")
        if isinstance(identifier, str):
            if identifier in seen:
                errors.append(f"citations[{i}].citation must be unique")
            seen.add(identifier)
        for field, allowed in (("reference_status", REFERENCE_STATUSES), ("support", SUPPORT_STATUSES), ("evidence_depth", EVIDENCE_DEPTHS)):
            value = item.get(field)
            if not isinstance(value, str) or value not in allowed:
                errors.append(f"citations[{i}].{field} invalid")
        if "evidence_artifact" in item and not _nonempty_string(item["evidence_artifact"]):
            errors.append(f"citations[{i}].evidence_artifact must be a non-empty string")
    summary = data.get("summary")
    if not isinstance(summary, dict):
        errors.append("summary must be an object")
    else:
        expected = {"total_citations": len(citations)}
        for label in REFERENCE_STATUSES | SUPPORT_STATUSES:
            field = "reference_status" if label in REFERENCE_STATUSES else "support"
            expected[label.lower()] = sum(isinstance(item, dict) and item.get(field) == label for item in citations)
        for key, value in expected.items():
            if type(summary.get(key)) is not int or summary[key] != value:
                errors.append(f"summary.{key} must be the integer {value}")
    if not md.lstrip().startswith("# Citation Audit Report"):
        errors.append("Markdown must begin with '# Citation Audit Report'")
    return not errors, errors, data
