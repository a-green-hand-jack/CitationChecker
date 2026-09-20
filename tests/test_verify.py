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
                "summary": {"total_citations": 1},
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
