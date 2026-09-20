# Coding-agent rules

1. Keep CitationChecker a small course-project agent.
2. Do not reimplement RefChecker, paper-search-mcp, or PyMuPDF4LLM.
3. Prefer LaTeX source when available; only convert PDF when source is unavailable.
4. Keep citation methodology in `SKILL.md` and `references/`.
5. Keep Python runtime deterministic; no in-process LLM calls.
6. PyMuPDF4LLM may be called by staging only for input conversion, never for citation judgment.
7. Do not execute manuscript code.
8. Do not persist model/provider credentials.
9. Preserve the two required final artifacts: `citation-report.md` and `citation-report.json`.
10. Keep the public CLI commands stable: `doctor`, `inspect`, `check`, `verify`.
