import json
from pathlib import Path

import citation_checker.runtime.staging as staging


def _skill_dir(tmp_path: Path) -> Path:
    skill = tmp_path / "skill-src"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
    (skill / "references" / "citation-checking.md").write_text("# Ref\n", encoding="utf-8")
    return skill


def test_stage_latex_project_uses_source_directly(tmp_path: Path):
    project = tmp_path / "paper"
    project.mkdir()
    (project / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nHello \\cite{x}.\n\\end{document}\n",
        encoding="utf-8",
    )
    (project / "refs.bib").write_text("@article{x, title={X}}\n", encoding="utf-8")
    (project / "main.aux").write_text("build junk", encoding="utf-8")

    run_dir = tmp_path / "run"
    inventory = staging.stage_manuscript(project, run_dir, _skill_dir(tmp_path))
    manifest = json.loads((run_dir / "workspace/input/manifest.json").read_text())

    assert inventory["source_type"] == "latex_project"
    assert manifest["reading_mode"] == "latex_source"
    assert manifest["main_tex"] == "./input/source/main.tex"
    assert (run_dir / "workspace/input/source/refs.bib").exists()
    assert not (run_dir / "workspace/input/source/main.aux").exists()
    assert not (run_dir / "workspace/input/manuscript.md").exists()


def test_stage_single_tex_copies_sibling_bib(tmp_path: Path):
    src = tmp_path / "main.tex"
    src.write_text("\\documentclass{article}\n\\begin{document}x\\end{document}", encoding="utf-8")
    (tmp_path / "refs.bib").write_text("@article{x,title={X}}", encoding="utf-8")

    run_dir = tmp_path / "run"
    staging.stage_manuscript(src, run_dir, _skill_dir(tmp_path))
    manifest = json.loads((run_dir / "workspace/input/manifest.json").read_text())

    assert manifest["reading_mode"] == "latex_source"
    assert "./input/refs.bib" in manifest["bibliography_files"]


def test_stage_pdf_uses_pymupdf4llm_converter(tmp_path: Path, monkeypatch):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"fake-pdf-for-mocked-converter")

    def fake_convert(src: Path, dst: Path):
        dst.write_text("# Converted\nclaim [1]", encoding="utf-8")
        return {"converter": "pymupdf4llm", "pages": 2, "normalized_markdown": str(dst)}

    monkeypatch.setattr(staging, "_convert_pdf_to_markdown", fake_convert)
    monkeypatch.setattr(
        staging,
        "inspect_manuscript",
        lambda path: {
            "path": str(path.resolve()),
            "name": path.name,
            "suffix": ".pdf",
            "size_bytes": path.stat().st_size,
            "sha256": "fake",
            "source_type": "pdf",
            "pages": 2,
            "convertible": True,
        },
    )

    run_dir = tmp_path / "run"
    staging.stage_manuscript(pdf, run_dir, _skill_dir(tmp_path))
    manifest = json.loads((run_dir / "workspace/input/manifest.json").read_text())

    assert manifest["reading_mode"] == "normalized_markdown"
    assert manifest["conversion"]["tool"] == "PyMuPDF4LLM"
    assert (run_dir / "workspace/input/manuscript.md").exists()
