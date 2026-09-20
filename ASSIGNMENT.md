# Assignment 1 evidence — SDK implementation

This branch implements its own loop in `runtime/sdk_worker.py`. The official
OpenAI Python SDK transports requests to a compatible model endpoint; no Pi,
Node.js, Agents SDK, or high-level agent framework drives the loop.

| Requirement | Implementation / evidence |
| --- | --- |
| Native roles and system instruction | One frozen system prompt is written to `task.json`, consumed by the worker, and logged; actual requests contain native system/user/assistant/tool messages. |
| At least two typed tools | RefChecker and paper-search adapters plus staged-file inspection and report submission; exported contracts, runtime JSON-schema validation, bounded observations. |
| Multi-step loop | Original assistant messages are preserved, results reference their call IDs, and the next request depends on tool observations. |
| Code-maintained task state | Bounded snapshots are appended at the tail before every request; full state is persisted separately. |
| Stopping conditions | Step, cumulative token, per-response output, and wall-clock limits; post-response checks block tool execution after budget exhaustion. A completion claim must pass report/coverage checks. |
| Error handling | Malformed arguments become observations, deterministic failures open a circuit on an unchanged retry, CLI timeouts/missing executables have actionable errors, and exits leave receipts. |
| Trajectory logging | Actual request payloads, full SDK response objects, linked tool observations, latency, state, and stop events; credential-shaped content is redacted. |
| Small evaluation and ablation | Existing controlled tasks and paired full/no-paper-search runner are retained. New SDK provider-backed results must be produced separately from the historical Pi results. |

## Offline checks

```bash
python -m pip install -e . pytest
python -m pytest tests/test_sdk_regressions.py tests/test_runtime.py -q
python -m compileall -q src
```

The regression suite exercises state injection, assistant replay, malformed and
blocked tool calls, usage accounting, unknown usage, schema/path boundaries,
RefChecker fallback, report rejection, and subprocess timeout behavior. Fake
providers/tools prove control flow, not citation accuracy.

## Fresh provider-backed evidence to collect

```bash
citationchecker check benchmark/tasks/case-0001/main.tex \
  --provider <provider> --model <model> --out runs/sdk-demo-new \
  --max-steps 10 --max-tokens 90000 --timeout 600
python benchmark/ablate.py --per-mutation 1 \
  --provider <provider> --model <model> --out benchmark/runs/sdk-ablation-new
```

Retain the exact commit, configuration, task IDs, both modes' predictions,
receipts, tool artifacts, and sanitized success/budget-stop trajectories. Keep
missing predictions in the denominator. Do not relabel `issue1-ablation-20260920`
or the older 40-case result as SDK measurements.

## Limits

Token limits are checked using returned usage and may be exceeded by the last
in-flight request. Unknown usage stops a capped run; it is not reported as zero.
Only SDK request tokens are included, not calls made internally by external CLIs.
Report validation checks format and registered-ID coverage, not truth or complete
manuscript parsing. The current fixtures are small abstract-derived citation
cards with some obvious synthetic negatives, not a full-paper benchmark.
