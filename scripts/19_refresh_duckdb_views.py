"""Utility — rebuild every DuckDB view from the Parquet files (the database is a derived artefact).

Useful after a step that ran while data/alj.duckdb was locked by another step (its log then says
``views_created: false``), or to recreate the database from scratch:

    uv run python scripts/19_refresh_duckdb_views.py [--db FILE] [--only candidates candidate_hits]

Prints (and logs) one row count per view; a view whose Parquet does not exist yet is reported as missing.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alj.db import VIEW_SOURCES, connect_or_memory, create_views  # noqa: E402

LOG = ROOT / "logs"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(ROOT / "data" / "alj.duckdb"))
    ap.add_argument("--only", nargs="*", choices=sorted(VIEW_SOURCES), help="refresh only these views")
    args = ap.parse_args(argv)

    con, is_file = connect_or_memory(args.db)
    if not is_file:
        print(f"{args.db} is locked by another process — stop the running step and try again", file=sys.stderr)
        return 3
    counts = create_views(con, ROOT, args.only)
    con.close()

    for view, rows in counts.items():
        print(f"  {view:<22} {'(no Parquet yet)' if rows is None else f'{rows:>12,} rows'}")
    out = {"run_at": dt.datetime.now().isoformat(timespec="seconds"), "db": str(Path(args.db).relative_to(ROOT)),
           "views": counts}
    LOG.mkdir(exist_ok=True)
    json.dump(out, open(LOG / "19_refresh_duckdb_views.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
