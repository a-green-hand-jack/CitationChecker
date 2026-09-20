import json
from pathlib import Path

from citation_checker.runtime.verify import verify_report


def test_verify_valid_report(tmp_path: Path):
    md = tmp_path / "citation-report.md"
    js = tmp_path / "citation-report.json"
    md.write_text("# Citation Audit Report\n\nOK\n", encoding="utf-8")
    js.write_text(
        json.dumps(
            {
                "manuscript": "paper.pdf",
                "summary": {
                    "total_citations": 1, "verified": 1, "not_found": 0,
                    "metadata_mismatch": 0, "unverifiable": 0, "supported": 1,
                    "partially_supported": 0, "unsupported": 0, "insufficient_evidence": 0,
                },
                "citations": [
                    {
                        "citation": "[1]",
                        "claim": "Example claim",
                        "reference": "Example Paper",
                        "reference_status": "VERIFIED",
                        "evidence_depth": "ABSTRACT",
                        "support": "SUPPORTED",
                        "reason": "The abstract directly states the claim.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    ok, errors, _ = verify_report(md)
    assert ok
    assert errors == []


def test_verify_rejects_non_object_and_inconsistent_summary(tmp_path: Path):
    md = tmp_path / "citation-report.md"
    md.write_text("# Citation Audit Report\n", encoding="utf-8")
    md.with_suffix(".json").write_text("[]", encoding="utf-8")
    ok, errors, _ = verify_report(md)
    assert not ok
    assert "top-level JSON value must be an object" in errors

    md.with_suffix(".json").write_text(json.dumps({
        "summary": {"total_citations": 1, "verified": 0},
        "citations": [{"citation": "[1]", "claim": "x", "reference_status": "VERIFIED", "support": "SUPPORTED", "evidence_depth": "ABSTRACT", "reason": "x"}],
    }), encoding="utf-8")
    ok, errors, _ = verify_report(md)
    assert not ok
    assert any("summary.verified" in error for error in errors)
