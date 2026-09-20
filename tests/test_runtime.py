from __future__ import annotations

import json
import os
import stat
import textwrap
from pathlib import Path

from citation_checker.runtime.runner import run_check
from citation_checker.runtime.trajectory import TrajectoryRecorder


VALID_JSON = {
    "manuscript": "main.tex",
    "summary": {
        "total_citations": 1, "verified": 1, "not_found": 0, "metadata_mismatch": 0,
        "unverifiable": 0, "supported": 1, "partially_supported": 0,
        "unsupported": 0, "insufficient_evidence": 0,
    },
    "citations": [{
        "citation": "ref_a", "claim": "A", "reference": "B", "reference_status": "VERIFIED",
        "evidence_depth": "ABSTRACT", "support": "SUPPORTED", "reason": "C",
    }],
}


def fake_pi(tmp_path: Path, *, sleep: bool = False) -> Path:
    script = tmp_path / "fake-pi.py"
    script.write_text(textwrap.dedent(f"""
        #!/usr/bin/env python3
        import json, os, pathlib, sys, time
        if '--version' in sys.argv:
            print('0.85.1'); raise SystemExit(0)
        if {sleep!r}:
            time.sleep(4)
        root = pathlib.Path(os.environ['CITATIONCHECKER_RUN_DIR'])
        out = pathlib.Path.cwd() / 'output'; out.mkdir(exist_ok=True)
        (out / 'citation-report.md').write_text('# Citation Audit Report\\n\\nref_a\\n')
        (out / 'citation-report.json').write_text(json.dumps({json.dumps(VALID_JSON)}))
        state = {{'registered': True, 'processed_citation_ids': ['ref_a'], 'pending_citation_ids': [], 'report_verified': True, 'stop_reason': None}}
        (root / 'state.json').write_text(json.dumps(state))
        events = [
          {{'type':'session','version':3}}, {{'type':'turn_start'}},
          {{'type':'message_end','message':{{'role':'assistant','responseId':'r1','stopReason':'toolUse','usage':{{'input':3,'output':2,'totalTokens':5}}}}}},
          {{'type':'tool_execution_start','toolCallId':'c1','toolName':'verify_references'}},
          {{'type':'tool_execution_end','toolCallId':'c1','toolName':'verify_references','isError':False}},
          {{'type':'turn_end'}}, {{'type':'agent_settled'}}
        ]
        for event in events: print(json.dumps(event), flush=True)
    """).lstrip())
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def source(tmp_path: Path) -> Path:
    path = tmp_path / "main.tex"
    path.write_text("\\documentclass{article}\\begin{document}Hi\\end{document}\\n")
    return path


def test_runner_records_replayable_trajectory_and_completion(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CITATIONCHECKER_PI", str(fake_pi(tmp_path)))
    out = tmp_path / "run"
    assert run_check(source(tmp_path), out=out, provider="fake", model="fake", thinking=None, timeout=10, dry_run=False, max_steps=2, max_tokens=100) == 0
    receipt = json.loads((out / "receipt.json").read_text())
    assert receipt["verified"] is True
    assert receipt["stop_reason"] == "completed"
    trajectory = [json.loads(line) for line in (out / "trajectory.jsonl").read_text().splitlines()]
    assert trajectory[0]["kind"] == "system"
    assert any(item["kind"] == "tool_start" and item["toolCallId"] == "c1" for item in trajectory)
    assert receipt["trajectory_summary"]["usage"]["total"] == 5


def test_runner_kills_timed_out_provider(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CITATIONCHECKER_PI", str(fake_pi(tmp_path, sleep=True)))
    out = tmp_path / "timeout"
    assert run_check(source(tmp_path), out=out, provider="fake", model="fake", thinking=None, timeout=1, dry_run=False) == 124
    receipt = json.loads((out / "receipt.json").read_text())
    assert receipt["stop_reason"] == "timeout"
    assert receipt["runner_exit_code"] == 124


def test_trajectory_records_protocol_errors(tmp_path: Path):
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl", "system")
    recorder.record_line("not-json")
    summary = recorder.summary()
    recorder.close()
    assert summary["protocol_errors"] == 1
