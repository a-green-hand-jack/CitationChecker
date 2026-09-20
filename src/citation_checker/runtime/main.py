from __future__ import annotations

import argparse
import json
from pathlib import Path

from citation_checker import __version__
from .doctor import run_doctor
from .runner import run_check
from .config import DEFAULT_MODEL, DEFAULT_PROVIDER
from .staging import inspect_manuscript
from .verify import verify_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="citationchecker")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("doctor", help="Check Pi and all three external tools")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("inspect", help="Inspect a PDF, TeX file, or LaTeX project without running the agent")
    p.add_argument("manuscript", type=Path)
    p.add_argument("--json", dest="json_out", type=Path)

    p = sub.add_parser("check", help="Run a citation audit in Pi")
    p.add_argument("manuscript", type=Path)
    p.add_argument("--out", type=Path)
    p.add_argument("--provider", default=DEFAULT_PROVIDER, help=f"Pi provider (default: {DEFAULT_PROVIDER})")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"Pi model (default: {DEFAULT_MODEL})")
    p.add_argument("--thinking")
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("verify", help="Mechanically verify citation-report.md + JSON")
    p.add_argument("report", type=Path)
    p.add_argument("--json", dest="json_out", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "doctor":
        raise SystemExit(run_doctor(as_json=args.json))
    if args.command == "inspect":
        data = inspect_manuscript(args.manuscript)
        text = json.dumps(data, indent=2)
        if args.json_out:
            args.json_out.write_text(text, encoding="utf-8")
        else:
            print(text)
        return
    if args.command == "check":
        raise SystemExit(
            run_check(
                args.manuscript,
                out=args.out,
                provider=args.provider,
                model=args.model,
                thinking=args.thinking,
                timeout=args.timeout,
                dry_run=args.dry_run,
            )
        )
    if args.command == "verify":
        ok, errors, data = verify_report(args.report)
        payload = {"ok": ok, "errors": errors, "data": data}
        if args.json_out:
            args.json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        else:
            print(json.dumps(payload, indent=2))
        raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
