# CitationChecker — SDK branch

A small citation-auditing agent with an explicit Python model/tool loop. The
OpenAI Python SDK is the API client, **not an agent framework**. This branch
requires neither Pi nor Node.js. The model judges claims; Python owns execution,
state, budgets, and mechanical report acceptance.

The agent checks two separate questions: whether a reference is real and correctly
identified, and whether the retrieved work supports the manuscript's claim.
It reuses [RefChecker](https://github.com/markrussinovich/refchecker) and
[paper-search-mcp](https://github.com/openags/paper-search-mcp) through their CLIs.
PyMuPDF4LLM converts PDF-only input; LaTeX is read directly.

## Install and run

Python 3.11+ and a POSIX environment are required for process-group cleanup.

```bash
python -m pip install -e .
python -m pip install 'academic-refchecker[llm]'
uv tool install paper-search-mcp
citationchecker doctor
citationchecker check ./latex-project --provider <provider> --model <model>
citationchecker check manuscript.pdf --provider <provider> --model <model>
```

Configure a compatible endpoint with `CITATIONCHECKER_BASE_URL` and a local
`OPENAI_API_KEY`. Provider-specific `CITATIONCHECKER_<PROVIDER>_BASE_URL` and
`CITATIONCHECKER_<PROVIDER>_API_KEY` take precedence; replace hyphens with underscores
and uppercase the provider name. Existing Apex/DeepSeek environment aliases remain
supported. Do not put credentials in the repository. `--thinking`, when supplied,
is forwarded as `reasoning_effort`; omit it for endpoints that do not support it.

The stable commands are `doctor`, `inspect`, `check`, and `verify`.

```bash
citationchecker check manuscript.tex --dry-run
citationchecker check manuscript.tex --max-steps 10 --max-tokens 90000 \
  --max-output-tokens 4096 --timeout 600
citationchecker verify runs/<run>/workspace/output/citation-report.md
```

## Small explicit architecture

```text
LaTeX or PDF -> staging (+ PDF conversion only when needed)
            -> SDK worker: system/user -> model -> typed tool -> observation -> repeat
            -> report validation -> receipt
```

Four registered tools have JSON schemas and runtime validation:
`inspect_workspace`, `verify_references`, `retrieve_paper`, and `write_report`.
There is no general shell tool. External CLIs receive argument lists, not shell
strings. Text observations are bounded (default 6,000, maximum 12,000 characters),
with saved artifacts for additional reading.

Before every model request, code appends a bounded state snapshot to the message
tail. The frozen system prefix and original assistant messages are retained.
Tool results use the original `tool_call_id`; malformed/blocked calls are logged
as observations. A plain completion claim gets at most one corrective turn.

Budgets are checked before requests **and after responses, before tool execution**.
An exhausted budget cannot submit a successful report. Missing usage is `null`,
not zero; with a token cap enabled it stops the run as `usage_unknown`. Provider
usage arrives after a request, so the final request can exceed the threshold.
Only per-request usage is summed; final totals are never added again. Cached
prompt tokens are not counted twice. External CLI model usage is excluded.

RefChecker fallback preserves the checking target: a failed TeX extraction may
retry its single staged sibling `.bib`, preserving all original metadata. It
never substitutes the cited paper's arXiv ID. Multiple bibliographies require an
explicit selection. A report requires a successful RefChecker observation, not
merely an attempted call.

## Artifacts and labels

Each run contains frozen instructions, `task.json`, `tool-contracts.json`,
`state.json`, `response.txt`, `trajectory.jsonl`, and `receipt.json`. The trajectory
records the actual request payloads, SDK responses, tool IDs/results, state,
latencies, and stop reason, with credential-shaped content redacted. Model-facing
history is not rewritten from the redacted log. Treat manuscripts/evidence as
sensitive and review artifacts before publishing.

Final outputs are `workspace/output/citation-report.md` and `.json`.
Reference labels: `VERIFIED`, `METADATA_MISMATCH`, `NOT_FOUND`, `UNVERIFIABLE`.
Support labels: `SUPPORTED`, `PARTIALLY_SUPPORTED`, `UNSUPPORTED`,
`INSUFFICIENT_EVIDENCE`. Mechanical validation is not a proof of scientific truth
or exhaustive citation extraction.

## Tests and evaluation provenance

```bash
python -m pip install pytest
python -m pytest tests/test_sdk_regressions.py tests/test_runtime.py -q
python -m pytest -q
```

The controlled corpus still contains 40 citation cards from ten papers; neutral
fixture IDs do not eliminate all synthetic clues or establish full-paper accuracy.
The tracked 40-case results and `issue1-ablation-20260920` results are **historical
Pi runs**, not measurements of this SDK implementation. They remain unchanged.
No new provider-backed score is claimed by this repair.

For a fresh SDK paired evaluation, use a new output directory:

```bash
python benchmark/ablate.py --per-mutation 1 --out benchmark/runs/sdk-ablation-new
```

See [ASSIGNMENT.md](ASSIGNMENT.md) for the submission evidence checklist and
[DEV.md](DEV.md) for the execution contracts and test scope.
