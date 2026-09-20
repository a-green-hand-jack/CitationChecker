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

`benchmark/cases.jsonl` is the source of truth. Every case has a `pair_id`, arXiv provenance, mutation type, and gold labels for both bibliographic status and semantic support. Keep the benchmark small and auditable. Negative cases should ideally change one factor only.

Run evaluator tests with:

```bash
pytest tests/test_benchmark.py
python benchmark/evaluate.py benchmark/example_predictions.jsonl
```

Do not paste long passages from source papers into the benchmark. Prefer short paraphrases plus arXiv identifiers and source URLs.
