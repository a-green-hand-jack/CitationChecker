#!/usr/bin/env python3
"""Create the controlled ICLR 2026 citation cases from the pinned corpus manifest.

The case rows are deliberately explicit: each paper gets one clean citation and
three hand-specified mutations (wrong metadata, fabricated reference, and a
real but irrelevant reference).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "corpus" / "manifest.json"
CASES = ROOT / "cases.jsonl"

# These are short, manually selected claims from each pinned arXiv abstract.
CLAIMS = {
    "atlas-transfer-scaling": "Scaling laws research has focused overwhelmingly on English, yet the most prominent AI models explicitly serve billions of international users.",
    "transformers-succinct": "We study succinctness as a measure of the expressive power of transformers.",
    "rl-dataset-distillation": "Given a training dataset, the goal of dataset distillation is to derive a synthetic dataset such that models trained on the latter perform as well as those trained on the training dataset.",
    "time-series-calibration": "The recent development of foundation models for time series data has generated considerable interest in using such models across a variety of applications.",
    "black-box-privacy-attacks": "Multitask learning (MTL) has emerged as a powerful paradigm that leverages similarities among multiple learning tasks, each with insufficient samples to train a standalone model, to solve them simultaneously while minimizing data sharing across users and organizations.",
    "kolmogorov-transformers": "The Minimum Description Length (MDL) principle offers a formal framework for applying Occam's razor in machine learning.",
    "evolutionary-transformer-learning": "The success of Transformers lies in their ability to improve inference through two complementary strategies: the permanent refinement of model parameters via in-weight learning (IWL), and the ephemeral modulation of inferences via in-context learning (ICL), which leverages contextual information maintained in the model's activations.",
    "adversarial-mdp-dec": "We study decision making with structured observation (DMSO).",
    "dp-sgd-square-roots": "Matrix factorization mechanisms for differentially private training have emerged as a promising approach to improve model utility under privacy constraints.",
    "bayes-adaptive-rl-reasoning": "Large Language Models (LLMs) trained via Reinforcement Learning (RL) have exhibited strong reasoning capabilities and emergent reflective behaviors, such as rethinking and error correction, as a form of in-context exploration.",
}


def base_reference(paper: dict) -> dict:
    return {
        "title": paper["title"],
        "authors": paper["authors"],
        "year": int(paper["published"][:4]),
        "arxiv_id": paper["arxiv_id"],
        "url": paper["arxiv_abs_url"],
    }


def row(paper: dict, *, task_id: str, mutation_type: str, construction: str,
        claim: str, citation_key: str, reference: dict, gold_ref: str,
        gold_support: str, mutation: dict | None, notes: str) -> dict:
    return {
        "task_id": task_id,
        "paper_id": paper["slug"],
        "source_paper": {
            "title": paper["title"],
            "authors": paper["authors"],
            "arxiv_id": paper["arxiv_id"],
            "arxiv_url": paper["arxiv_abs_url"],
            "openreview_id": paper["openreview_id"],
            "openreview_url": paper["openreview_url"],
            "status": paper["status"],
            "local_pdf": paper["local_pdf"],
            "local_source_dir": paper["local_source_dir"],
        },
        "construction": construction,
        "mutation_type": mutation_type,
        "mutation": mutation,
        "claim": claim,
        "claim_provenance": "pinned arXiv abstract, manually selected sentence",
        "citation_key": citation_key,
        "reference": reference,
        "gold_reference_status": gold_ref,
        "gold_support": gold_support,
        "notes": notes,
    }


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    papers = manifest["papers"]
    assert len(papers) == 10, f"expected 10 papers, found {len(papers)}"
    refs = {p["slug"]: base_reference(p) for p in papers}
    rows: list[dict] = []
    for i, paper in enumerate(papers):
        slug = paper["slug"]
        claim = CLAIMS[slug]
        ref = refs[slug]
        key = f"self_{slug.replace('-', '_')}"
        rows.append(row(
            paper, task_id=f"{slug}-valid", mutation_type="none", construction="positive",
            claim=claim, citation_key=key, reference=ref,
            gold_ref="VERIFIED", gold_support="SUPPORTED", mutation=None,
            notes="Clean self-reference to the exact pinned arXiv version; claim is from that paper's abstract.",
        ))
        wrong_year = ref["year"] - 1
        rows.append(row(
            paper, task_id=f"{slug}-wrong-year", mutation_type="metadata_corruption", construction="negative",
            claim=claim, citation_key=key,
            reference={**ref, "year": wrong_year},
            gold_ref="METADATA_MISMATCH", gold_support="SUPPORTED",
            mutation={"field": "year", "original": ref["year"], "mutated": wrong_year},
            notes="Only the cited publication year is changed; the exact paper remains recoverable by title and arXiv id.",
        ))
        fake_key = f"hallucinated_{slug.replace('-', '_')}"
        fake = {
            "title": f"{paper['title']} — Extended Results and Universal Guarantees",
            "authors": ["A. Nonexistent", "B. Fabricated"],
            "year": ref["year"],
            "arxiv_id": "9999.99999",
            "url": "https://arxiv.org/abs/9999.99999",
        }
        rows.append(row(
            paper, task_id=f"{slug}-hallucinated", mutation_type="hallucinated_reference", construction="negative",
            claim=claim, citation_key=fake_key, reference=fake,
            gold_ref="NOT_FOUND", gold_support="INSUFFICIENT_EVIDENCE",
            mutation={"kind": "fabricated_reference", "replaces": key},
            notes="The title, authors, and arXiv id are fabricated and do not identify a real work.",
        ))
        swap_paper = papers[(i + 1) % len(papers)]
        swap_ref = refs[swap_paper["slug"]]
        swap_key = f"swap_{swap_paper['slug'].replace('-', '_')}"
        rows.append(row(
            paper, task_id=f"{slug}-real-swap", mutation_type="reference_swap", construction="negative",
            claim=claim, citation_key=swap_key, reference=swap_ref,
            gold_ref="VERIFIED", gold_support="UNSUPPORTED",
            mutation={"kind": "real_reference_swap", "replaces": key, "replacement_paper": swap_paper["slug"]},
            notes="A real ICLR 2026 paper from the corpus replaces the intended self-reference; it is unrelated to this claim.",
        ))
    CASES.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} cases to {CASES}")


if __name__ == "__main__":
    main()
