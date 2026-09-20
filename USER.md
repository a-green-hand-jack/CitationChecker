# CitationChecker User Guide

## 1. Install prerequisites

Configure Pi first, then install the two scholarly CLIs:

```bash
pip install "academic-refchecker[llm]"
uv tool install paper-search-mcp
```

Install CitationChecker. This also installs PyMuPDF4LLM for PDF-only inputs:

```bash
pip install -e .
```

## 2. Check your environment

```bash
citationchecker doctor
```

The check covers:

- `pi`
- `academic-refchecker`
- `paper-search`
- Python package `pymupdf4llm`

Optional provider keys for RefChecker and paper-search-mcp stay in their normal environment/configuration. CitationChecker does not store credentials.

## 3. Choose the best manuscript input

Prefer LaTeX source when available:

```bash
citationchecker check ./latex-project
```

or:

```bash
citationchecker check ./latex-project/main.tex
```

When only PDF is available:

```bash
citationchecker check manuscript.pdf
```

CitationChecker converts PDF-only input to `manuscript.md` with PyMuPDF4LLM before launching Pi. It does not perform this conversion for LaTeX inputs.

Development defaults are `apex-deepseek/deepseek-v4-flash`. Use `--provider` and
`--model` to override them.

For a no-execution preview:

```bash
citationchecker check manuscript.pdf --dry-run
```

Bounded runs accept `--max-steps`, `--max-tokens`, `--max-output-tokens`, and
`--timeout`. `--disable-paper-search` is the paired ablation mode. A run is
accepted only when `receipt.json` says `stop_reason=completed`; inspect
`trajectory.jsonl` for the redacted replayable event log.

## 4. Inspect staging metadata

```bash
citationchecker inspect ./latex-project
citationchecker inspect manuscript.pdf
```

Each run writes `workspace/input/manifest.json`, which tells Pi whether it should read LaTeX directly or the normalized Markdown.

## 5. Read the result

The important files are:

```text
workspace/output/citation-report.md
workspace/output/citation-report.json
```

The Markdown report is for humans. The JSON report contains the same citation-level labels for scripts or grading.

## 6. Verify output structure

```bash
citationchecker verify /path/to/citation-report.md
```

This only checks the report contract. It does not re-judge scientific correctness.

## Run the controlled benchmark

CitationChecker ships with 40 controlled LaTeX citation cards derived from ten
real ICLR 2026 papers. The original arXiv TeX sources and compiled PDFs are
stored under `benchmark/corpus/`. To run all cases with the development model:

```bash
python benchmark/run.py --workers 8
python benchmark/evaluate.py benchmark/runs/predictions.jsonl
```

Use `--limit 4` for one mutation of each type and `--workers 1` for a serial
run. To run the paired mechanism comparison:

```bash
python benchmark/ablate.py --per-mutation 1
```

The benchmark is controlled and diagnostic; it is not a broad performance estimate.
