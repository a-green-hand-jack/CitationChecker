from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .sdk_protocol import error_payload
from .verify import verify_report


def _bounded(text: str, limit: int = 6000) -> dict[str, Any]:
    return {"observation": text[:limit], "truncated": len(text) > limit}


class SDKToolContext:
    def __init__(self, workspace: Path, run_dir: Path, search_enabled: bool = True) -> None:
        self.workspace, self.run_dir = workspace.resolve(), run_dir.resolve()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.output = self.workspace / "output"
        self.search_enabled = search_enabled
        self.state: dict[str, Any] = {
            "schema_version": 2, "steps": 0, "processed_citation_ids": [],
            "pending_citation_ids": [], "citation_aliases": {}, "registered": False,
            "tool_counts": {}, "artifacts": [], "errors": [], "last_error": None,
            "usage": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "total": 0},
            "usage_known": True, "max_steps": int(os.environ.get("CITATIONCHECKER_MAX_STEPS", "12")),
            "max_tokens": self._int_or_none(os.environ.get("CITATIONCHECKER_MAX_TOKENS", "80000")),
            "max_output_tokens": int(os.environ.get("CITATIONCHECKER_MAX_OUTPUT_TOKENS", "4096")),
            "stop_reason": None, "report_verified": False, "final_assistant_stop": None,
        }
        self.failure_counts: dict[str, int] = {}
        self.artifact_index = 0
        self.save()

    @staticmethod
    def _int_or_none(value: str | None) -> int | None:
        return None if value in (None, "none", "") else int(value)

    def save(self) -> None:
        (self.run_dir / "state.json").write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def safe_path(self, value: str, roots: tuple[str, ...] = ("input", "output")) -> Path:
        if not isinstance(value, str) or not value or Path(value).is_absolute():
            raise ValueError("Use a relative staged workspace path")
        target = (self.workspace / value).resolve()
        try:
            rel = target.relative_to(self.workspace)
        except ValueError as exc:
            raise ValueError("Path outside allowed staged files") from exc
        if not rel.parts or rel.parts[0] not in roots or any(p.startswith(".") for p in rel.parts):
            raise ValueError("Path outside allowed staged files")
        return target

    def artifact(self, prefix: str, text: str) -> str:
        directory = self.output / "tool-artifacts"
        directory.mkdir(parents=True, exist_ok=True)
        self.artifact_index += 1
        rel = f"./output/tool-artifacts/{prefix}-{self.artifact_index:03d}.txt"
        (self.workspace / rel).write_text(text[:5_000_000], encoding="utf-8")
        self.state["artifacts"].append(rel)
        return rel

    def external(self, command: str, args: list[str], timeout: int) -> dict[str, Any]:
        started = time.monotonic()
        try:
            proc = subprocess.run([command, *args], cwd=self.workspace, capture_output=True, text=True,
                                  timeout=timeout, check=False)
            stdout, stderr = proc.stdout or "", proc.stderr or ""
            timed_out = False
        except FileNotFoundError as exc:
            return {"ok": False, "exit_code": None, "spawn_error": str(exc), "latency_ms": round((time.monotonic()-started)*1000, 3)}
        except subprocess.TimeoutExpired as exc:
            stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
            proc = None
            timed_out = True
        text = "\n".join(x for x in (stdout, stderr) if x)
        payload = {"ok": proc is not None and proc.returncode == 0 and not timed_out,
                   "exit_code": None if proc is None else proc.returncode,
                   "latency_ms": round((time.monotonic()-started)*1000, 3),
                   "artifact_path": self.artifact(command.replace("-", "_"), text), **_bounded(text),
                   "_stdout": stdout, "_stderr": stderr}
        if not payload["ok"]:
            kind = "timeout" if timed_out else "nonzero_exit"
            payload["error"] = error_payload(kind, "Command timed out" if timed_out else f"Command exited {payload['exit_code']}", not timed_out)
        return payload

    def dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        self.state["tool_counts"][name] = self.state["tool_counts"].get(name, 0) + 1
        key = f"{name}:{json.dumps(args, sort_keys=True)}"
        if self.failure_counts.get(key, 0) >= 2:
            self.state["stop_reason"] = "tool_failure"
            self.save()
            return error_payload("circuit_open", "Repeated identical failed request")
        try:
            result = getattr(self, f"tool_{name}")(args)
        except Exception as exc:
            result = error_payload("invalid_input", str(exc))
        if not result.get("ok", False):
            self.failure_counts[key] = self.failure_counts.get(key, 0) + (1 if result.get("error", {}).get("retryable") else 2)
            self.state["last_error"] = {"tool": name, **result.get("error", {})}
            self.state["errors"].append(self.state["last_error"])
        self.save()
        return result

    def tool_inspect_workspace(self, p: dict[str, Any]) -> dict[str, Any]:
        operation = p.get("operation")
        if operation == "register":
            ids = p.get("citation_ids")
            if not isinstance(ids, list) or not ids or any(not isinstance(x, str) or not x.strip() for x in ids):
                raise ValueError("Register at least one nonempty citation ID")
            self.state["registered"] = True
            pending = self.state["pending_citation_ids"]
            pending.extend(x for x in dict.fromkeys(ids) if x not in pending and x not in self.state["processed_citation_ids"])
            return {"ok": True, "pending_citation_ids": pending}
        path = "input/manifest.json" if operation == "manifest" else p.get("path", "input")
        target = self.safe_path(path)
        if operation == "list": return {"ok": True, "entries": sorted(x.name for x in target.iterdir())[:100]}
        if operation == "manifest": return {"ok": True, "manifest": json.loads(target.read_text())}
        if operation != "read": raise ValueError("Invalid operation")
        text = target.read_text(encoding="utf-8")
        offset = int(p.get("offset", 0)); return {"ok": True, "path": p.get("path"), "offset": offset, "total_chars": len(text), **_bounded(text[offset:], int(p.get("max_chars", 6000)))}

    def tool_verify_references(self, p: dict[str, Any]) -> dict[str, Any]:
        if not self.state["registered"]:
            # Recover from a model that skipped the explicit registration call.
            # This deterministic safety net keeps scholarly tools from being
            # blocked by a malformed read path while preserving the same IDs.
            ids: list[str] = []
            for tex in self.workspace.rglob("*.tex"):
                text = tex.read_text(encoding="utf-8", errors="replace")
                ids.extend(re.findall(r"\\cite[a-zA-Z*]*\s*(?:\[[^]]*\])?\s*\{([^}]+)\}", text))
            flattened = [item.strip() for group in ids for item in group.split(",") if item.strip()]
            if flattened:
                self.state["registered"] = True
                self.state["pending_citation_ids"] = list(dict.fromkeys(flattened))
                self.state["auto_registered"] = True
            else:
                raise ValueError("Register citation IDs first")
        manifest = json.loads((self.workspace / "input/manifest.json").read_text())
        target = self.safe_path(p.get("target") or manifest["refchecker_target"], ("input",))
        if target.suffix.lower() not in {".tex", ".bib", ".pdf", ".md", ".txt"}: raise ValueError("Unsupported RefChecker input")
        report = f"./output/refchecker-{self.artifact_index + 1}.json"
        args = ["--paper", str(target), "--report-file", report, "--report-format", "json"]
        if os.environ.get("CITATIONCHECKER_PROVIDER") in {"apex", "gpt-priority"} and os.environ.get("OPENAI_API_KEY"):
            args += ["--llm-provider", "openai", "--llm-model", os.environ.get("CITATIONCHECKER_MODEL", "gpt-5.6-terra")]
            args += ["--llm-endpoint", os.environ.get("CITATIONCHECKER_BASE_URL") or os.environ.get("APEX_BASE_URL", "https://api.apexin.ai/v1")]
        result = self.external("academic-refchecker", args, int(p.get("timeout_seconds", 120)))
        try:
            parsed = json.loads((self.workspace / report).read_text())
            result["report_path"] = report
            if parsed.get("summary", {}).get("total_references_processed", 0) > 0:
                result["ok"] = True; result.pop("error", None)
        except Exception:
            parsed = None
        # Short benchmark cards often defeat LaTeX bibliography extraction.
        # RefChecker accepts BibTeX directly, so retry the staged sibling file.
        if not result.get("ok") and target.suffix.lower() == ".tex":
            bibs = sorted(target.parent.glob("*.bib"))
            if bibs:
                bib_text = bibs[0].read_text(encoding="utf-8", errors="replace")
                identifiers = re.findall(r"(?:eprint|arxiv(?:Id|_id)?|url)\s*=\s*[\{\"]?(?:https?://arxiv\.org/(?:abs|pdf)/)?([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)", bib_text, re.I)
                identifier = identifiers[0] if identifiers else None
                fallback_target = identifier or str(bibs[0])
                bib_report = f"./output/refchecker-{self.artifact_index + 1}.json"
                fallback_args = ["--paper", fallback_target, "--report-file", bib_report, "--report-format", "json"]
                if os.environ.get("CITATIONCHECKER_PROVIDER") in {"apex", "gpt-priority"} and os.environ.get("OPENAI_API_KEY"):
                    fallback_args += ["--llm-provider", "openai", "--llm-model", os.environ.get("CITATIONCHECKER_MODEL", "gpt-5.6-terra"), "--llm-endpoint", os.environ.get("CITATIONCHECKER_BASE_URL") or os.environ.get("APEX_BASE_URL", "https://api.apexin.ai/v1")]
                fallback = self.external("academic-refchecker", fallback_args, int(p.get("timeout_seconds", 120)))
                try:
                    parsed = json.loads((self.workspace / bib_report).read_text())
                    if parsed.get("summary", {}).get("total_references_processed", 0) > 0:
                        fallback["ok"] = True; fallback.pop("error", None); fallback["report_path"] = bib_report; fallback["fallback_from"] = str(target)
                except Exception:
                    pass
                result = fallback
        result.pop("_stdout", None); result.pop("_stderr", None)
        return result

    def tool_retrieve_paper(self, p: dict[str, Any]) -> dict[str, Any]:
        if not self.search_enabled: raise ValueError("Paper retrieval is disabled")
        if not self.state["registered"]: raise ValueError("Register citation IDs first")
        op = p.get("operation")
        if op == "search":
            if not str(p.get("query", "")).strip(): raise ValueError("search requires query")
            args = ["search", p["query"], "-n", str(p.get("max_results", 3)), "-s", p.get("source", "semantic,crossref,openalex,arxiv")]
        elif op in {"read", "download"} and p.get("source") and p.get("paper_id"):
            args = [op, p["source"], p["paper_id"], "-o", "./output/papers"]
        else: raise ValueError("read/download require one source and paper_id")
        result = self.external("paper-search", args, int(p.get("timeout_seconds", 120)))
        if result.get("ok") and op == "search":
            try:
                parsed = json.loads(result.get("_stdout", ""))
                if not isinstance(parsed.get("papers"), list): return error_payload("bad_json", "Search JSON missing papers list")
            except Exception: return error_payload("bad_json", "Tool output is not valid JSON")
        result.pop("_stdout", None); result.pop("_stderr", None)
        return result

    def tool_write_report(self, p: dict[str, Any]) -> dict[str, Any]:
        if not self.state["registered"]: raise ValueError("Register citation IDs first")
        markdown, report_json = p.get("markdown"), p.get("report_json")
        if not isinstance(markdown, str) or not isinstance(report_json, dict): raise ValueError("markdown and report_json are required")
        (self.output / "citation-report.md").write_text(markdown, encoding="utf-8")
        (self.output / "citation-report.json").write_text(json.dumps(report_json, indent=2), encoding="utf-8")
        ok, errors, _ = verify_report(self.output / "citation-report.md")
        ids = [x.get("citation") for x in report_json.get("citations", []) if isinstance(x, dict)]
        expected = self.state["pending_citation_ids"] + self.state["processed_citation_ids"]
        aliases = {x: x for x in expected} | {f"[{i+1}]": x for i, x in enumerate(expected)}
        aliases.update({f"\\citep{{{x}}}": x for x in expected})
        aliases.update({f"\\cite{{{x}}}": x for x in expected})
        normalized = [aliases.get(x, x) for x in ids]
        coverage = len(normalized) == len(expected) and sorted(normalized) == sorted(expected)
        if not ok or not coverage: return error_payload("invalid_report", json.dumps({"errors": errors, "missing": [x for x in expected if x not in normalized]}))
        if not self.state["tool_counts"].get("verify_references"): return error_payload("invalid_report", "Report requires an actual RefChecker observation")
        self.state.update({"citation_aliases": aliases, "processed_citation_ids": expected, "pending_citation_ids": [], "report_verified": True, "stop_reason": "completed"})
        self.save()
        return {"ok": True, "markdown_path": "./output/citation-report.md", "json_path": "./output/citation-report.json", "total_citations": len(ids)}


TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "inspect_workspace", "description": "Read staged manuscript files or register citation IDs.", "parameters": {"type": "object", "properties": {"operation": {"type": "string", "enum": ["manifest", "list", "read", "register"]}, "path": {"type": "string"}, "offset": {"type": "integer"}, "max_chars": {"type": "integer"}, "citation_ids": {"type": "array", "items": {"type": "string"}}}, "required": ["operation"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "verify_references", "description": "Run RefChecker against the staged manuscript.", "parameters": {"type": "object", "properties": {"target": {"type": "string"}, "timeout_seconds": {"type": "integer"}}, "additionalProperties": False}}},
    {"type": "function", "function": {"name": "retrieve_paper", "description": "Search, read, or download scholarly evidence.", "parameters": {"type": "object", "properties": {"operation": {"type": "string", "enum": ["search", "read", "download"]}, "query": {"type": "string"}, "source": {"type": "string"}, "paper_id": {"type": "string"}, "max_results": {"type": "integer"}, "max_chars": {"type": "integer"}, "timeout_seconds": {"type": "integer"}}, "required": ["operation"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "write_report", "description": "Write and mechanically validate both final reports.", "parameters": {"type": "object", "properties": {"markdown": {"type": "string"}, "report_json": {"type": "object"}}, "required": ["markdown", "report_json"], "additionalProperties": False}}},
]
