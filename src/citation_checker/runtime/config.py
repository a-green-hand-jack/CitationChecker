from __future__ import annotations

import os


# Development runs use the managed DeepSeek route unless a caller explicitly
# overrides it on the CLI or through these environment variables.
DEFAULT_PROVIDER = os.environ.get("CITATIONCHECKER_PROVIDER", "apex-deepseek")
DEFAULT_MODEL = os.environ.get("CITATIONCHECKER_MODEL", "deepseek-v4-flash")
