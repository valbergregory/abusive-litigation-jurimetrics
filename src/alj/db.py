"""DuckDB helpers: the database is a *derived* artefact, the Parquet files are the source of truth.

Two practical consequences, both handled here:

* DuckDB allows a single writer per file, and the ingestion steps are long. A step that only needs to publish
  views must not fail because another step holds the file — :func:`connect_or_memory` falls back to an in-memory
  connection and tells the caller, which then reports ``views_created: false`` in its log;
* every view is a one-line mapping from a name to a Parquet glob (:data:`VIEW_SOURCES`), so
  ``scripts/19_refresh_duckdb_views.py`` can rebuild the whole database from the Parquet at any time.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

#: view name → Parquet glob, relative to the repository root
VIEW_SOURCES: dict[str, str] = {
    "documents": "data/interim/stj_integras/meta/*.parquet",
    "document_text": "data/interim/stj_integras/text/*.parquet",
    "candidates": "data/interim/candidates/docs/*.parquet",
    "candidate_hits": "data/interim/candidates/hits/*.parquet",
    "bridge": "data/interim/bridge/*.parquet",
    "espelhos": "data/interim/espelhos/espelhos/*.parquet",
    "espelho_citations": "data/interim/espelhos/citations/*.parquet",
    "espelho_legislation": "data/interim/espelhos/legislation/*.parquet",
}


def connect_or_memory(path: str | Path, *, read_only: bool = False) -> tuple[duckdb.DuckDBPyConnection, bool]:
    """``(connection, is_file)``. Falls back to in-memory when the database file is locked by another step."""
    try:
        return duckdb.connect(str(path), read_only=read_only), True
    except (duckdb.IOException, duckdb.Error):
        return duckdb.connect(), False


def create_views(
    con: duckdb.DuckDBPyConnection, root: str | Path, only: list[str] | None = None
) -> dict[str, int | None]:
    """(Re)create the views whose Parquet exists. Returns ``{view: rows}``, ``None`` when there is no data yet."""
    root = Path(root)
    out: dict[str, int | None] = {}
    for view, pattern in VIEW_SOURCES.items():
        if only and view not in only:
            continue
        glob = (root / pattern).as_posix()
        if not list(Path(root / pattern).parent.glob(Path(pattern).name)):
            out[view] = None
            continue
        con.execute(f"CREATE OR REPLACE VIEW {view} AS SELECT * FROM read_parquet('{glob}')")
        out[view] = con.execute(f"SELECT count(*) FROM {view}").fetchone()[0]
    return out
