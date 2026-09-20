#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 -m pip install -e "$ROOT"

echo "Installed CitationChecker (including PyMuPDF4LLM)."
echo "Run: citationchecker doctor"
echo "Scholarly tools are not installed automatically:"
echo "  RefChecker: pip install 'academic-refchecker[llm]'"
echo "  paper-search-mcp: uv tool install paper-search-mcp"
