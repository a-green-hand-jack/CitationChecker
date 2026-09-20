# CitationChecker Micro Benchmark

This benchmark is intentionally small. It is designed for a course project, not as a research-grade leaderboard.

## Design

The benchmark contains **12 single-citation tasks** built from **6 real citation relationships** found in three arXiv papers:

- RoBERTa: arXiv:1907.11692
- Efficient Transformers: A Survey: arXiv:2009.06732
- Expository Text Generation: Imitate, Retrieve, Paraphrase: arXiv:2305.03276

Each positive task contains a short **paraphrase** of the original citation context plus the intended real reference. Each positive is paired with one manually constructed negative. We do not redistribute the source papers or long excerpts.

Negative mutations cover three failure modes:

1. `metadata_corruption` — the intended paper is real, but one bibliographic field (here, year) is deliberately wrong.
2. `reference_swap` — the citation points to a different, real paper that does not support the claim.
3. `claim_strength_corruption` — the reference is real, but the manuscript claim is deliberately strengthened or altered beyond what the cited work supports.

The benchmark therefore separates two outputs:

- `gold_reference_status`: bibliographic validity (`VERIFIED` or `METADATA_MISMATCH` in this set).
- `gold_support`: semantic support (`SUPPORTED` or `UNSUPPORTED` in this set).

## Files

- `cases.jsonl` — gold data and provenance.
- `tasks/*.md` — tiny manuscripts that can be passed directly to `citationchecker check`.
- `evaluate.py` — lightweight scorer.
- `example_predictions.jsonl` — perfect-format example, useful for testing the evaluator.

## Running CitationChecker

Run each task independently so the output corresponds to one gold item:

```bash
citationchecker check benchmark/tasks/roberta_bert_pos.md --provider <provider> --model <model>
```

For a full benchmark, run the 12 files and collect one prediction per `task_id`. A prediction JSONL row only needs:

```json
{"task_id":"roberta_bert_pos","reference_status":"VERIFIED","support":"SUPPORTED"}
```

Then score it:

```bash
python benchmark/evaluate.py predictions.jsonl
```

The evaluator reports:

- reference-status accuracy
- support-label accuracy
- overall exact match
- exact match by mutation type
- simple confusion counts

It can also consume a directory tree containing `citation-report.json` files, though explicit JSONL predictions are the most reproducible format.

## Ground-truth policy

The positive relationships were manually checked against the cited works and the source papers. The text in `tasks/` is paraphrased rather than copied verbatim. Negative examples change exactly one high-level factor whenever possible, so the intended error type is easy to audit.

This benchmark is deliberately diagnostic rather than statistically representative. Do not report it as evidence of general citation-verification performance.

## Source papers and cited works

Source papers:

- https://arxiv.org/abs/1907.11692
- https://arxiv.org/abs/2009.06732
- https://arxiv.org/abs/2305.03276

Cited works used in tasks include:

- BERT — https://arxiv.org/abs/1810.04805
- Attention Is All You Need — https://arxiv.org/abs/1706.03762
- Layer Normalization — https://arxiv.org/abs/1607.06450
- Retrieval-Augmented Generation — https://arxiv.org/abs/2005.11401
- Longformer — https://arxiv.org/abs/2004.05150
- Deep Residual Learning — https://arxiv.org/abs/1512.03385
- Dense Passage Retrieval — https://arxiv.org/abs/2004.04906

Consult the original arXiv pages for licenses and definitive metadata.
