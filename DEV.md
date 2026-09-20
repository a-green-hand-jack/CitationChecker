# Development Guide

CitationChecker is intentionally split into two planes.

## Product definition

- `src/citation_checker/SKILL.md`
- `src/citation_checker/references/`

These files define how the agent audits citations.

## Deterministic runtime

- `runtime/staging.py`: detect source type, stage LaTeX, or convert PDF to Markdown with PyMuPDF4LLM; freeze skill
- `runtime/doctor.py`: detect Pi, RefChecker, paper-search, and PyMuPDF4LLM
- `runtime/runner.py`: launch Pi headlessly
- `runtime/verify.py`: validate final artifact shape
- `runtime/main.py`: CLI parser

Do not move scientific judgment into Python. If the definition of `SUPPORTED` or how evidence should be retrieved changes, change the skill/reference guide.

PyMuPDF4LLM is allowed in Python because it is a deterministic input-conversion dependency, not a scientific verifier.

## Staging contract

Every run writes:

```text
workspace/input/manifest.json
```

Important fields include:

- `source_type`
- `refchecker_target`
- `reading_mode`
- `main_tex` for LaTeX, when applicable
- `normalized_markdown` for PDF, when applicable

For a LaTeX project directory, the original project structure is copied under `workspace/input/source/`, excluding common VCS/build/cache directories and LaTeX build artifacts.

## Local checks

```bash
python -m compileall src
PYTHONPATH=src python -m citation_checker.runtime.main --help
PYTHONPATH=src python -m citation_checker.runtime.main doctor
pytest
```

`doctor` may return nonzero on development machines that do not have Pi or the external scholarly tools installed; that is expected.

## Benchmark development

`benchmark/corpus/manifest.json` pins ten ICLR 2026 OpenReview records to exact
arXiv versions and records the PDF/source hashes. Verify the materialized corpus
with:

```bash
python benchmark/download_corpus.py --verify-only
```

`benchmark/cases.jsonl` is the gold source of truth. It contains 40 cases (four
per paper): a valid self-reference, a wrong-year mutation, a fabricated
reference, and a swap to another real corpus paper. The claim text is a short,
manually selected sentence from the pinned arXiv abstract. Rebuild the LaTeX
fixtures with:

```bash
python benchmark/create_cases.py
python benchmark/generate_tasks.py --clean
```

Do not execute manuscript code. The benchmark task fixtures are citation cards;
the full TeX source and compiled PDF remain available under `benchmark/corpus/`
for provenance and future full-paper fixtures.

Run evaluator checks with:

```bash
pytest tests/test_benchmark.py
python benchmark/evaluate.py benchmark/example_predictions.jsonl
```

Development benchmark runs default to `apex-deepseek/deepseek-v4-flash`; pass
`--provider` and `--model` only when intentionally testing another route.
Use `--workers` to control parallel provider-backed cases.
