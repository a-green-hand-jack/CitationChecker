from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from pathlib import Path

from .staging import stage_manuscript
from .verify import verify_report


def _run_id(manuscript: Path) -> str:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    stem = "".join(c if c.isalnum() or c in "-_" else "-" for c in manuscript.stem)[:48]
    return f"{stamp}-{stem}"


def _prompt() -> str:
    return (
        "Audit the academic manuscript in ./input using the loaded CitationChecker skill. "
        "Read ./input/manifest.json first. Use the staged LaTeX source directly, or the PyMuPDF4LLM-normalized Markdown when the input is PDF-only. "
        "Use RefChecker and paper-search exactly as instructed by the skill. "
        "Write the final human-readable report to ./output/citation-report.md and the machine-readable companion to "
        "./output/citation-report.json. Do not execute manuscript code."
    )


def run_check(
    manuscript: Path,
    *,
    out: Path | None,
    provider: str | None,
    model: str | None,
    thinking: str | None,
    timeout: int,
    dry_run: bool,
) -> int:
    package_dir = Path(__file__).resolve().parents[1]
    run_root = Path(os.environ.get("CITATIONCHECKER_RUN_ROOT", "runs")).resolve()
    run_dir = out.resolve() if out else run_root / _run_id(manuscript)

    stage_manuscript(manuscript, run_dir, package_dir)
    workspace = run_dir / "workspace"
    skill = run_dir / "skill"
    response = run_dir / "response.txt"

    task = {
        "manuscript": str(manuscript.resolve()),
        "provider": provider,
        "model": model,
        "thinking": thinking,
        "prompt": _prompt(),
    }
    (run_dir / "task.json").write_text(json.dumps(task, indent=2), encoding="utf-8")

    cmd = [
        "pi",
        "--no-skills",
        "--skill",
        str(skill),
        "--no-context-files",
        "--print",
        "--no-session",
    ]
    if provider:
        cmd += ["--provider", provider]
    if model:
        cmd += ["--model", model]
    if thinking:
        cmd += ["--thinking", thinking]
    cmd.append(_prompt())

    print(f"run directory: {run_dir}")
    print("command:", shlex.join(cmd))
    if dry_run:
        return 0

    with response.open("w", encoding="utf-8") as log, open(os.devnull, "r") as devnull:
        proc = subprocess.run(
            cmd,
            cwd=workspace,
            stdin=devnull,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )

    report = workspace / "output" / "citation-report.md"
    ok, errors, _ = verify_report(report)
    receipt = {
        "exit_code": proc.returncode,
        "verified": ok,
        "verify_errors": errors,
        "report": str(report),
    }
    (run_dir / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    if proc.returncode != 0:
        print(f"Pi exited with code {proc.returncode}; see {response}")
        return proc.returncode or 1
    if not ok:
        print("report verification failed:")
        for err in errors:
            print(f"- {err}")
        return 2
    print(f"report: {report}")
    return 0
