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
citationchecker check ./latex-project --provider <provider> --model <model>
```

or:

```bash
citationchecker check ./latex-project/main.tex --provider <provider> --model <model>
```

When only PDF is available:

```bash
citationchecker check manuscript.pdf --provider <provider> --model <model>
```

CitationChecker converts PDF-only input to `manuscript.md` with PyMuPDF4LLM before launching Pi. It does not perform this conversion for LaTeX inputs.

You can omit provider/model if Pi already has suitable defaults.

For a no-execution preview:

```bash
citationchecker check manuscript.pdf --dry-run
```

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

## Run the bundled micro benchmark

CitationChecker ships with 12 tiny single-citation tasks under `benchmark/tasks/`. To run them all:

```bash
python benchmark/run.py --provider <provider> --model <model>
python benchmark/evaluate.py benchmark/runs/predictions.jsonl
```

Use `--limit 2` for a quick end-to-end smoke test. The benchmark is diagnostic only; it is intentionally too small for broad performance claims.
