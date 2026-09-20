# Assignment 1 evidence

This checkout uses Pi 0.85.1 as a low-level provider/session harness. The
course boundary was confirmed for this implementation by the project owner on
2026-09-20: Pi is not treated as a high-level agent framework. CitationChecker
owns the domain tools, state, request budget, stop reasons, report validation,
and trajectory receipt; Pi supplies the provider protocol and extension hook.

The adapter is [pi_extension.ts](src/citation_checker/pi_extension.ts). It
registers typed `inspect_workspace`, `verify_references`, `retrieve_paper`, and
`write_report` tools. The first three delegate to existing CLIs or bounded
staged-file reads; it does not reimplement RefChecker, paper-search, or PDF
conversion. `write_report` persists both required artifacts and calls the
mechanical verifier before accepting the run.

Each model request receives a code-generated `citation_state` custom message.
The state includes registered and processed citation IDs, pending IDs, tool
counts, errors, usage, and remaining budgets. `trajectory.jsonl` stores the
original Pi JSONL events plus normalized role, call ID, latency, tool, usage,
state, and stop records. Credentials are redacted before persistence.

The stable CLI remains `doctor`, `inspect`, `check`, and `verify`. `check`
adds `--max-steps`, `--max-tokens`, `--max-output-tokens`,
`--disable-paper-search`, and the existing wall-clock `--timeout`. Receipts
distinguish `completed`, `step_limit`, `token_limit`, `timeout`,
`tool_failure`, `provider_error`, `invalid_report`, and setup/protocol errors.
Timeout cleanup kills the Pi process group. Provider usage arrives after a
request, so a token-limit run can exceed the cap by the final in-flight
request; the receipt preserves the actual reported total.

The benchmark task directories use neutral `case-0001` identifiers and
`ref_a` citation keys. Gold mutation labels remain in `cases.jsonl`, which is
read only by the evaluator. `benchmark/ablate.py` runs the same fixed neutral
task set in `full` and `no-paper-search` modes and records paired predictions,
receipts, trajectories, token totals, latency, tool counts, failures, and
metrics.

## Reproducible evidence commands

```bash
.venv/bin/python -m pytest -q
.venv/bin/citationchecker doctor --json
.venv/bin/citationchecker check benchmark/tasks/case-0001/main.tex \
  --provider apex-deepseek --model deepseek-v4-flash \
  --max-steps 10 --max-tokens 90000 --timeout 600
.venv/bin/python benchmark/ablate.py --per-mutation 1 \
  --provider apex-deepseek --model deepseek-v4-flash
```

The last two commands require the configured real provider and external
scholarly CLIs. A run is accepted only when its receipt says `completed`, its
two reports pass `verify`, and its trajectory and tool artifacts are present.

The paired real result is recorded in
[`benchmark/results/issue1-ablation-20260920/`](benchmark/results/issue1-ablation-20260920/).
Its full mode scored 1.0 reference / 1.0 support / 1.0 joint exact on the four
fixed cases; the no-paper-search mode scored 1.0 / 0.5 / 0.5. The raw ignored
runs retain all eight trajectories and external-tool artifacts.

[`budget-trace.json`](benchmark/results/issue1-ablation-20260920/budget-trace.json)
is a current provider-backed `token_limit` run: it is non-verified, records the
known usage and trajectory, and demonstrates that budget exhaustion is not
reported as success.

[`ASSIGNMENT_SLIDES.md`](ASSIGNMENT_SLIDES.md) is a seven-slide submission
outline with the architecture, evidence, ablation, reproduction command, and
limitations.
