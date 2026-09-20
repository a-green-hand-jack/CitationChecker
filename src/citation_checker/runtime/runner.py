"""Deterministic staging, worker lifecycle, acceptance checks, and receipts."""
from __future__ import annotations

import json
import os
import selectors
import signal
import subprocess
import sys
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from .config import DEFAULT_MODEL, DEFAULT_PROVIDER
from .sdk_tools import TOOL_SCHEMAS
from .sdk_worker import USER_PROMPT, build_system_prompt
from .staging import stage_manuscript
from .trajectory import TrajectoryRecorder, redact
from .verify import verify_report


def _run_id(manuscript: Path) -> str:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    stem = "".join(char if char.isalnum() or char in "-_" else "-" for char in manuscript.stem)[:48]
    return f"{stamp}-{stem}"


def _kill_process_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(redact(payload), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _capture(proc: subprocess.Popen, recorder: TrajectoryRecorder, response: Path, timeout: int) -> bool:
    deadline = time.monotonic() + timeout
    timed_out = False
    buffer = b""
    assert proc.stdout is not None
    with selectors.DefaultSelector() as selector, response.open("w", encoding="utf-8") as log:
        selector.register(proc.stdout, selectors.EVENT_READ)
        while selector.get_map():
            if time.monotonic() >= deadline and not timed_out:
                timed_out = True
                _kill_process_group(proc)
            for key, _ in selector.select(timeout=0.2):
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    text = line.decode("utf-8", errors="replace")
                    log.write(redact(text) + "\n")
                    log.flush()
                    recorder.record_line(text)
        if buffer:
            text = buffer.decode("utf-8", errors="replace")
            log.write(redact(text) + "\n")
            recorder.record_line(text)
    proc.wait()
    return timed_out


def run_check(manuscript: Path, *, out: Path | None, provider: str | None, model: str | None,
              thinking: str | None, timeout: int, dry_run: bool, max_steps: int = 12,
              max_tokens: int | None = 80000, disable_paper_search: bool = False,
              max_output_tokens: int = 4096) -> int:
    provider, model = provider or DEFAULT_PROVIDER, model or DEFAULT_MODEL
    package = Path(__file__).resolve().parents[1]
    run_root = Path(os.environ.get("CITATIONCHECKER_RUN_ROOT", "runs")).resolve()
    run_dir = out.resolve() if out else run_root / _run_id(manuscript)
    if run_dir.exists():
        print(f"Refusing to overwrite existing run: {run_dir}")
        return 2
    try:
        sdk_version = version("openai")
    except PackageNotFoundError:
        sdk_version = "missing"
    receipt: dict[str, Any] = {
        "schema_version": 3, "agent_backend": "openai-sdk", "sdk_version": sdk_version,
        "provider": provider, "model": model, "thinking": thinking,
        "max_steps": max_steps, "max_tokens": max_tokens or None,
        "max_output_tokens": max_output_tokens, "timeout_seconds": timeout,
        "paper_search_enabled": not disable_paper_search, "exit_code": None,
        "runner_exit_code": 2, "verified": False, "verify_errors": [],
        "stop_reason": "setup_error", "secrets_redacted": True,
        "usage_scope": "SDK requests only; cached tokens are included in prompt totals; external CLI usage excluded",
    }
    recorder = proc = None
    started = time.monotonic()
    code = 2
    try:
        if min(timeout, max_steps, max_output_tokens) < 1 or (max_tokens is not None and max_tokens < 0):
            raise ValueError("Budgets must be positive; max_tokens=0 disables the cumulative cap")
        if thinking is not None and thinking not in {"none", "minimal", "low", "medium", "high", "xhigh"}:
            raise ValueError("Unsupported reasoning_effort; omit --thinking for providers without it")
        stage_manuscript(manuscript, run_dir, package)
        system = build_system_prompt(run_dir, not disable_paper_search)
        schemas = [item for item in TOOL_SCHEMAS if not disable_paper_search or item["function"]["name"] != "retrieve_paper"]
        # The worker consumes these exact instructions. The logger uses them too.
        _write_json(run_dir / "task.json", {**receipt, "prompt": USER_PROMPT, "system_prompt": system,
                                           "tools": [item["function"]["name"] for item in schemas]})
        (run_dir / "tool-contracts.json").write_text(json.dumps(schemas, indent=2), encoding="utf-8")
        print(f"run directory: {run_dir}", flush=True)
        if dry_run:
            receipt["stop_reason"], code = "dry_run", 0
        else:
            recorder = TrajectoryRecorder(run_dir / "trajectory.jsonl", system)
            env = {**os.environ, "CITATIONCHECKER_RUN_DIR": str(run_dir),
                   "CITATIONCHECKER_PROVIDER": provider, "CITATIONCHECKER_MODEL": model}
            if provider in {"apex", "gpt-priority"} and env.get("APEX_GPT_API_KEY"):
                env.setdefault("OPENAI_API_KEY", env["APEX_GPT_API_KEY"])
            proc = subprocess.Popen([sys.executable, "-m", "citation_checker.runtime.sdk_worker"],
                cwd=run_dir / "workspace", env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
            timed_out = _capture(proc, recorder, run_dir / "response.txt", timeout)
            receipt["exit_code"] = proc.returncode
            state_file = run_dir / "state.json"
            state = json.loads(state_file.read_text()) if state_file.exists() else {}
            report = run_dir / "workspace/output/citation-report.md"
            ok, errors, data = verify_report(report)
            expected = state.get("pending_citation_ids", []) + state.get("processed_citation_ids", [])
            ids = [item.get("citation") for item in (data or {}).get("citations", []) if isinstance(item, dict)]
            aliases = state.get("citation_aliases", {})
            coverage = bool(state.get("registered")) and all(isinstance(item, str) for item in ids)
            coverage = coverage and sorted(aliases.get(item, item) for item in ids) == sorted(expected)
            if not coverage:
                errors.append("report does not cover registered citation IDs")
            ok = ok and coverage and bool(state.get("report_verified"))
            reason = state.get("stop_reason")
            if timed_out:
                reason, code = "timeout", 124
            elif reason and reason != "completed":
                code = 1 if reason == "provider_error" else 2
            elif proc.returncode != 0:
                reason, code = "provider_error", 1
            elif recorder.summary()["protocol_errors"]:
                reason, code = "protocol_error", 2
            elif not ok or reason != "completed":
                reason, code = "invalid_report", 2
            else:
                code = 0
            receipt.update(verified=bool(ok and code == 0), verify_errors=errors, stop_reason=reason,
                           state_summary=state, trajectory_summary=recorder.summary(),
                           report=str(report), trajectory=str(recorder.path))
    except KeyboardInterrupt:
        receipt["stop_reason"], code = "interrupted", 130
    except (OSError, ValueError, RuntimeError, TypeError, subprocess.TimeoutExpired) as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        code = 2
    finally:
        if proc is not None and proc.poll() is None:
            _kill_process_group(proc)
        receipt["elapsed_seconds"] = round(time.monotonic() - started, 3)
        receipt["runner_exit_code"] = code
        if recorder:
            recorder.record_stop(receipt["stop_reason"], exit_code=receipt["exit_code"],
                                 elapsed_seconds=receipt["elapsed_seconds"])
            receipt["trajectory_summary"] = recorder.summary()
            recorder.close()
        run_dir.mkdir(parents=True, exist_ok=True)
        _write_json(run_dir / "receipt.json", receipt)
    print(f"stop: {receipt['stop_reason']}; receipt: {run_dir / 'receipt.json'}", flush=True)
    return code
