"""Typed, bounded adapters around existing scholarly CLIs, not new verifiers."""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from .sdk_protocol import error_payload
from .trajectory import redact
from .verify import verify_report

MAX_CHARS = 12000
MAX_CAPTURE_BYTES = 5_000_000


def _bounded(text: str, limit: int = 6000) -> dict[str, Any]:
    limit = max(1, min(limit, MAX_CHARS))
    return {"observation": text[:limit], "truncated": len(text) > limit}


def _string(max_length: int = 4096) -> dict:
    return {"type": "string", "minLength": 1, "maxLength": max_length}


def _integer(minimum: int, maximum: int) -> dict:
    return {"type": "integer", "minimum": minimum, "maximum": maximum}


def _tool(name: str, description: str, properties: dict, required: tuple = ()) -> dict:
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties,
                           "required": list(required), "additionalProperties": False}}}


TOOL_SCHEMAS = [
    _tool("inspect_workspace", "Start with manifest; read staged files in bounded windows and register every citation-context ID. No shell or network.", {
        "operation": {"type": "string", "enum": ["manifest", "list", "read", "register"]},
        "path": _string(), "offset": _integer(0, MAX_CAPTURE_BYTES),
        "max_chars": _integer(500, MAX_CHARS),
        "citation_ids": {"type": "array", "minItems": 1, "maxItems": 1000,
                         "uniqueItems": True, "items": _string(128)},
    }, ("operation",)),
    _tool("verify_references", "Check authenticity and metadata with RefChecker on a staged manuscript or .bib. On TeX extraction failure only a local bibliography may be retried, never the cited paper's arXiv ID.", {
        "target": _string(), "timeout_seconds": _integer(5, 180),
    }),
    _tool("retrieve_paper", "After identifying a credible reference, search/read/download evidence with paper-search. Returns bounded observations and an artifact path. Missing full text is not proof of non-support.", {
        "operation": {"type": "string", "enum": ["search", "read", "download"]},
        "query": {**_string(2000), "pattern": r"^(?!-).*\S"},
        "source": {"type": "string", "enum": ["semantic", "crossref", "openalex", "arxiv"]},
        "paper_id": {**_string(256), "pattern": r"^(?!-).*\S"},
        "max_results": _integer(1, 5), "max_chars": _integer(500, MAX_CHARS),
        "timeout_seconds": _integer(5, 180),
    }, ("operation",)),
    _tool("write_report", "Submit both reports after a successful RefChecker observation. citations[].citation must be the exact registered citation-context ID, once per registered ID. Checks structure, counts, and registered coverage, not scientific truth. Repair any validation errors.", {
        "markdown": _string(500000),
        "report_json": {"type": "object", "properties": {
            "manuscript": _string(), "summary": {"type": "object"},
            "citations": {"type": "array", "maxItems": 1000, "items": {"type": "object"}},
        }, "required": ["manuscript", "summary", "citations"]},
    }, ("markdown", "report_json")),
]


class SDKToolContext:
    def __init__(self, workspace: Path, run_dir: Path, search_enabled: bool = True) -> None:
        self.workspace, self.run_dir = workspace.resolve(), run_dir.resolve()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.output = self.workspace / "output"
        self.output.mkdir(parents=True, exist_ok=True)
        self.search_enabled = search_enabled
        self.schemas = [item for item in TOOL_SCHEMAS
                        if search_enabled or item["function"]["name"] != "retrieve_paper"]
        self.validators = {item["function"]["name"]: Draft202012Validator(item["function"]["parameters"])
                           for item in self.schemas}
        self.state: dict[str, Any] = {
            "schema_version": 3, "steps": 0, "processed_citation_ids": [],
            "pending_citation_ids": [], "citation_aliases": {}, "registered": False,
            "tool_counts": {}, "successful_tool_counts": {}, "artifacts": [],
            "errors": [], "last_error": None, "usage": {"total": 0}, "usage_known": True,
            "max_steps": 12, "max_tokens": 80000, "max_output_tokens": 4096,
            "stop_reason": None, "report_verified": False, "final_assistant_stop": None,
        }
        self.failure_counts: dict[str, int] = {}
        self.artifact_index = 0
        self.active_child: subprocess.Popen | None = None
        (run_dir / "tool-contracts.json").write_text(json.dumps(self.schemas, indent=2), encoding="utf-8")
        self.save()

    def save(self) -> None:
        temporary = self.run_dir / "state.json.tmp"
        temporary.write_text(json.dumps(redact(self.state), indent=2), encoding="utf-8")
        temporary.replace(self.run_dir / "state.json")

    def snapshot(self) -> dict[str, Any]:
        total = self.state["usage"].get("total")
        cap = self.state["max_tokens"]
        return {"steps": self.state["steps"], "remaining_steps": max(0, self.state["max_steps"] - self.state["steps"]),
                "registered": self.state["registered"],
                "pending_count": len(self.state["pending_citation_ids"]),
                "pending_citation_ids": self.state["pending_citation_ids"][:50],
                "processed_count": len(self.state["processed_citation_ids"]),
                "ids_truncated": len(self.state["pending_citation_ids"]) > 50,
                "tool_counts": dict(self.state["tool_counts"]), "usage": dict(self.state["usage"]),
                "usage_known": self.state["usage_known"],
                "remaining_tokens": None if total is None or cap is None else max(0, cap - total),
                "last_error": self.state["last_error"], "report_verified": self.state["report_verified"]}

    def safe_path(self, value: str, roots: tuple[str, ...] = ("input", "output")) -> Path:
        if not isinstance(value, str) or not value or Path(value).is_absolute():
            raise ValueError("Use a relative staged workspace path")
        target = (self.workspace / value).resolve()
        try:
            rel = target.relative_to(self.workspace)
        except ValueError as exc:
            raise ValueError("Path outside allowed staged files") from exc
        if not rel.parts or rel.parts[0] not in roots or any(part.startswith(".") for part in rel.parts):
            raise ValueError("Path outside allowed staged files")
        return target

    def artifact(self, prefix: str, text: str) -> str:
        (self.output / "tool-artifacts").mkdir(parents=True, exist_ok=True)
        self.artifact_index += 1
        rel = f"./output/tool-artifacts/{prefix}-{self.artifact_index:03d}.txt"
        (self.workspace / rel).write_text(redact(text)[:MAX_CAPTURE_BYTES], encoding="utf-8")
        self.state["artifacts"].append(rel)
        return rel

    def cancel_external(self) -> None:
        child = self.active_child
        if child is None:
            return
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            child.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait()
        self.active_child = None

    def external(self, command: str, args: list[str], timeout: float) -> dict[str, Any]:
        """Use files instead of unbounded in-memory subprocess output buffers."""
        started = time.monotonic()
        reason = None
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            try:
                self.active_child = subprocess.Popen([command, *args], cwd=self.workspace,
                    stdout=stdout_file, stderr=stderr_file, stdin=subprocess.DEVNULL,
                    shell=False, start_new_session=True)
            except OSError as exc:
                return {**error_payload("missing_executable", str(exc)), "exit_code": None,
                        "latency_ms": round((time.monotonic() - started) * 1000, 3)}
            child = self.active_child
            try:
                while child.poll() is None:
                    if time.monotonic() - started >= timeout:
                        reason = "timeout"
                        break
                    if max(os.fstat(stdout_file.fileno()).st_size, os.fstat(stderr_file.fileno()).st_size) > MAX_CAPTURE_BYTES:
                        reason = "output_limit"
                        break
                    time.sleep(0.02)
            finally:
                self.cancel_external()  # Reap descendants even when the parent exited.
            captures = []
            for stream in (stdout_file, stderr_file):
                stream.seek(0)
                raw = stream.read(MAX_CAPTURE_BYTES + 1)
                if len(raw) > MAX_CAPTURE_BYTES:
                    reason = reason or "output_limit"
                captures.append(raw[:MAX_CAPTURE_BYTES].decode("utf-8", errors="replace"))
        stdout, stderr = captures
        text = "\n".join(item for item in captures if item)
        payload = {"ok": child.returncode == 0 and reason is None, "exit_code": child.returncode,
                   "latency_ms": round((time.monotonic() - started) * 1000, 3),
                   "artifact_path": self.artifact(Path(command).name.replace("-", "_"), text),
                   **_bounded(text), "_stdout": stdout, "_stderr": stderr}
        if not payload["ok"]:
            transient = reason is None and bool(re.search(r"\b(429|502|503|504)\b|rate.limit|temporar", text, re.I))
            error = error_payload(reason or "nonzero_exit", reason or f"Command exited {child.returncode}", transient)
            if reason == "timeout":
                # A slow scholarly CLI is a retry signal, not a deterministic dead
                # end: the fix is a larger timeout, not abandoning the run.
                error["error"].update(retryable=True, next_action=(
                    "Retry once with a larger timeout_seconds (up to 180), or use one explicit staged .bib target."
                    " Do not repeat the identical call unchanged."))
            payload.update(error)
        return payload

    def failure(self, name: str, args: Any, result: dict) -> dict:
        key = f"{name}:{json.dumps(args, sort_keys=True)}"
        detail = result.get("error", {})
        self.failure_counts[key] = self.failure_counts.get(key, 0) + (1 if detail.get("retryable") else 2)
        self.state["last_error"] = {"tool": name, **detail}
        self.state["errors"].append(self.state["last_error"])
        if self.failure_counts[key] > 2:
            self.state["stop_reason"] = "tool_failure"
        self.save()
        return redact(result)

    def dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if self.state.get("stop_reason"):
            return error_payload("run_stopped", str(self.state["stop_reason"]))
        self.state["tool_counts"][name] = self.state["tool_counts"].get(name, 0) + 1
        key = f"{name}:{json.dumps(args, sort_keys=True)}"
        if self.failure_counts.get(key, 0) >= 2:
            self.state["stop_reason"] = "tool_failure"
            self.save()
            return error_payload("circuit_open", "Repeated identical failed request; not executed")
        try:
            if name not in self.validators:
                raise ValueError("Tool is not enabled for this run")
            self.validators[name].validate(args)
            result = getattr(self, f"tool_{name}")(args)
        except (ValidationError, ValueError, OSError, TypeError) as exc:
            result = error_payload("invalid_input", str(exc)[:2000])
        if not result.get("ok"):
            result = self.failure(name, args, result)
        else:
            counts = self.state["successful_tool_counts"]
            counts[name] = counts.get(name, 0) + 1
        # Large manifests/registrations also get bounded envelopes, not just text reads.
        result = redact(result)
        encoded = json.dumps(result, ensure_ascii=False)
        if len(encoded) > 16000:
            result = {"ok": result.get("ok", False), "artifact_path": self.artifact("tool-result", encoded),
                      **_bounded(encoded)}
        self.save()
        return result

    def tool_inspect_workspace(self, p: dict[str, Any]) -> dict[str, Any]:
        op = p["operation"]
        if op == "register":
            ids = p.get("citation_ids")
            if not ids or any(not item.strip() for item in ids):
                raise ValueError("Register at least one nonempty citation-context ID")
            self.state["registered"] = True
            pending = self.state["pending_citation_ids"]
            pending.extend(item for item in ids if item not in pending and item not in self.state["processed_citation_ids"])
            return {"ok": True, "pending_count": len(pending), "pending_citation_ids": pending[:50]}
        if op == "read" and "path" not in p:
            raise ValueError("read requires a staged path")
        target = self.safe_path("input/manifest.json" if op == "manifest" else p.get("path", "input"))
        if op == "list":
            return {"ok": True, "entries": sorted(item.name for item in target.iterdir())[:100]}
        if op == "manifest":
            return {"ok": True, "manifest": json.loads(target.read_text(encoding="utf-8"))}
        offset, limit = p.get("offset", 0), p.get("max_chars", 6000)
        with target.open(encoding="utf-8", errors="replace") as stream:
            stream.read(offset)
            text = stream.read(limit + 1)
        return {"ok": True, "path": p["path"], "offset": offset, **_bounded(text, limit)}

    def _refcheck(self, target: Path, timeout: int) -> dict:
        report = f"./output/refchecker-{self.artifact_index + 1}.json"
        report_file = self.workspace / report
        report_file.unlink(missing_ok=True)
        args = ["--paper", str(target), "--report-file", report, "--report-format", "json"]
        if os.environ.get("CITATIONCHECKER_PROVIDER") in {"apex", "gpt-priority"} and os.environ.get("OPENAI_API_KEY"):
            args += ["--llm-provider", "openai", "--llm-model", os.environ["CITATIONCHECKER_MODEL"],
                     "--llm-endpoint", os.environ.get("CITATIONCHECKER_BASE_URL") or os.environ.get("APEX_BASE_URL", "https://api.apexin.ai/v1")]
        result = self.external("academic-refchecker", args, timeout)
        fatal = result.get("error", {}).get("kind") in {"timeout", "output_limit", "missing_executable"}
        try:
            parsed = json.loads(report_file.read_text(encoding="utf-8"))
            count = parsed.get("summary", {}).get("total_references_processed")
            if type(count) is not int or count < 1:
                raise ValueError("RefChecker processed no references")
            if not fatal:
                result["ok"] = True  # Nonzero exit may mean bibliography findings.
                result.pop("error", None)
                result["report_path"] = report
        except (OSError, ValueError, AttributeError) as exc:
            if not fatal:
                result.update(error_payload("invalid_report", str(exc)))
        result["checked_target"] = "./" + target.relative_to(self.workspace).as_posix()
        result.pop("_stdout", None)
        result.pop("_stderr", None)
        return result

    def tool_verify_references(self, p: dict[str, Any]) -> dict[str, Any]:
        if not self.state["registered"]:
            ids = []
            for tex in (self.workspace / "input").rglob("*.tex"):
                text = self.safe_path(str(tex.relative_to(self.workspace)), ("input",)).read_text(encoding="utf-8", errors="replace")
                text = re.sub(r"(?<!\\)%[^\n]*", "", text)
                for group in re.findall(r"\\cite[a-zA-Z*]*\s*(?:\[[^]]*\]\s*){0,2}\{([^}]+)\}", text):
                    ids.extend(item.strip() for item in group.split(",") if item.strip())
            ids = list(dict.fromkeys(ids))
            if not ids or len(ids) > 1000:
                raise ValueError("Register citation-context IDs first")
            self.state.update(registered=True, pending_citation_ids=ids, auto_registered=True)
        manifest = json.loads((self.workspace / "input/manifest.json").read_text(encoding="utf-8"))
        target = self.safe_path(p.get("target") or manifest["refchecker_target"], ("input",))
        if target.suffix.lower() not in {".tex", ".bib", ".pdf", ".md", ".txt"}:
            raise ValueError("Unsupported RefChecker input")
        result = self._refcheck(target, p.get("timeout_seconds", 180))
        if not result["ok"] and target.suffix.lower() == ".tex" and result.get("error", {}).get("kind") not in {"timeout", "missing_executable", "output_limit"}:
            bibs = sorted(target.parent.glob("*.bib"))
            if len(bibs) == 1:
                # Preserve every original bibliographic field, including wrong years.
                # NEVER substitute a cited arXiv ID: that audits a different paper.
                bib = self.safe_path(str(bibs[0].relative_to(self.workspace)), ("input",))
                fallback = self._refcheck(bib, p.get("timeout_seconds", 180))
                fallback.update(fallback_from=result["checked_target"], primary_result=result)
                result = fallback
            elif len(bibs) > 1:
                result["error"]["next_action"] = "Several .bib files exist. Choose the intended staged bibliography explicitly; no arbitrary one was selected."
        return result

    def tool_retrieve_paper(self, p: dict[str, Any]) -> dict[str, Any]:
        if not self.search_enabled or not self.state["registered"]:
            raise ValueError("Retrieval must be enabled and citation IDs registered")
        op = p["operation"]
        if op == "search":
            if not p.get("query", "").strip():
                raise ValueError("search requires a nonempty query")
            args = ["search", p["query"], "-n", str(p.get("max_results", 3)), "-s", p.get("source", "semantic,crossref,openalex,arxiv")]
        elif p.get("source") and p.get("paper_id"):
            args = [op, p["source"], p["paper_id"], "-o", "./output/papers"]
        else:
            raise ValueError("read/download require source and paper_id")
        result = self.external("paper-search", args, p.get("timeout_seconds", 120))
        text = "\n".join(item for item in (result.get("_stdout", ""), result.get("_stderr", "")) if item)
        result.update(_bounded(text, p.get("max_chars", 6000)))
        if result.get("ok") and op == "search":
            try:
                parsed = json.loads(result.get("_stdout", ""))
                if not isinstance(parsed.get("papers"), list):
                    raise ValueError("Search JSON missing papers list")
                if not parsed["papers"] and parsed.get("errors"):
                    result.update(error_payload("network_error", json.dumps(parsed["errors"]), True))
            except (ValueError, AttributeError) as exc:
                result.update(error_payload("bad_json", str(exc)))
        result.pop("_stdout", None)
        result.pop("_stderr", None)
        return result

    def tool_write_report(self, p: dict[str, Any]) -> dict[str, Any]:
        if not self.state["registered"]:
            raise ValueError("Register citation-context IDs first")
        if not self.state["successful_tool_counts"].get("verify_references"):
            return error_payload("invalid_report", "Report requires a successful RefChecker observation, not just an attempted call")
        report = p["report_json"]
        (self.output / "citation-report.md").write_text(redact(p["markdown"]), encoding="utf-8")
        (self.output / "citation-report.json").write_text(json.dumps(redact(report), indent=2), encoding="utf-8")
        ok, errors, _ = verify_report(self.output / "citation-report.md")
        ids = [item.get("citation") for item in report.get("citations", []) if isinstance(item, dict)]
        expected = self.state["pending_citation_ids"] + self.state["processed_citation_ids"]
        aliases = {item: item for item in expected} | {f"[{i + 1}]": item for i, item in enumerate(expected)}
        aliases.update({f"\\{cmd}{{{item}}}": item for cmd in ("cite", "citep") for item in expected})
        normalized = [aliases.get(item, item) for item in ids if isinstance(item, str)]
        coverage = len(normalized) == len(ids) and sorted(normalized) == sorted(expected)
        if not ok or not coverage:
            return error_payload("invalid_report", json.dumps({
                "errors": errors,
                "missing": [item for item in expected if item not in normalized],
                "hint": "Set citations[].citation to the exact registered context ID; every registered ID must appear exactly once."}))
        self.state.update(citation_aliases=aliases, processed_citation_ids=expected,
                          pending_citation_ids=[], report_verified=True, stop_reason="completed")
        return {"ok": True, "markdown_path": "./output/citation-report.md",
                "json_path": "./output/citation-report.json", "total_citations": len(ids)}
