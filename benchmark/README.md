# Controlled ICLR 2026 benchmark

The benchmark uses ten real papers accepted as ICLR 2026 posters. Each paper is
pinned to an arXiv version and stored with:

- the compiled arXiv PDF;
- the original arXiv source archive;
- the extracted TeX source tree;
- SHA-256 hashes and the OpenReview/arXiv provenance in
  [`corpus/manifest.json`](corpus/manifest.json).

The corpus is the original sample. The benchmark cases are small LaTeX citation
cards generated from manually selected sentences in the pinned papers' arXiv
abstracts. This keeps each test focused while retaining a direct link to the
real source paper and its PDF/TeX materials.

## Cases

There are 40 cases: four for each paper.

| Case | Reference | Claim |
| --- | --- | --- |
| `valid` | exact self-reference | supported |
| `wrong-year` | same paper, year changed | metadata mismatch; claim remains recoverable |
| `hallucinated` | independently fabricated title/authors/arXiv id | not found; insufficient evidence |
| `real-swap` | another real ICLR 2026 paper | verified reference; unsupported claim |

`cases.jsonl` is the gold source of truth. Every mutation is explicit in the
`mutation` field. The hallucinated titles are hand-written and intentionally do
not contain the source-paper title, so the model cannot pass the case by
recovering a title suffix. A `NOT_FOUND` reference is scored with
`INSUFFICIENT_EVIDENCE`; `UNSUPPORTED` is reserved for a real retrieved paper
that fails to support the claim. Each generated task directory uses a neutral `case-0001` style ID and
the neutral `ref_a` citation key. It contains only `main.tex` and
`references.bib`, so gold metadata and mutation names cannot be staged into the
manuscript sent to Pi even when a task directory is passed directly.

## Rebuild or verify the corpus

The checked-in corpus is already materialized. To download missing files or
rebuild a fresh checkout, run:

```bash
python benchmark/download_corpus.py
python benchmark/download_corpus.py --verify-only
python benchmark/create_cases.py
python benchmark/generate_tasks.py --clean
```

The downloader uses version-pinned arXiv URLs and refuses SHA-256 or TeX-file
inventory mismatches.

## Run the benchmark

Development runs default to the managed DeepSeek route:

```text
provider: apex-deepseek
model:    deepseek-v4-flash
```

Run all 40 cases and score them:

```bash
python benchmark/run.py --workers 8
python benchmark/evaluate.py benchmark/runs/predictions.jsonl
```

`--workers` controls the number of concurrent provider-backed tasks. Use `1`
for a serial diagnostic run; the example uses eight workers to keep the run
bounded while exercising the full corpus in parallel.

The provider and model remain explicit overrides when needed:

```bash
python benchmark/run.py --provider apex-deepseek --model deepseek-v4-flash --limit 4
```

The evaluator reports reference-status accuracy, support-label accuracy, exact
match, and exact match by mutation type. These are controlled diagnostic cases,
not a broad estimate of citation-checking performance.

Run a paired mechanism ablation on one case of each mutation type:

```bash
python benchmark/ablate.py --per-mutation 1
```

Both modes use the same neutral tasks, model, and budgets. `full` exposes paper
retrieval; `no-paper-search` removes that tool from the Pi allowlist.
`ablation.json` records predictions, failures, reference and support accuracy,
joint exact match, per-mutation scores, tool calls, model tokens, and elapsed
time for both modes.

The latest tracked real run is published under
[`results/iclr2026-deepseek-v4-flash-2026-09-20/`](results/iclr2026-deepseek-v4-flash-2026-09-20/).
It contains the predictions, sanitized receipts, score summary, evaluator
output, and checksums without duplicating the raw downloaded evidence cache.

## Provenance

The conference decision/status comes from the public ICLR 2026 OpenReview record
stored in each manifest row. The manuscript source, PDF, title, authors, and
abstract are pinned to the listed arXiv version. The benchmark does not execute
any manuscript code.
