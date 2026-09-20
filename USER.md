# CitationChecker SDK quick start

This branch does not use Pi. Install with Python 3.11+ on Linux/macOS:

```bash
python -m pip install -e .
python -m pip install 'academic-refchecker[llm]'
uv tool install paper-search-mcp
citationchecker doctor
```

Keep API credentials in local environment variables. Set `CITATIONCHECKER_BASE_URL`
for your compatible endpoint and `OPENAI_API_KEY` locally, or use the documented
provider-specific variables in [README.md](README.md). Do not commit secrets.

```bash
citationchecker inspect ./latex-project
citationchecker check ./latex-project --provider <provider> --model <model>
citationchecker check paper.pdf --provider <provider> --model <model>
citationchecker check main.tex --dry-run
```

Prefer a complete LaTeX project directory when the manuscript has included files.
A single `.tex` stages sibling bibliographies; PDF-only input is converted into
Markdown. RefChecker still checks the original staged PDF or bibliography.

Use `--max-steps`, `--max-tokens`, `--max-output-tokens`, and `--timeout` to bound a
run. `--max-tokens 0` explicitly disables only the cumulative token cap. Returned
usage may cross the cap on the last request; such a response cannot execute tools.
With a cap enabled, missing usage stops as `usage_unknown`.

The two reports are under `workspace/output/`. A successful run requires
`receipt.json` to say `completed`, `verified: true`, and runner exit code zero.
An `INSUFFICIENT_EVIDENCE` citation is not necessarily a failed run: it is an
explicit abstention when the source could not be adequately checked.

```bash
citationchecker verify runs/<run>/workspace/output/citation-report.md
python benchmark/ablate.py --per-mutation 1 --out benchmark/runs/sdk-ablation-new
```

Use a new output directory for each experiment. Existing published results are
historical Pi runs; fresh SDK results have not been supplied by the repair.
`--thinking` is optional and maps to the endpoint's `reasoning_effort` parameter.
Omit it when your endpoint does not support that parameter.

Before sharing trajectories, review manuscript privacy and the automated redaction.
Mechanical report validation is not a guarantee that scientific claims are correct.
