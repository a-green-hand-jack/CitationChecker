# ICLR 2026 citation benchmark — DeepSeek v4 Flash

This directory contains the tracked result package for the real provider-backed
40-case run over the ten-paper ICLR 2026 corpus.

- provider: `apex-deepseek`
- model: `deepseek-v4-flash`
- thinking: `medium`
- concurrency: 8 workers
- benchmark source commit: `81fae30bffc4435965598907b94845a0c5b074b3`

The package includes the model predictions, one sanitized receipt per task, a
machine-readable score summary, the evaluator's raw output, run metadata, and
SHA-256 checksums. The raw ignored run directory contains repeated downloaded
paper evidence and is intentionally not duplicated in GitHub.

The corpus provenance is recorded in [`benchmark/corpus/manifest.json`](../../corpus/manifest.json);
the ten papers are pinned to their arXiv versions and linked to their public
ICLR 2026 OpenReview records.

To reproduce the run locally:

```bash
python3 benchmark/run.py --workers 8 --thinking medium --out benchmark/runs/deepseek-40-fixed
python3 benchmark/evaluate.py benchmark/runs/deepseek-40-fixed/predictions.jsonl
```
