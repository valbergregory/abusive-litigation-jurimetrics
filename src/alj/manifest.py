"""The download manifest: one SHA-256 line per raw file (CLAUDE.md §7, policy §15).

Single implementation on purpose. The manifest is a reproducibility artefact, so its column order must not drift
between steps: ``sha256 · bytes · date · licence · source · file``, tab-separated, appended once per file name.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

MANIFEST_COLUMNS: tuple[str, ...] = ("sha256", "bytes", "date", "licence", "source", "file")
DEFAULT_LICENCE = "CC-BY (STJ open data)"


def file_sha256(path: str | Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def file_identity(path: str | Path, root: str | Path | None = None) -> str:
    """The value of the ``file`` column: the path relative to ``root`` when possible, else the bare name.

    The identity must be the *path*, not the name: the ten judging bodies all publish a ``20220531.json``, and
    deduplicating by name would silently drop nine of them.
    """
    path = Path(path)
    if root is not None:
        try:
            return path.resolve().relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            pass
    return path.name


def manifest_line(
    path: str | Path, source: str, licence: str = DEFAULT_LICENCE, root: str | Path | None = None
) -> str:
    """The tab-separated line for one file, in :data:`MANIFEST_COLUMNS` order."""
    path = Path(path)
    return "\t".join([
        file_sha256(path),
        str(path.stat().st_size),
        dt.date.today().isoformat(),
        licence,
        source,
        file_identity(path, root),
    ])


def record_download(
    path: str | Path,
    source: str,
    manifest: str | Path,
    *,
    licence: str = DEFAULT_LICENCE,
    seen: set[str] | None = None,
    root: str | Path | None = None,
) -> bool:
    """Append the line for ``path`` unless that path is already recorded. Returns True when appended.

    ``seen`` lets a long run keep the identities in memory instead of re-reading the manifest per file; when it is
    None the manifest itself is read, so the function stays correct on its own.
    """
    path = Path(path)
    manifest = Path(manifest)
    name = file_identity(path, root)
    if seen is not None:
        if name in seen:
            return False
    elif manifest.exists():
        recorded = {line.rsplit("\t", 1)[-1] for line in manifest.read_text(encoding="utf-8").splitlines()}
        if name in recorded:
            return False
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest, "a", encoding="utf-8") as fh:
        fh.write(manifest_line(path, source, licence, root) + "\n")
    if seen is not None:
        seen.add(name)
    return True
