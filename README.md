# CitationChecker

CitationChecker is a small **Pi-based citation-auditing agent** for a course project.
It checks two questions in an already-written academic manuscript:

1. **Is each cited reference real and correctly identified?**
2. **Does the cited paper actually support the claim made in the manuscript?**

It deliberately reuses existing tools instead of rebuilding them:

- [RefChecker](https://github.com/markrussinovich/refchecker) for reference existence and metadata validation.
- [paper-search-mcp](https://github.com/openags/paper-search-mcp) through its `paper-search` CLI for paper discovery, abstract/full-text retrieval, and evidence access.
- [PyMuPDF4LLM](https://github.com/pymupdf/pymupdf4llm) for **PDF-only manuscript normalization** into LLM-readable Markdown.

Pi is the agent harness. The model decides when to call scholarly tools and how to interpret their results. Python remains deterministic and shallow.

## Architecture

```text
                       manuscript input
                    /                    \
          LaTeX source/project          PDF only
                  |                        |
                  |                  PyMuPDF4LLM
                  |                        |
                  +-----------+------------+
                              |
                       staged manuscript
                              |
                              v
                      Pi / SKILL.md
                         /         \
                        /           \
                RefChecker        paper-search
             existence/metadata   evidence retrieval
                        \           /
                         \         /
                      claim-support judgment
                              |
                 citation-report.md + .json
```

The design principle is:

```text
CLI          = deterministic orchestration and input staging
Skill        = citation-auditing methodology
Pi           = agent reasoning and tool selection
PyMuPDF4LLM  = PDF-only input conversion
RefChecker   = bibliographic verification
paper-search = cited-paper evidence retrieval
```

## Installation

Prerequisites:

- Python 3.11+
- Pi (`pi`) configured with a model/provider
- RefChecker CLI (`academic-refchecker`)
- paper-search-mcp CLI (`paper-search`)

Install the scholarly tools:

```bash
pip install "academic-refchecker[llm]"
uv tool install paper-search-mcp
```

Install CitationChecker from this checkout. PyMuPDF4LLM is installed as a normal package dependency:

```bash
pip install -e .
```

Or:

```bash
./install.sh
```

Check the machine:

```bash
citationchecker doctor
```

`doctor` verifies Pi, RefChecker, paper-search, and PyMuPDF4LLM.

## Usage

### LaTeX project — preferred

When source is available, pass the project directory:

```bash
citationchecker check ./my-paper --provider <provider> --model <model>
```

CitationChecker finds the likely main `.tex`, stages the project, and Pi reads LaTeX directly. No PDF conversion is performed.

You can also pass a single file:

```bash
citationchecker check ./my-paper/main.tex
```

For a single `.tex`, sibling `.bib` files are staged automatically.

### PDF-only manuscript

```bash
citationchecker check paper.pdf --provider <provider> --model <model>
```

For PDF-only input, CitationChecker uses PyMuPDF4LLM once during staging:

```text
paper.pdf -> manuscript.md
```

Pi reads `manuscript.md` for citation contexts, while RefChecker still receives the original PDF.

### Inspect or dry-run

```bash
citationchecker inspect ./my-paper
citationchecker inspect paper.pdf
citationchecker check paper.pdf --dry-run
```

## Run layout

A PDF run contains:

```text
runs/<timestamp>-<paper>/
├── task.json
├── inventory.json
├── skill/
├── workspace/
│   ├── input/
│   │   ├── manifest.json
│   │   ├── paper.pdf
│   │   └── manuscript.md
│   └── output/
│       ├── refchecker-report.json
│       ├── citation-report.md
│       ├── citation-report.json
│       └── papers/
├── response.txt
└── receipt.json
```

A LaTeX-project run instead stages the source tree under `workspace/input/source/` and records the selected main file in `manifest.json`.

Verify an existing report mechanically:

```bash
citationchecker verify runs/.../workspace/output/citation-report.md
```

## Why this is an agent rather than a fixed pipeline

Input normalization is deterministic: use LaTeX directly when available; otherwise convert the PDF with PyMuPDF4LLM.

The citation audit itself is conditional. RefChecker is used first. Pi only escalates to `paper-search` when a real or recoverable cited paper needs semantic support checking. It can stop at the abstract when that is sufficient, or escalate to full text for quantitative or scope-sensitive claims.

The Python runtime does **not** decide whether a citation is scientifically valid.

## Output labels

Reference status:

- `VERIFIED`
- `NOT_FOUND`
- `METADATA_MISMATCH`
- `UNVERIFIABLE`

Claim support:

- `SUPPORTED`
- `PARTIALLY_SUPPORTED`
- `UNSUPPORTED`
- `INSUFFICIENT_EVIDENCE`

Evidence depth:

- `FULLTEXT`
- `ABSTRACT`
- `METADATA`
- `NONE`

## Supported manuscript inputs

- LaTeX project directory — preferred
- `.tex`
- `.pdf`
- `.md`
- `.txt`

The PDF conversion stage is intentionally isolated and replaceable. It does not make citation judgments.

## Micro benchmark

The repository includes a small diagnostic benchmark under `benchmark/`: **12 single-citation tasks** (6 positive + 6 manually mutated negative examples) grounded in real citation relationships from arXiv papers. The negatives cover metadata corruption, swapping in a real-but-irrelevant reference, and over-strengthening the manuscript claim.

Run the full benchmark:

```bash
python benchmark/run.py --provider <provider> --model <model>
python benchmark/evaluate.py benchmark/runs/predictions.jsonl
```

The scorer reports reference-status accuracy, support-label accuracy, overall exact match, and results by mutation type. See [`benchmark/README.md`](benchmark/README.md) for provenance and limitations.

## Scope

This is intentionally a small course-project agent. It does not implement a new search engine, embedding database, RAG framework, custom NLI model, or web UI.
