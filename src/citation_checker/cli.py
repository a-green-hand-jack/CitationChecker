"""Public ``citationchecker`` command.

The CLI is intentionally deterministic: it stages inputs, checks host tools,
launches Pi, and mechanically validates the final artifacts. Citation reasoning
lives in SKILL.md and is performed by the harness model.
"""

from __future__ import annotations

from citation_checker.runtime.main import main


if __name__ == "__main__":
    main()
