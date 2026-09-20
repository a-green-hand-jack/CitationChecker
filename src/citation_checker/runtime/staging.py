from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


IGNORED_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "__pycache__", "build", "dist", "runs"}
IGNORED_SUFFIXES = {".aux", ".log", ".out", ".toc", ".synctex.gz", ".fls", ".fdb_latexmk"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_tree(path: Path) -> str:
    """Hash relevant project files deterministically by relative path + bytes."""
    h = hashlib.sha256()
    for file in sorted(p for p in path.rglob("*") if p.is_file() and not _ignored(p, path)):
        rel = file.relative_to(path).as_posix().encode()
        h.update(rel)
        h.update(b"\0")
        with file.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        h.update(b"\0")
    return h.hexdigest()


def _ignored(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if any(part in IGNORED_DIRS for part in rel.parts):
        return True
    return any(path.name.endswith(suffix) for suffix in IGNORED_SUFFIXES)


def _find_main_tex(project: Path) -> Path:
    tex_files = sorted(p for p in project.rglob("*.tex") if p.is_file() and not _ignored(p, project))
    if not tex_files:
        raise ValueError(f"No .tex files found in LaTeX project: {project}")

    candidates: list[Path] = []
    for tex in tex_files:
        text = tex.read_text(encoding="utf-8", errors="replace")
        if "\\documentclass" in text and "\\begin{document}" in text:
            candidates.append(tex)

    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        preferred = [p for p in candidates if p.name.lower() in {"main.tex", "paper.tex", "manuscript.tex"}]
        return preferred[0] if preferred else candidates[0]

    preferred = [p for p in tex_files if p.name.lower() in {"main.tex", "paper.tex", "manuscript.tex"}]
    return preferred[0] if preferred else tex_files[0]


def _copy_latex_project(src: Path, dst: Path) -> None:
    def ignore(directory: str, names: list[str]) -> set[str]:
        base = Path(directory)
        ignored: set[str] = set()
        for name in names:
            candidate = base / name
            if name in IGNORED_DIRS:
                ignored.add(name)
            elif candidate.is_file() and any(name.endswith(suffix) for suffix in IGNORED_SUFFIXES):
                ignored.add(name)
        return ignored

    shutil.copytree(src, dst, ignore=ignore)


def _convert_pdf_to_markdown(src: Path, dst: Path) -> dict:
    """Use the external PyMuPDF4LLM package for LLM-ready PDF normalization."""
    import pymupdf
    import pymupdf4llm

    markdown = pymupdf4llm.to_markdown(str(src))
    if not isinstance(markdown, str):
        raise RuntimeError("PyMuPDF4LLM returned non-string Markdown output")
    dst.write_text(markdown, encoding="utf-8")
    with pymupdf.open(str(src)) as doc:
        pages = len(doc)
    return {
        "converter": "pymupdf4llm",
        "pages": pages,
        "normalized_markdown": str(dst),
    }


def inspect_manuscript(path: Path) -> dict:
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(path)

    if path.is_dir():
        main_tex = _find_main_tex(path)
        tex_files = [p for p in path.rglob("*.tex") if p.is_file() and not _ignored(p, path)]
        bib_files = [p for p in path.rglob("*.bib") if p.is_file() and not _ignored(p, path)]
        return {
            "path": str(path),
            "name": path.name,
            "source_type": "latex_project",
            "main_tex": str(main_tex.relative_to(path)),
            "tex_files": len(tex_files),
            "bib_files": len(bib_files),
            "sha256": sha256_tree(path),
        }

    suffix = path.suffix.lower()
    info = {
        "path": str(path),
        "name": path.name,
        "suffix": suffix,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }
    if suffix == ".pdf":
        info["source_type"] = "pdf"
        try:
            import pymupdf

            with pymupdf.open(str(path)) as doc:
                info["pages"] = len(doc)
            info["convertible"] = True
        except Exception as exc:  # pragma: no cover - environment/file dependent
            info["convertible"] = False
            info["conversion_error"] = str(exc)
    elif suffix == ".tex":
        info["source_type"] = "latex_file"
    elif suffix in {".txt", ".md"}:
        info["source_type"] = "text"
    else:
        raise ValueError("Supported manuscript inputs: PDF, .tex, .md, .txt, or a LaTeX project directory")
    return info


def stage_manuscript(manuscript: Path, run_dir: Path, skill_dir: Path) -> dict:
    manuscript = manuscript.resolve()
    run_dir.mkdir(parents=True, exist_ok=False)

    input_dir = run_dir / "workspace" / "input"
    output_dir = run_dir / "workspace" / "output"
    frozen_skill = run_dir / "skill"
    input_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)

    base_info = inspect_manuscript(manuscript)
    source_type = base_info["source_type"]
    manifest: dict = {"source_type": source_type}

    if source_type == "latex_project":
        project_dst = input_dir / "source"
        _copy_latex_project(manuscript, project_dst)
        main_rel = Path(base_info["main_tex"])
        staged_main = project_dst / main_rel
        manifest.update(
            {
                "original_name": manuscript.name,
                "source_root": "./input/source",
                "main_tex": f"./input/source/{main_rel.as_posix()}",
                "refchecker_target": f"./input/source/{main_rel.as_posix()}",
                "reading_mode": "latex_source",
            }
        )
    elif source_type == "latex_file":
        staged = input_dir / manuscript.name
        shutil.copy2(manuscript, staged)
        copied_bibs: list[str] = []
        for bib in sorted(manuscript.parent.glob("*.bib")):
            dst = input_dir / bib.name
            if dst != staged:
                shutil.copy2(bib, dst)
                copied_bibs.append(f"./input/{bib.name}")
        manifest.update(
            {
                "original_name": manuscript.name,
                "main_tex": f"./input/{staged.name}",
                "refchecker_target": f"./input/{staged.name}",
                "reading_mode": "latex_source",
                "bibliography_files": copied_bibs,
            }
        )
    elif source_type == "pdf":
        staged = input_dir / manuscript.name
        shutil.copy2(manuscript, staged)
        markdown_path = input_dir / "manuscript.md"
        conversion = _convert_pdf_to_markdown(staged, markdown_path)
        manifest.update(
            {
                "original_name": manuscript.name,
                "pdf": f"./input/{staged.name}",
                "refchecker_target": f"./input/{staged.name}",
                "reading_mode": "normalized_markdown",
                "normalized_markdown": "./input/manuscript.md",
                "conversion": {
                    "tool": "PyMuPDF4LLM",
                    "output": "./input/manuscript.md",
                    "pages": conversion["pages"],
                },
            }
        )
    elif source_type == "text":
        staged = input_dir / manuscript.name
        shutil.copy2(manuscript, staged)
        manifest.update(
            {
                "original_name": manuscript.name,
                "text": f"./input/{staged.name}",
                "refchecker_target": f"./input/{staged.name}",
                "reading_mode": "plain_text",
            }
        )
    else:  # pragma: no cover - inspect_manuscript guards this
        raise AssertionError(source_type)

    (input_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    frozen_skill.mkdir(parents=True)
    shutil.copy2(skill_dir / "SKILL.md", frozen_skill / "SKILL.md")
    shutil.copytree(skill_dir / "references", frozen_skill / "references")

    inventory = {**base_info, "staged_manifest": manifest}
    (run_dir / "inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    return inventory
