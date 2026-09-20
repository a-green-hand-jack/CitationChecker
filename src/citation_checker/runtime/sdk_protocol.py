from __future__ import annotations

import json
import sys
import time
from typing import Any

from .trajectory import redact


def emit(kind: str, **payload: Any) -> None:
    # Redact at the producer as well as the recorder: stdout is an artifact too.
    event = {"kind": kind, "timestamp": time.time(), **payload}
    sys.stdout.write(json.dumps(redact(event), ensure_ascii=False) + "\n")
    sys.stdout.flush()


def error_payload(kind: str, message: str, retryable: bool = False) -> dict[str, Any]:
    return {"ok": False, "error": {"kind": kind, "message": message,
            "retryable": retryable, "next_action":
            "Change the query or source; at most one identical transient retry is allowed."
            if retryable else "Correct the parameters or report insufficient evidence; do not retry unchanged."}}
