# Assignment 1 — CitationChecker (7-slide outline)

## 1. Problem and boundary

- Audit reference authenticity and claim support in an existing manuscript.
- Reuse RefChecker, paper-search, and PyMuPDF4LLM; no replacement search or verifier.
- Pi 0.85.1 is the low-level provider/session harness. CitationChecker owns the loop policy, tools, state, budgets, reports, and evidence.

## 2. Native loop

- Frozen system instruction plus user task are preserved in `trajectory.jsonl`.
- Pi JSONL assistant messages retain response IDs, tool calls, and tool results.
- The `context` hook appends a code-generated `citation_state` message before every provider request.

## 3. Typed tools

- `inspect_workspace`: bounded staged-file reads and citation registration.
- `verify_references`: typed, path-restricted RefChecker delegation.
- `retrieve_paper`: bounded search/read/download delegation with saved artifacts.
- `write_report`: validates and persists the two required report files.

## 4. State, stopping, and errors

- State tracks citation IDs, steps, tools, usage, errors, artifacts, and report verification.
- `--max-steps`, `--max-tokens`, `--max-output-tokens`, and wall timeout are enforced in code.
- Receipts distinguish `completed`, `token_limit`, `step_limit`, `timeout`, `tool_failure`, `provider_error`, and `invalid_report`.
- External processes run without a shell and are killed as process groups on timeout.

## 5. Replayable evidence

- `trajectory.jsonl` records system/user/assistant/tool events, call IDs, bounded observations, artifact paths, usage, and latency.
- `state.json`, `tool-contracts.json`, and schema-2 `receipt.json` are written for every run.
- `budget-trace.json` is a real non-success token-limit run; no budget exhaustion is promoted to completion.

## 6. Blind benchmark and ablation

- Model-visible fixtures use `case-0001`…`case-0040` and neutral `ref_a`; gold mutation labels stay evaluator-side.
- Four paired cases cover clean, metadata corruption, hallucinated reference, and real-reference swap.
- Full: reference/support/joint = 1.0/1.0/1.0. No-paper-search: 1.0/0.5/0.5.
- Both modes used the same provider, model, task IDs, and budgets; all eight receipts completed and verified.

## 7. Reproduction and limits

```bash
.venv/bin/python -m pytest -q
.venv/bin/python benchmark/ablate.py --per-mutation 1 \
  --provider apex-deepseek --model deepseek-v4-flash
```

- The ablation is a four-task course evaluation, not a general benchmark.
- External CLI usage is retained as artifacts and excluded from Pi token totals.
- Full raw trajectories are kept in the ignored run directory; sanitized summaries and checksums are tracked under `benchmark/results/issue1-ablation-20260920/`.
