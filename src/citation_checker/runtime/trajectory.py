"""Redacted JSONL events; only per-request usage contributes to totals."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SECRET_KEY = re.compile(r"authorization|api[-_]?key|access[-_]?token|refresh[-_]?token|client[-_]?secret|password|credential", re.I)
_SECRET_VALUE = re.compile(r"(authorization|api[-_]?key|access[-_]?token|refresh[-_]?token|client[-_]?secret|password)(\s*[:=]\s*)(?:Bearer\s+)?[\"']?[^\s,\"'}]+", re.I)
USAGE_FIELDS = ("input", "output", "cache_read", "cache_write", "total")


def redact(value: Any) -> Any:
    if isinstance(value, str):
        value = _SECRET_VALUE.sub(r"\1\2[REDACTED]", value)
        value = re.sub(r"\bsk-[A-Za-z0-9_-]{16,}", "[REDACTED]", value)
        for key, secret in os.environ.items():
            if _SECRET_KEY.search(key) and len(secret) >= 8:
                value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        return {key: "[REDACTED]" if _SECRET_KEY.search(str(key)) else redact(item)
                for key, item in value.items()}
    return value


class TrajectoryRecorder:
    def __init__(self, path: Path, system_prompt: str) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = path.open("w", encoding="utf-8")
        self.sequence = self.events = self.protocol_errors = 0
        self.tool_counts: dict[str, int] = {}
        self.usage: dict[str, int | None] = dict.fromkeys(USAGE_FIELDS, 0)
        self._usage_steps: set[Any] = set()
        self._open_calls: set[str] = set()
        self.write("system", {"role": "system", "content": system_prompt})

    def write(self, kind: str, payload: dict[str, Any]) -> None:
        self.sequence += 1
        record = {**payload, "sequence": self.sequence,
                  "recorded_at": datetime.now(timezone.utc).isoformat(), "kind": kind}
        self.stream.write(json.dumps(redact(record), ensure_ascii=False) + "\n")
        self.stream.flush()

    def record_line(self, line: str) -> None:
        if not line.strip():
            return
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError("event must be an object")
        except (ValueError, TypeError) as exc:
            self.protocol_errors += 1
            self.write("protocol_error", {"raw": line.rstrip(), "error": str(exc)})
            return
        self.events += 1
        kind = str(event.pop("kind", "unknown"))
        self.write(kind, event)
        if kind == "protocol_error":
            self.protocol_errors += 1
        if kind == "tool_start":
            call_id = event.get("call_id", "")
            if not call_id or call_id in self._open_calls:
                self.protocol_errors += 1
            self._open_calls.add(call_id)
            if event.get("executed", True):
                name = str(event.get("tool", "unknown"))
                self.tool_counts[name] = self.tool_counts.get(name, 0) + 1
        elif kind == "tool_result":
            call_id = event.get("call_id", "")
            if call_id not in self._open_calls:
                self.protocol_errors += 1
            self._open_calls.discard(call_id)
        # Stop/state events carry cumulative totals. Never sum them again.
        if kind == "model_response" and "usage" in event:
            key = event.get("step", event.get("response_id", self.sequence))
            if key in self._usage_steps:
                return
            self._usage_steps.add(key)
            usage = event["usage"] or {}
            for field in USAGE_FIELDS:
                value = usage.get(field)
                if type(value) is not int or value < 0:
                    self.usage[field] = None
                elif self.usage[field] is not None:
                    self.usage[field] += value

    def record_state(self, state: dict[str, Any]) -> None:
        self.write("state_snapshot", {"state": state})

    def record_stop(self, reason: str, **details: Any) -> None:
        self.write("stop", {"stop_reason": reason, **details})

    def summary(self) -> dict[str, Any]:
        return {"events": self.events, "tool_counts": dict(sorted(self.tool_counts.items())),
                "usage": dict(self.usage), "usage_known": self.usage["total"] is not None,
                "protocol_errors": self.protocol_errors + len(self._open_calls),
                "secrets_redacted": True}

    def close(self) -> None:
        self.stream.close()
