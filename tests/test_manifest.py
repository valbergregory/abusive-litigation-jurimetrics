"""Tests for the download manifest (alj.manifest) and for the committed logs/raw_hashes.tsv.

The manifest is the audit trail required by CLAUDE.md §7 and policy §15, so its column order must stay stable
across steps 10, 11 and 12 — the repository-level test below fails if any step ever writes a different layout.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from alj.manifest import MANIFEST_COLUMNS, file_sha256, manifest_line, record_download

REPO_MANIFEST = Path(__file__).resolve().parents[1] / "logs" / "raw_hashes.tsv"


def test_manifest_line_has_the_canonical_columns(tmp_path: Path):
    f = tmp_path / "20260630.json"
    f.write_bytes(b"abc")
    parts = manifest_line(f, "https://example.org/x").split("\t")
    assert len(parts) == len(MANIFEST_COLUMNS) == 6
    sha, size, date, licence, source, name = parts
    assert sha == file_sha256(f) and len(sha) == 64
    assert size == "3" and date == dt.date.today().isoformat()
    assert licence.startswith("CC-BY") and source == "https://example.org/x" and name == f.name


def test_record_download_is_idempotent_per_file_name(tmp_path: Path):
    manifest = tmp_path / "hashes.tsv"
    f = tmp_path / "a.json"
    f.write_bytes(b"x")
    assert record_download(f, "src", manifest) is True
    assert record_download(f, "src", manifest) is False
    assert len(manifest.read_text(encoding="utf-8").splitlines()) == 1


def test_record_download_uses_the_seen_set_when_given(tmp_path: Path):
    manifest = tmp_path / "hashes.tsv"
    f = tmp_path / "a.json"
    f.write_bytes(b"x")
    seen: set[str] = set()
    assert record_download(f, "src", manifest, seen=seen) is True
    assert seen == {"a.json"}
    assert record_download(f, "src", manifest, seen=seen) is False


def test_record_download_creates_the_parent_directory(tmp_path: Path):
    manifest = tmp_path / "logs" / "hashes.tsv"
    f = tmp_path / "a.json"
    f.write_bytes(b"x")
    assert record_download(f, "src", manifest) is True
    assert manifest.exists()


def test_repository_manifest_is_consistent():
    lines = REPO_MANIFEST.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("#")
    assert lines[1].split("\t") == list(MANIFEST_COLUMNS)
    rows = [ln.split("\t") for ln in lines[2:] if ln.strip()]
    assert rows, "the manifest must not be empty"
    for row in rows:
        assert len(row) == 6, row[:2]
        assert len(row[0]) == 64 and all(c in "0123456789abcdef" for c in row[0]), row[0]
        assert row[1].isdigit()
        dt.date.fromisoformat(row[2])
    names = [row[5] for row in rows]
    assert len(names) == len(set(names)), "a file is recorded twice"
