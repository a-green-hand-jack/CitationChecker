#!/usr/bin/env python3
"""Fetch and verify the pinned ICLR 2026 benchmark corpus from arXiv."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "corpus" / "manifest.json"
CHUNK = 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_range(url: str, start: int, end: int) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CitationChecker/0.1 (course benchmark)",
            "Range": f"bytes={start}-{end}",
        },
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = response.read()
        status = getattr(response, "status", 200)
        if status == 200 and start != 0:
            raise RuntimeError(f"server ignored range request for {url}")
        return payload


def download(url: str, destination: Path, expected_sha: str) -> None:
    if destination.exists() and sha256(destination) == expected_sha:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    first = fetch_range(url, 0, CHUNK - 1)
    # Range responses include Content-Range, but a one-shot response is also
    # accepted when a cache ignores the range for the first request.
    request = urllib.request.Request(url, headers={"User-Agent": "CitationChecker/0.1"})
    with urllib.request.urlopen(request, timeout=180) as response:
        total = int(response.headers.get("Content-Length", "0"))
    if len(first) >= total > 0:
        payload = first[:total]
    else:
        pieces = [first]
        start = len(first)
        while total <= 0 or start < total:
            end = start + CHUNK - 1 if total <= 0 else min(start + CHUNK - 1, total - 1)
            piece = fetch_range(url, start, end)
            if not piece:
                break
            pieces.append(piece)
            start += len(piece)
            if total <= 0 and len(piece) < CHUNK:
                break
        payload = b"".join(pieces)
    destination.write_bytes(payload)
    actual = sha256(destination)
    if actual != expected_sha:
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"sha256 mismatch for {destination}: {actual} != {expected_sha}")


def safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:*") as handle:
        members = handle.getmembers()
        root = destination.resolve()
        for member in members:
            if member.issym() or member.islnk():
                raise RuntimeError(f"links are not allowed in source archive: {member.name}")
            target = (destination / member.name).resolve()
            if not str(target).startswith(str(root) + "/"):
                raise RuntimeError(f"unsafe archive member: {member.name}")
        for member in members:
            handle.extract(member, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    for paper in data["papers"]:
        pdf = Path(paper["local_pdf"])
        archive = Path(paper["local_source_archive"])
        source = Path(paper["local_source_dir"])
        if not args.verify_only:
            download(paper["pdf_url"], pdf, paper["pdf_sha256"])
            download(paper["source_url"], archive, paper["source_sha256"])
            if not source.exists() or not any(source.rglob("*.tex")):
                safe_extract(archive, source)
        if not pdf.exists() or sha256(pdf) != paper["pdf_sha256"]:
            raise SystemExit(f"PDF verification failed: {pdf}")
        if not archive.exists() or sha256(archive) != paper["source_sha256"]:
            raise SystemExit(f"source archive verification failed: {archive}")
        tex = sorted(str(p.relative_to(source)) for p in source.rglob("*.tex"))
        if tex != sorted(paper["tex_files"]):
            raise SystemExit(f"TeX inventory mismatch for {paper['slug']}")
        print(f"verified {paper['slug']} ({paper['arxiv_id']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
