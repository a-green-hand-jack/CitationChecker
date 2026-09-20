from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SECRET_KEY = re.compile(r"(authorization|api[-_]?key|access[-_]?token|refresh[-_]?token|client[-_]?secret|password|credential)", re.I)
_SECRET_VALUE = re.compile(
    r"(?i)(authorization|api[-_]?key|access[-_]?token|refresh[-_]?token|client[-_]?secret|password)(\s*[:=]\s*)([\"']?)[^\s,\"'}]+\3"
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact(value: Any) -> Any:
    """Remove credential-shaped values before a run artifact is persisted."""
    if isinstance(value, str):
        return _SECRET_VALUE.sub(r"\1\2[REDACTED]", value)
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _SECRET_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    return value


def _kind(event: dict[str, Any]) -> str:
    mapping = {
        "session": "session",
        "agent_start": "agent_start",
        "agent_end": "agent_end",
        "agent_settled": "agent_settled",
        "turn_start": "turn_start",
        "turn_end": "turn_end",
        "message_start": "message_start",
        "message_update": "message_update",
        "message_end": "message_end",
        "tool_execution_start": "tool_start",
        "tool_execution_update": "tool_update",
        "tool_execution_end": "tool_end",
        "compaction_start": "compaction_start",
        "compaction_end": "compaction_end",
        "auto_retry_start": "auto_retry_start",
        "auto_retry_end": "auto_retry_end",
    }
    return mapping.get(str(event.get("type")), str(event.get("type", "unknown")))


class TrajectoryRecorder:
    """Persist every Pi JSON event plus derived timing and usage metadata."""

    def __init__(self, path: Path, system_prompt: str) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = path.open("w", encoding="utf-8")
        self._sequence = 0
        self._turn_started: float | None = None
        self._tool_started: dict[str, float] = {}
        self._usage = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "total": 0}
        self._tool_counts: dict[str, int] = {}
        self._events = 0
        self._messages = 0
        self._protocol_errors = 0
        self._usage_keys: set[str] = set()
        self.write(
            "system",
            {
                "role": "system",
                "content": system_prompt,
            },
        )

    def write(self, kind: str, payload: dict[str, Any], **extra: Any) -> None:
        self._sequence += 1
        record = {
            "sequence": self._sequence,
            "timestamp": _timestamp(),
            "kind": kind,
            **payload,
            **extra,
        }
        self._stream.write(json.dumps(redact(record), ensure_ascii=False, sort_keys=True) + "\n")
        self._stream.flush()

    def record_line(self, line: str) -> None:
        text = line.rstrip("\n")
        if not text:
            return
        try:
            event = json.loads(text)
        except json.JSONDecodeError as exc:
            self._protocol_errors += 1
            self.write("protocol_error", {"raw": text, "error": str(exc)})
            return
        if not isinstance(event, dict):
            self._protocol_errors += 1
            self.write("protocol_error", {"raw": event, "error": "Pi event was not a JSON object"})
            return

        self._events += 1
        event_type = str(event.get("type", "unknown"))
        now = time.monotonic()
        if event_type == "turn_start":
            self._turn_started = now
        elif event_type == "turn_end":
            event["latency_ms"] = round((now - self._turn_started) * 1000, 3) if self._turn_started else None
            self._turn_started = None
        elif event_type == "tool_execution_start":
            call_id = str(event.get("toolCallId", ""))
            self._tool_started[call_id] = now
            name = str(event.get("toolName", "unknown"))
            self._tool_counts[name] = self._tool_counts.get(name, 0) + 1
        elif event_type == "tool_execution_end":
            call_id = str(event.get("toolCallId", ""))
            event["latency_ms"] = round((now - self._tool_started.pop(call_id, now)) * 1000, 3)

        message = event.get("message")
        for candidate in (message,):
            if isinstance(candidate, dict):
                self._messages += 1
                if event_type == "message_end":
                    response_id = candidate.get("responseId") or candidate.get("id") or f"message-end:{self._sequence + 1}"
                    self._add_usage(candidate.get("usage"), str(response_id))
        metadata = {
            key: event[key]
            for key in ("role", "messageId", "responseId", "toolCallId", "toolName", "stopReason")
            if key in event
        }
        if isinstance(message, dict):
            for key in ("role", "id", "responseId", "stopReason"):
                if key in message and key not in metadata:
                    metadata[key if key != "id" else "message_id"] = message[key]
        self.write(_kind(event), {"event": event, **metadata})

    def _add_usage(self, usage: Any, key: str) -> None:
        if not isinstance(usage, dict):
            return
        if key in self._usage_keys:
            return
        self._usage_keys.add(key)
        fields = {
            "input": "input",
            "output": "output",
            "cacheRead": "cache_read",
            "cacheWrite": "cache_write",
            "totalTokens": "total",
        }
        for source, target in fields.items():
            value = usage.get(source)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                self._usage[target] += int(value)

    def record_state(self, state: dict[str, Any]) -> None:
        self.write("state_snapshot", {"state": state})

    def record_stop(self, reason: str, **details: Any) -> None:
        self.write("stop", {"stop_reason": reason, **details})

    def summary(self) -> dict[str, Any]:
        return {
            "events": self._events,
            "messages": self._messages,
            "tool_counts": dict(sorted(self._tool_counts.items())),
            "usage": dict(self._usage),
            "protocol_errors": self._protocol_errors,
            "secrets_redacted": True,
        }

    def close(self) -> None:
        self._stream.close()
