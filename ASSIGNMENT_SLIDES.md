# Assignment 1 — SDK implementation (7-slide outline)

## 1. Problem
Reference authenticity and claim support are separate questions. Reuse existing
scholarly tools; let the model compare claims with retrieved evidence.

## 2. Architecture
Python staging -> our SDK worker loop -> typed tools -> observations -> report.
The OpenAI SDK is only the API client; no Pi or high-level agent framework.

## 3. Tools
`inspect_workspace`, `verify_references`, `retrieve_paper`, `write_report`.
Runtime schema validation, path restrictions, bounded output and saved artifacts.
PDF conversion is preprocessing, not a model-initiated tool call.

## 4. Loop and state
Frozen system prefix, native roles, original assistant messages, matching
`tool_call_id`, and a code-generated state snapshot at each request's tail.
Show an actual SDK success trajectory after running the new version.

## 5. Budgets and errors
Step/output/token/wall-clock caps; post-response budget checks prevent tool calls
after exhaustion. Missing usage is unknown. One completion-repair turn, bounded
retries, target-preserving RefChecker fallback, and non-success failure receipts.

## 6. Evaluation
Use the existing 40 controlled citation cards and paired full/no-paper-search
runner. The old 40/40 and four-task ablation are historical Pi measurements.
Do not present them as SDK scores. Insert fresh SDK results only after running
and publishing the matching configuration, predictions, receipts and trajectories.

## 7. Reproduction and limitations
Run `python -m pytest tests/test_sdk_regressions.py -q`, then a fresh provider-backed
`python benchmark/ablate.py --per-mutation 1 --out benchmark/runs/sdk-ablation-new`.
The small abstract-derived fixtures and synthetic negatives limit generalization.
Returned token counts exclude external CLI model calls; the last in-flight
request can exceed the threshold. Validation does not establish scientific truth.
