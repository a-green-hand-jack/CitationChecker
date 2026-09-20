"""Offline regression tests: no provider credentials or scholarly network calls."""
import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from citation_checker.runtime import runner, sdk_worker
from citation_checker.runtime.sdk_tools import SDKToolContext, TOOL_SCHEMAS
from citation_checker.runtime.sdk_worker import run_agent_loop
from citation_checker.runtime.trajectory import TrajectoryRecorder
from citation_checker.runtime.verify import verify_report


def call(name="inspect_workspace", args=None, cid="c1", raw=None):
    return {"id": cid, "type": "function", "function": {"name": name,
            "arguments": raw if raw is not None else json.dumps(args if args is not None else {"operation": "manifest"})}}


def response(calls=None, content=None, tokens=2, **extra):
    message = {"role": "assistant", "content": content, **extra}
    if calls:
        message["tool_calls"] = calls
    return {"id": "response", "choices": [{"message": message,
            "finish_reason": "tool_calls" if calls else "stop"}],
            "usage": None if tokens is None else {"prompt_tokens": tokens - 1,
                       "completion_tokens": 1, "total_tokens": tokens}}


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        item = next(self.responses)
        if isinstance(item, Exception):
            raise item
        return copy.deepcopy(item)


@pytest.fixture
def ctx(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "input").mkdir(parents=True)
    (workspace / "input/main.tex").write_text(r"Text\cite{ref_a}.")
    (workspace / "input/references.bib").write_text('@article{ref_a, year={2024}, eprint={2510.22037v2}}')
    (workspace / "input/manifest.json").write_text(json.dumps({"refchecker_target": "./input/main.tex"}))
    return SDKToolContext(workspace, tmp_path / "run")


def run(client, ctx, **kwargs):
    defaults = dict(model="fake", system="frozen system", prompt="audit", tools=ctx.schemas,
                    context=ctx, max_steps=4, max_tokens=100, max_output_tokens=20)
    defaults.update(kwargs)
    return run_agent_loop(client, **defaults)


def report():
    return {"manuscript": "main.tex", "summary": {
        "total_citations": 1, "verified": 1, "not_found": 0, "metadata_mismatch": 0,
        "unverifiable": 0, "supported": 1, "partially_supported": 0,
        "unsupported": 0, "insufficient_evidence": 0},
        "citations": [{"citation": "ref_a", "claim": "Claim", "reference": "Paper",
        "reference_status": "VERIFIED", "support": "SUPPORTED", "evidence_depth": "ABSTRACT", "reason": "Evidence"}]}


def submission():
    return {"markdown": "# Citation Audit Report\n", "report_json": report()}


def ready(ctx):
    ctx.dispatch("inspect_workspace", {"operation": "register", "citation_ids": ["ref_a"]})
    ctx.state["successful_tool_counts"]["verify_references"] = 1


def test_state_at_tail_and_exact_assistant_replay(ctx):
    first = response([call()], content="checking", reasoning_content="provider field")
    client = FakeClient([first, response(content="done")])
    run(client, ctx, max_steps=2)
    sent = client.requests[1]["messages"]
    assert sent[0] == {"role": "system", "content": "frozen system"}
    assert first["choices"][0]["message"] in sent
    assert sent[-2]["role"] == "tool" and sent[-2]["tool_call_id"] == "c1"
    state = json.loads(sent[-1]["content"].split("\n", 1)[1])
    assert state["steps"] == 2 and state["usage"]["total"] == 2
    assert state["remaining_tokens"] == 98


def test_all_actual_messages_and_schemas_are_logged(ctx, capsys):
    run(FakeClient([response([call()])]), ctx, max_steps=1)
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    request = next(e for e in events if e["kind"] == "model_request")["request"]
    assert request["messages"][0]["content"] == "frozen system"
    assert request["tools"] == ctx.schemas
    assert next(e for e in events if e["kind"] == "model_response")["response"]["choices"][0]["message"]["tool_calls"][0]["id"] == "c1"
    assert next(e for e in events if e["kind"] == "tool_result")["message"]["tool_call_id"] == "c1"


@pytest.mark.parametrize("tokens,expected", [(101, "token_limit"), (100, "token_limit"), (None, "usage_unknown")])
def test_budget_blocks_report_before_dispatch(ctx, tokens, expected):
    ready(ctx)
    client = FakeClient([response([call("write_report", submission())], tokens=tokens)])
    result = run(client, ctx)
    assert result["stop_reason"] == expected
    assert not ctx.state["report_verified"]
    assert not (ctx.output / "citation-report.json").exists()


def test_unknown_usage_with_cap_disabled_is_not_zero(ctx):
    result = run(FakeClient([response([call()], tokens=None)]), ctx, max_tokens=0, max_steps=1)
    assert result["usage"]["total"] is None
    assert not ctx.state["usage_known"]
    assert ctx.state["tool_counts"]["inspect_workspace"] == 1


def test_no_tool_claim_gets_one_bounded_repair_turn(ctx):
    ready(ctx)
    client = FakeClient([response(content="already done"), response([call("write_report", submission())])])
    result = run(client, ctx)
    assert result["stop_reason"] == "completed"
    assert any("No complete report" in m.get("content", "") for m in client.requests[1]["messages"])


def test_no_tool_invalid_report_is_not_success(ctx):
    client = FakeClient([response(content="done"), response(content="done")])
    assert run(client, ctx)["stop_reason"] == "invalid_report"
    assert len(client.requests) == 2


def test_success_ends_batch_without_executing_later_calls(ctx):
    ready(ctx)
    result = run(FakeClient([response([call("write_report", submission()), call(cid="c2")])]), ctx)
    assert result["stop_reason"] == "completed"
    assert ctx.state["tool_counts"]["inspect_workspace"] == 1  # only registration


@pytest.mark.parametrize("calls", [[call(cid="")], [call(), call()], [call(cid=None)]])
def test_missing_duplicate_ids_stop_without_execution(ctx, calls):
    result = run(FakeClient([response(calls)]), ctx)
    assert result["stop_reason"] == "protocol_error"
    assert not ctx.state["tool_counts"]


def test_malformed_arguments_have_paired_events_and_recovery(ctx, capsys):
    client = FakeClient([response([call(raw="not-json")]), response([call(cid="c2")])])
    run(client, ctx, max_steps=2)
    observation = next(m for m in client.requests[1]["messages"] if m["role"] == "tool")
    assert json.loads(observation["content"])["error"]["kind"] == "malformed_arguments"
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [e["call_id"] for e in events if e["kind"] == "tool_start"] == ["c1", "c2"]
    assert [e["call_id"] for e in events if e["kind"] == "tool_result"] == ["c1", "c2"]


def test_model_provider_error_has_unknown_usage(ctx):
    result = run(FakeClient([RuntimeError("provider failed")]), ctx)
    assert result["stop_reason"] == "provider_error" and result["usage"]["total"] is None


def test_totals_not_added_again_on_stop_and_duplicate(ctx):
    recorder = TrajectoryRecorder(ctx.run_dir / "trajectory.jsonl", "system")
    for step, tokens in [(1, 5), (2, 7), (2, 7)]:
        recorder.record_line(json.dumps({"kind": "model_response", "step": step, "usage": {"total": tokens}}))
    recorder.record_line(json.dumps({"kind": "stop", "usage": {"total": 12}}))
    assert recorder.summary()["usage"]["total"] == 12
    recorder.close()


def test_missing_usage_stays_unknown_in_receipt(ctx):
    recorder = TrajectoryRecorder(ctx.run_dir / "trajectory.jsonl", "system")
    recorder.record_line(json.dumps({"kind": "model_response", "step": 1, "usage": None}))
    assert recorder.summary()["usage"]["total"] is None
    assert not recorder.summary()["usage_known"]
    recorder.close()


@pytest.mark.parametrize("name,args", [
    ("inspect_workspace", {"operation": "read", "path": "input/main.tex", "max_chars": 100000}),
    ("inspect_workspace", {"operation": "read", "offset": -1}),
    ("inspect_workspace", {"operation": "read", "offset": True}),
    ("verify_references", {"timeout_seconds": 0}),
    ("verify_references", {"timeout_seconds": 181}),
    ("retrieve_paper", {"operation": "search", "query": "paper", "max_results": 99}),
    ("retrieve_paper", {"operation": "read", "source": "shell", "paper_id": "id"}),
    ("retrieve_paper", {"operation": "search", "query": "--help"}),
    ("inspect_workspace", {"operation": "manifest", "extra": True}),
])
def test_schema_validation_blocks_bad_arguments(ctx, name, args, monkeypatch):
    monkeypatch.setattr(ctx, "external", lambda *a: pytest.fail("must not execute"))
    result = ctx.dispatch(name, args)
    assert not result["ok"] and result["error"]["kind"] == "invalid_input"


def test_exported_contracts_and_ablation_gate(ctx):
    disabled = SDKToolContext(ctx.workspace, ctx.run_dir / "disabled", False)
    names = {s["function"]["name"] for s in disabled.schemas}
    assert "retrieve_paper" not in names
    for schema in TOOL_SCHEMAS:
        Draft202012Validator.check_schema(schema["function"]["parameters"])
    assert not disabled.dispatch("retrieve_paper", {"operation": "search", "query": "paper"})["ok"]


def test_read_blocks_path_escape_and_symlink(ctx, tmp_path):
    outside = tmp_path / "private.txt"
    outside.write_text("private")
    (ctx.workspace / "input/link").symlink_to(outside)
    for path in (str(outside), "../private.txt", "input/link"):
        assert not ctx.dispatch("inspect_workspace", {"operation": "read", "path": path})["ok"]


def test_retry_circuit_blocks_identical_deterministic_failures(ctx):
    args = {"operation": "read", "path": "input/missing"}
    assert not ctx.dispatch("inspect_workspace", args)["ok"]
    result = ctx.dispatch("inspect_workspace", args)
    assert result["error"]["kind"] == "circuit_open"
    assert ctx.state["stop_reason"] == "tool_failure"


def test_fallback_checks_original_bib_never_arxiv(ctx, monkeypatch):
    targets = []
    original = (ctx.workspace / "input/references.bib").read_bytes()
    def external(command, args, timeout):
        target = Path(args[args.index("--paper") + 1]); targets.append(target)
        path = ctx.workspace / args[args.index("--report-file") + 1]
        path.write_text(json.dumps({"summary": {"total_references_processed": int(target.suffix == ".bib")}}))
        return {"ok": False, "exit_code": 1, "error": {"kind": "nonzero_exit"}}
    monkeypatch.setattr(ctx, "external", external)
    result = ctx.dispatch("verify_references", {})
    assert result["ok"] and result["checked_target"].endswith("references.bib")
    assert [p.suffix for p in targets] == [".tex", ".bib"]
    assert (ctx.workspace / "input/references.bib").read_bytes() == original
    assert ctx.state["successful_tool_counts"]["verify_references"] == 1


def test_ambiguous_bibliographies_do_not_choose_first(ctx, monkeypatch):
    (ctx.workspace / "input/second.bib").write_text("another bibliography")
    calls = []
    def failing(target, timeout):
        calls.append(target)
        return {"ok": False, "checked_target": "./input/main.tex", "error": {"kind": "invalid_report"}}
    monkeypatch.setattr(ctx, "_refcheck", failing)
    result = ctx.dispatch("verify_references", {})
    assert not result["ok"] and len(calls) == 1
    assert "Several .bib" in result["error"]["next_action"]


def test_partial_report_after_timeout_is_not_success(ctx, monkeypatch):
    def external(command, args, timeout):
        (ctx.workspace / args[args.index("--report-file") + 1]).write_text(json.dumps({"summary": {"total_references_processed": 1}}))
        return {"ok": False, "error": {"kind": "timeout"}}
    monkeypatch.setattr(ctx, "external", external)
    result = ctx.dispatch("verify_references", {})
    assert not result["ok"] and not ctx.state["successful_tool_counts"]


def test_read_evidence_honors_max_chars_and_keeps_artifact(ctx, monkeypatch):
    ready(ctx)
    monkeypatch.setattr(ctx, "external", lambda *a: {"ok": True, "_stdout": "a" * 3000,
                        "_stderr": "", "artifact_path": "./output/evidence.txt"})
    result = ctx.dispatch("retrieve_paper", {"operation": "read", "source": "arxiv", "paper_id": "1706.03762", "max_chars": 500})
    assert len(result["observation"]) == 500 and result["truncated"]
    assert result["artifact_path"] and "_stdout" not in result


def test_empty_search_with_errors_is_not_success(ctx, monkeypatch):
    ready(ctx)
    monkeypatch.setattr(ctx, "external", lambda *a: {"ok": True, "_stdout": json.dumps({"papers": [], "errors": {"arxiv": "503"}})})
    assert ctx.dispatch("retrieve_paper", {"operation": "search", "query": "paper"})["error"]["kind"] == "network_error"


def test_report_requires_success_not_attempt_count(ctx):
    ctx.dispatch("inspect_workspace", {"operation": "register", "citation_ids": ["ref_a"]})
    ctx.state["tool_counts"]["verify_references"] = 1
    assert not ctx.dispatch("write_report", submission())["ok"]


@pytest.mark.parametrize("mutate", [
    lambda r: r["citations"][0].update(support=[]),
    lambda r: r["summary"].update(total_citations=True),
    lambda r: r["citations"][0].update(citation=[]),
    lambda r: r["citations"][0].update(reference=""),
])
def test_bad_report_types_return_errors_not_crash(ctx, mutate):
    data = report(); mutate(data)
    md = ctx.output / "citation-report.md"
    md.write_text("# Citation Audit Report\n")
    md.with_suffix(".json").write_text(json.dumps(data))
    assert not verify_report(md)[0]


def test_secrets_redacted_at_all_persistence_points(ctx, monkeypatch, capsys):
    monkeypatch.setenv("EXAMPLE_API_KEY", "super-secret-123")
    ctx.state["last_error"] = {"message": "super-secret-123"}; ctx.save()
    artifact = ctx.artifact("err", "super-secret-123")
    sdk_worker.emit("event", text="super-secret-123")
    assert "super-secret-123" not in (ctx.run_dir / "state.json").read_text()
    assert "super-secret-123" not in (ctx.workspace / artifact).read_text()
    assert "super-secret-123" not in capsys.readouterr().out


def test_external_timeout_and_missing_executable_are_actionable(ctx):
    result = ctx.external(sys.executable, ["-c", "import time; time.sleep(5)"], 0.1)
    assert result["error"]["kind"] == "timeout" and ctx.active_child is None
    assert ctx.external("/definitely/missing/executable", [], 1)["error"]["kind"] == "missing_executable"


def test_dry_run_freezes_actual_system_and_contracts(tmp_path):
    source = tmp_path / "main.tex"; source.write_text(r"text\cite{a}")
    out = tmp_path / "dry"
    assert runner.run_check(source, out=out, provider="fake", model="fake", thinking=None,
                            timeout=1, dry_run=True, disable_paper_search=True) == 0
    task = json.loads((out / "task.json").read_text())
    assert task["system_prompt"] == sdk_worker.build_system_prompt(out, False)
    assert "retrieve_paper" not in task["tools"]
    assert "Paper retrieval is disabled" in task["system_prompt"]


def test_two_scholarly_tools_complete_a_multistep_loop(ctx, monkeypatch, capsys):
    monkeypatch.setattr(ctx, "_refcheck", lambda *a: {"ok": True, "checked_target": "./input/main.tex"})
    monkeypatch.setattr(ctx, "external", lambda *a: {"ok": True, "_stdout": json.dumps({"papers": [{"title": "Paper"}]})})
    client = FakeClient([
        response([call("inspect_workspace", {"operation": "register", "citation_ids": ["ref_a"]}, cid="r")]),
        response([call("verify_references", {}, cid="v")]),
        response([call("retrieve_paper", {"operation": "search", "query": "Paper"}, cid="s")]),
        response([call("write_report", submission(), cid="w")]),
    ])
    assert run(client, ctx)["stop_reason"] == "completed"
    assert ctx.state["successful_tool_counts"]["verify_references"] == 1
    assert ctx.state["successful_tool_counts"]["retrieve_paper"] == 1
    recorder = TrajectoryRecorder(ctx.run_dir / "trajectory.jsonl", "frozen system")
    for line in capsys.readouterr().out.splitlines():
        recorder.record_line(line)
    assert recorder.summary()["usage"]["total"] == 8
    assert recorder.summary()["protocol_errors"] == 0
    recorder.close()


@pytest.mark.parametrize("invalid", [False, True])
def test_runner_rechecks_completion_independently(tmp_path, monkeypatch, invalid):
    fake = tmp_path / "fake_worker.py"
    fake.write_text('''import json, os
from pathlib import Path
root = Path(os.environ['CITATIONCHECKER_RUN_DIR'])
out = root / 'workspace/output'
(out / 'citation-report.md').write_text('# Citation Audit Report\\n')
data = ''' + repr(report()) + '''
''' + ("data['summary']['total_citations'] = 99\n" if invalid else "") + '''
(out / 'citation-report.json').write_text(json.dumps(data))
(root / 'state.json').write_text(json.dumps({'registered': True, 'processed_citation_ids': ['ref_a'], 'pending_citation_ids': [], 'report_verified': True, 'stop_reason': 'completed'}))
print(json.dumps({'kind': 'model_response', 'step': 1, 'usage': {'total': 5}}))
print(json.dumps({'kind': 'stop', 'usage_total': {'total': 5}}))
''')
    actual_popen = subprocess.Popen
    def spawn(args, **kwargs):
        return actual_popen([sys.executable, str(fake)], **kwargs)
    monkeypatch.setattr(runner.subprocess, "Popen", spawn)
    source = tmp_path / "main.tex"; source.write_text(r"text\cite{ref_a}")
    out = tmp_path / "run"
    code = runner.run_check(source, out=out, provider="fake", model="fake", thinking=None, timeout=10, dry_run=False)
    receipt = json.loads((out / "receipt.json").read_text())
    assert code == (2 if invalid else 0)
    assert receipt["verified"] is not invalid
    assert receipt["trajectory_summary"]["usage"]["total"] == 5
    first = json.loads((out / "trajectory.jsonl").read_text().splitlines()[0])
    assert first["content"] == json.loads((out / "task.json").read_text())["system_prompt"]


def test_runner_timeout_has_non_success_receipt(tmp_path, monkeypatch):
    actual_popen = subprocess.Popen
    monkeypatch.setattr(runner.subprocess, "Popen", lambda args, **kwargs:
                        actual_popen([sys.executable, "-c", "import time; time.sleep(5)"], **kwargs))
    source = tmp_path / "main.tex"; source.write_text(r"text\cite{a}")
    out = tmp_path / "timeout"
    assert runner.run_check(source, out=out, provider="fake", model="fake", thinking=None, timeout=1, dry_run=False) == 124
    receipt = json.loads((out / "receipt.json").read_text())
    assert receipt["stop_reason"] == "timeout" and not receipt["verified"]


def test_thinking_is_forwarded_not_silently_discarded(ctx):
    client = FakeClient([response(content="done")])
    run(client, ctx, max_steps=1, thinking="medium")
    assert client.requests[0]["reasoning_effort"] == "medium"
