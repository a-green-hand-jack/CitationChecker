---
name: citation-checker
description: Audit academic citations for bibliographic authenticity and claim support using RefChecker and paper-search-mcp; consume LaTeX directly or PyMuPDF4LLM-normalized Markdown for PDF-only manuscripts.
---

# CitationChecker

You are auditing citations in an already-written academic manuscript.

Your job is narrow:

1. verify whether cited references are real and whether their metadata matches;
2. verify whether each cited work supports the claim made at the citation location.

Do not review novelty, writing quality, venue fit, or the manuscript's own experiments.
Do not execute manuscript code.

Read `references/citation-checking.md` before starting.

## Inputs and normalization

Always read `./input/manifest.json` first.

The CLI stages one of these source forms:

- **LaTeX project**: `source_type=latex_project`. Read the staged `.tex` source directly. The manifest gives `main_tex` and `source_root`. Follow `\\input` / `\\include` files as needed. Read `.bib` files when useful.
- **Single TeX file**: `source_type=latex_file`. Read the `.tex` directly; sibling `.bib` files may also be staged.
- **PDF only**: `source_type=pdf`. The CLI has already invoked **PyMuPDF4LLM** and created `./input/manuscript.md`. Use that Markdown to locate citation contexts. The original PDF remains available for RefChecker.
- **Markdown/plain text**: read the staged original directly.

PyMuPDF4LLM is an input-conversion tool only. Do not use it to decide whether a citation is real or supportive.

The manifest also gives `refchecker_target`; use that exact staged path with RefChecker.

## Required scholarly tools

### RefChecker

Use RefChecker first on the `refchecker_target` from `manifest.json`:

```bash
academic-refchecker --paper <refchecker_target> \
  --report-file ./output/refchecker-report.json \
  --report-format json
```

RefChecker supports PDF and LaTeX inputs. Use its result for bibliographic existence and metadata checking. Do not replace RefChecker with your own web search.

### paper-search-mcp CLI

Use `paper-search` only after a reference is verified enough to investigate its support for a manuscript claim.

Search:

```bash
paper-search search "<title, DOI, or identifying query>" -n 5 -s semantic,crossref,openalex,arxiv
```

Read full text when supported:

```bash
paper-search read <source> <paper_id> -o ./output/papers
```

Download if useful:

```bash
paper-search download <source> <paper_id> -o ./output/papers
```

`paper-search search` and `download` return JSON; `read` returns text.
Prefer targeted sources over `all`.

## Required workflow

For each citation context that makes a substantive factual, quantitative,
methodological, causal, comparative, or prior-work claim:

1. Read the manuscript in its staged representation and identify the local claim.
2. Match the citation to the bibliography entry.
3. Consult the RefChecker result.
4. Assign one reference status:
   - `VERIFIED`
   - `NOT_FOUND`
   - `METADATA_MISMATCH`
   - `UNVERIFIABLE`
5. If the reference is `VERIFIED` or the mismatch is minor enough to identify the intended paper, use `paper-search` to retrieve the paper.
6. Prefer evidence in this order:
   - `FULLTEXT`
   - `ABSTRACT`
   - `METADATA`
   - `NONE`
7. Compare the manuscript claim with the strongest retrieved evidence.
8. Assign one support status:
   - `SUPPORTED`
   - `PARTIALLY_SUPPORTED`
   - `UNSUPPORTED`
   - `INSUFFICIENT_EVIDENCE`
   If the reference is `NOT_FOUND` or `UNVERIFIABLE`, assign
   `INSUFFICIENT_EVIDENCE` because no credible source was retrieved. Reserve
   `UNSUPPORTED` for a real retrieved source that contradicts or does not
   support the claim.
9. Record a short reason and, when available, the strongest evidence passage or a concise paraphrase with source location.

Do not infer support from title similarity alone. A paper being topically relevant is not enough. Pay special attention to changed numbers, population/scope shifts, causal language, modality (may vs. does), and claims generalized beyond the cited study.

## Tool-selection policy

This is an agent workflow, not a fixed batch script.

- PyMuPDF4LLM is used by deterministic staging only when the input is PDF-only; LaTeX never needs PDF conversion.
- RefChecker is the default first scholarly tool for bibliography validation.
- Do not call `paper-search` for a citation that RefChecker cannot identify at all, unless a metadata mismatch gives a clear intended paper to recover.
- Use abstract evidence when it directly resolves the claim.
- Escalate to full text when the abstract is insufficient, ambiguous, or the claim is quantitative/specific.
- If full text is unavailable, say `INSUFFICIENT_EVIDENCE`; do not guess.

## Output contract

Write both files:

- `./output/citation-report.md`
- `./output/citation-report.json`

The Markdown report must begin with:

```markdown
# Citation Audit Report
```

For each checked citation, include the claim, reference status, evidence depth,
support verdict, and reason.

The JSON must have this shape:

```json
{
  "manuscript": "...",
  "summary": {
    "total_citations": 0,
    "verified": 0,
    "not_found": 0,
    "metadata_mismatch": 0,
    "unverifiable": 0,
    "supported": 0,
    "partially_supported": 0,
    "unsupported": 0,
    "insufficient_evidence": 0
  },
  "citations": [
    {
      "citation": "[12]",
      "claim": "...",
      "reference": "...",
      "reference_status": "VERIFIED",
      "evidence_depth": "FULLTEXT",
      "support": "SUPPORTED",
      "evidence": "...",
      "reason": "..."
    }
  ]
}
```

`summary.total_citations` must equal the number of objects in `citations`.
