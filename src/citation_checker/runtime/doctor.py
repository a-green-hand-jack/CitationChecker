from __future__ import annotations

import importlib
import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, version

@dataclass
class Check:
    name: str
    command: str
    found: bool
    detail: str = ""


def _probe(name: str, executable: str, args: list[str]) -> Check:
    path = shutil.which(executable)
    if not path:
        return Check(name=name, command=executable, found=False, detail="not found on PATH")
    try:
        proc = subprocess.run(
            [path, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=15,
            check=False,
        )
        first = (proc.stdout or "").strip().splitlines()
        detail = first[0] if first else f"exit={proc.returncode}"
        return Check(name=name, command=executable, found=True, detail=detail[:180])
    except Exception as exc:  # pragma: no cover
        return Check(name=name, command=executable, found=True, detail=f"probe failed: {exc}")


def _probe_python_package(name: str, module: str) -> Check:
    try:
        mod = importlib.import_module(module)
        try:
            installed = version(module)
        except PackageNotFoundError:
            installed = getattr(mod, "__version__", None) or "installed"
        return Check(name=name, command=f"python:{module}", found=True, detail=str(installed))
    except Exception as exc:
        return Check(name=name, command=f"python:{module}", found=False, detail=str(exc))


def run_doctor(as_json: bool = False) -> int:
    checks = [
        _probe_python_package("OpenAI Python SDK", "openai"),
        _probe("RefChecker", "academic-refchecker", ["--help"]),
        _probe("paper-search-mcp CLI", "paper-search", ["sources"]),
        _probe_python_package("PDF conversion", "pymupdf4llm"),
    ]
    ok = all(c.found for c in checks)
    payload = {"ok": ok, "checks": [asdict(c) for c in checks]}
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        for c in checks:
            print(f"{'OK' if c.found else 'MISS':4}  {c.name:22} {c.command:20} {c.detail}")
    return 0 if ok else 1
