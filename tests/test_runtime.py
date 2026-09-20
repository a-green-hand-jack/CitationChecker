import json
from pathlib import Path
from types import SimpleNamespace

from citation_checker.runtime.sdk_tools import SDKToolContext, TOOL_SCHEMAS
from citation_checker.runtime.sdk_worker import run_agent_loop
from citation_checker.runtime.trajectory import TrajectoryRecorder


def _response(content=None, calls=None, n=2):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=calls or []), finish_reason="tool_calls" if calls else "stop")], usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=n))


def test_sdk_loop_records_tool_result_and_final_response(tmp_path: Path):
    class FakeClient:
        def __init__(self): self.turn = 0
        @property
        def chat(self):
            outer = self
            class Chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        outer.turn += 1
                        if outer.turn == 1:
                            call = SimpleNamespace(id="c1", function=SimpleNamespace(name="inspect_workspace", arguments='{"operation":"list"}'))
                            return _response(calls=[call])
                        return _response(content="final")
            return Chat()
    (tmp_path / "input").mkdir(); (tmp_path / "output").mkdir()
    context = SDKToolContext(tmp_path, tmp_path / "run")
    result = run_agent_loop(FakeClient(), model="fake", system="system", prompt="audit", tools=TOOL_SCHEMAS, context=context, max_steps=3, max_tokens=100, max_output_tokens=20)
    assert result["text"] == "final"
    assert context.state["tool_counts"]["inspect_workspace"] == 1
    # One bounded repair turn follows the first unverified plain response.
    assert result["usage"]["total"] == 6
    assert result["stop_reason"] == "invalid_report"


def test_sdk_loop_malformed_arguments_is_reported(tmp_path: Path):
    class FakeClient:
        @property
        def chat(self):
            class Chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        call = SimpleNamespace(id="bad", function=SimpleNamespace(name="inspect_workspace", arguments="not-json"))
                        return _response(calls=[call])
            return Chat()
    (tmp_path / "input").mkdir(); (tmp_path / "output").mkdir()
    context = SDKToolContext(tmp_path, tmp_path / "run")
    result = run_agent_loop(FakeClient(), model="fake", system="system", prompt="audit", tools=TOOL_SCHEMAS, context=context, max_steps=1, max_tokens=10, max_output_tokens=5)
    assert result["stop_reason"] == "step_limit"


def test_trajectory_records_sdk_events_and_redacts_secrets(tmp_path: Path):
    recorder = TrajectoryRecorder(tmp_path / "trajectory.jsonl", "system")
    recorder.record_line(json.dumps({"kind": "model_response", "usage": {"total": 5}, "content": "api_key=secret"}))
    recorder.record_line("not-json")
    recorder.record_stop("timeout")
    recorder.close()
    text = (tmp_path / "trajectory.jsonl").read_text()
    assert "secret" not in text
    assert recorder.summary()["usage"]["total"] == 5
    assert recorder.summary()["protocol_errors"] == 1
