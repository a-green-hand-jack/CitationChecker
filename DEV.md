# Development — explicit SDK loop

Keep the implementation small. `SKILL.md` and `references/` define the citation
method; `sdk_worker.py` owns the loop; `sdk_tools.py` owns validated CLI adapters;
`runner.py` owns staging, worker lifetime and final acceptance. The SDK is only
an API client. Preserve the four public CLI commands.

## Invariants

1. Use `build_system_prompt()` once during staging. The worker consumes the exact
   persisted system/user prompt; do not log a substitute prompt.
2. Before each request, append a code-generated state snapshot to the tail.
   Preserve assistant messages and original argument strings/call IDs. Do not
   insert state between an assistant tool call and its tool result.
3. Validate arguments against exported JSON schemas before executing tools.
   Enforce bounds in code; no shell interpolation or unrestricted network tool.
4. TeX-to-bibliography fallback must preserve the original `.bib` contents and
   checking target. Never change `--paper` to a cited arXiv ID.
5. Missing usage is unknown. Sum only per-request events, once per step; stop
   events contain cumulative `usage_total`. Cache reads are a subset of prompt
   tokens. Disable hidden SDK retries so attempts remain explicit.
6. Check the token budget again before dispatching a response's tool calls.
   After completion, block remaining calls in the same response but retain their
   paired observations. Recheck artifacts and coverage in the parent runner.
7. `--disable-paper-search` removes the tool from both the schemas and dispatcher.
   It is an execution gate, not just a prompt. RefChecker still exposes its normal
   bibliography observations; document those when interpreting an ablation.
8. Redact producer events, logs, state, and saved tool text. Original in-memory
   messages are used for the next model request, not redacted reconstructions.

## Testing

```bash
python -m pip install -e . pytest
python -m pytest tests/test_sdk_regressions.py tests/test_runtime.py -q
python -m pytest -q
python -m compileall -q src
```

The repair was checked offline with fake model/tool responses and local subprocess
fixtures. It did not run a paid model benchmark or download the scholarly corpus.
A successful unit test is not evidence that a live provider accepts every optional
parameter; `--thinking` is now forwarded as `reasoning_effort` rather than ignored.

## Artifacts and evaluation

Receipts identify `agent_backend: openai-sdk`. Request/response/tool logs are
redacted application-level replays, not byte-for-byte HTTP captures. Unknown
usage must remain null in aggregate metrics. Re-run SDK ablations in a fresh
output directory; never edit historical Pi predictions or silently mix backends.
The four variants from one paper are not four independent source papers.

Process-group cancellation targets POSIX platforms. PDF conversion remains a
preprocessing dependency, not a model-initiated third scholarly tool. Bibliography
extraction, retrieval coverage, and scientific judgment remain fallible.
