#!/usr/bin/env python3
"""Materialize the controlled benchmark cases as tiny LaTeX manuscripts."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_CASES = HERE / "cases.jsonl"
DEFAULT_OUT = HERE / "tasks"


def bib_escape(value: str) -> str:
    return value.replace("\\", "{\\textbackslash}").replace("&", r"\\&")


def bibtex(case: dict) -> str:
    ref = case["reference"]
    authors = " and ".join(ref["authors"])
    return (
        f"@article{{{case['citation_key']},\n"
        f"  author = {{{bib_escape(authors)}}},\n"
        f"  title = {{{bib_escape(ref['title'])}}},\n"
        f"  year = {{{ref['year']}}},\n"
        f"  url = {{{ref['url']}}},\n"
        f"  eprint = {{{ref['arxiv_id']}}},\n"
        f"  archivePrefix = {{arXiv}}\n"
        f"}}\n"
    )


def latex_escape(value: str) -> str:
    # Claims are selected plain-text abstract sentences. Keep punctuation and
    # Unicode readable while escaping TeX characters that change syntax.
    return (
        value.replace("\\", r"\textbackslash{}")
        .replace("&", r"\&")
        .replace("%", r"\%")
        .replace("#", r"\#")
        .replace("_", r"\_")
        .replace("{", r"\{")
        .replace("}", r"\}")
    )


def generate(cases_path: Path, out: Path, clean: bool) -> int:
    cases = [json.loads(line) for line in cases_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if clean and out.exists():
        for child in out.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    out.mkdir(parents=True, exist_ok=True)
    for case in cases:
        task = out / case["task_id"]
        task.mkdir(parents=True, exist_ok=True)
        (task / "main.tex").write_text(
            "\\documentclass{article}\n"
            "\\usepackage[numbers]{natbib}\n"
            "\\begin{document}\n"
            f"{latex_escape(case['claim'])}~\\citep{{{case['citation_key']}}}.\n"
            "\\bibliographystyle{plainnat}\n"
            "\\bibliography{references}\n"
            "\\end{document}\n",
            encoding="utf-8",
        )
        (task / "references.bib").write_text(bibtex(case), encoding="utf-8")
    print(f"generated {len(cases)} tasks under {out}")
    return len(cases)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--clean", action="store_true")
    args = p.parse_args()
    return 0 if generate(args.cases, args.out, args.clean) else 1


if __name__ == "__main__":
    raise SystemExit(main())
