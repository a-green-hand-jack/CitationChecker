# Coding-agent rules

Keep this branch a small Python SDK agent; do not reintroduce Pi or a high-level
agent framework. Reuse RefChecker, paper-search-mcp, and PyMuPDF4LLM.

Keep scientific methodology in the Skill/reference guide and loop policy in
Python. Preserve original assistant messages and linked tool results, append
code-derived state before requests, validate bounded tool arguments, and require
verified artifacts before completion. Never replace a manuscript's bibliography
with the cited paper itself during fallback.

Do not execute manuscript code, persist credentials, fabricate evaluations, or
relabel historical Pi results as SDK results. Preserve `doctor`, `inspect`,
`check`, `verify`, and both final report artifacts. Run offline regressions after
changing protocol, usage, state, budget, or tool-dispatch behavior.
