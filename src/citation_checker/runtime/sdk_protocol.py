from __future__ import annotations

import json
import sys
import time
from typing import Any


def emit(kind: str, **payload: Any) -> None:
    event = {"kind": kind, "timestamp": time.time(), **payload}
    sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def error_payload(kind: str, message: str, retryable: bool = False) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "kind": kind,
            "message": message,
            "retryable": retryable,
            "next_action": "Change the query or source; do not repeat an identical failed request twice."
            if retryable else "Correct the parameters or report insufficient evidence.",
        },
    }
