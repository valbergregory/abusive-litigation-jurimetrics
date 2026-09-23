"""Phase 1, step 12 — build the numeroRegistro ↔ numeroUnico (CNJ) bridge from the STJ open data.

Sources, in order of coverage (feasibility report §4):
  * the **acervo em tramitação** snapshot already in this repository (data/raw/stj/acervo_processos_*.json.gz,
    downloaded 2026-09-05 with SHA-256) — pending caseload only, so recent decisions link well and old ones do not;
  * the **atas de distribuição** (every case distributed since 2023-06-30) — the historical bridge. They are NOT
    downloaded here: pass `--atas DIR` with a local mirror. Downloading the 1.005 files (~4.2 GB) is a separate,
    explicitly authorised step (RUNBOOK, step 12).

Only bridge fields are read (`alj.bridge.ACERVO_FIELDS` / `ATA_FIELDS`); party and lawyer fields are never
touched (CLAUDE.md §§4–5) and the rapporteur is stored as a salted hash.

Writes:
  data/interim/bridge/<source>_<file>.parquet   BRIDGE_SCHEMA rows
  data/alj.duckdb                               view `bridge` + table `bridge_log`
  logs/raw_hashes.tsv                           SHA-256 of every file read
  logs/12_ingest_stj_bridge.json                counts, coverage against the íntegras, per-tribunal breakdown

Usage:  uv run python scripts/12_ingest_stj_bridge.py [--acervo FILE] [--atas DIR] [--limit N] [--force]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):  # the Windows console is cp1252; logs are always UTF-8
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alj.bridge import read_bridge  # noqa: E402
from alj.db import connect_or_memory, create_views  # noqa: E402
from alj.manifest import record_download  # noqa: E402

RAW = ROOT / "data" / "raw" / "stj"
OUT = ROOT / "data" / "interim" / "bridge"
META = (ROOT / "data" / "interim" / "stj_integras" / "meta" / "*.parquet").as_posix()
CAND = (ROOT / "data" / "interim" / "candidates" / "docs" / "*.parquet").as_posix()
DB = ROOT / "data" / "alj.duckdb"
LOG = ROOT / "logs"
HASHES = LOG / "raw_hashes.tsv"
SALT_FILE = ROOT / ".secrets" / "salt"


def load_salt() -> bytes:
    SALT_FILE.parent.mkdir(exist_ok=True)
    if not SALT_FILE.exists():
        SALT_FILE.write_bytes(os.urandom(32))
    return SALT_FILE.read_bytes()



def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--acervo", help="acervo snapshot .json.gz (default: the newest in data/raw/stj)")
    ap.add_argument("--atas", help="directory with ata*.json files (not downloaded by this script)")
    ap.add_argument("--limit", type=int, help="read at most N records per file (smoke run)")
    ap.add_argument("--force", action="store_true", help="re-read files already ingested")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    salt = load_salt()
    OUT.mkdir(parents=True, exist_ok=True)
    LOG.mkdir(exist_ok=True)

    todo: list[tuple[str, Path]] = []
    acervo = Path(args.acervo) if args.acervo else next(
        iter(sorted(RAW.glob("acervo_processos_tramitando_*.json.gz"), reverse=True)), None
    )
    if acervo and acervo.exists():
        todo.append(("acervo", acervo))
    else:
        print(f"no acervo snapshot in {RAW} — pass --acervo FILE", file=sys.stderr)
    if args.atas:
        folder = Path(args.atas)
        atas = sorted({p for pat in ("ata*.json", "ata*.json.gz", "ata*[0-9]") for p in folder.glob(pat)})
        todo.extend(("ata", p) for p in atas)
        print(f"atas: {len(atas)} file(s) in {args.atas}")
    else:
        sample = RAW / "atas_ata20250101.json"
        if sample.exists():
            todo.append(("ata", sample))
            print(f"no --atas DIR: using the single sample {sample.name} (the 4.2 GB mirror is a separate step)")
    if not todo:
        return 2

    t_all = time.time()
    per_file: list[dict] = []
    for source, path in todo:
        target = OUT / f"{source}_{path.name.split('.')[0]}.parquet"
        if target.exists() and not args.force and not args.limit:
            print(f"  skip {path.name} (already ingested)")
            per_file.append({"source": source, "file": path.name, "rows": None, "skipped": True})
            continue
        t0 = time.time()
        frame = read_bridge(path, source=source, salt=salt, limit=args.limit)
        if frame.height:
            frame.write_parquet(target)
        record_download(path, "local mirror (already hashed in phase 0/1)", HASHES, root=ROOT)
        per_file.append({"source": source, "file": path.name, "rows": frame.height,
                         "seconds": round(time.time() - t0, 1), "skipped": False})
        print(f"  {path.name}: {frame.height} bridge rows ({round(time.time() - t0, 1)}s)", flush=True)

    if not list(OUT.glob("*.parquet")):
        print("nothing written", file=sys.stderr)
        return 1
    con, is_file = connect_or_memory(DB)  # the database may be locked by another step; stats still work
    create_views(con, ROOT, ["bridge"])
    if is_file:
        con.execute("""CREATE TABLE IF NOT EXISTS bridge_log (
                           source VARCHAR, file VARCHAR, rows INTEGER, ingested_at TIMESTAMP)""")
        for r in per_file:
            if not r["skipped"]:
                con.execute("DELETE FROM bridge_log WHERE file = ?", [r["file"]])
                con.execute("INSERT INTO bridge_log VALUES (?, ?, ?, now())", [r["source"], r["file"], r["rows"]])

    def rows_of(sql: str, cols: list[str]) -> list[dict]:
        return [dict(zip(cols, row, strict=True)) for row in con.execute(sql).fetchall()]

    pairs = con.execute("SELECT count(*), count(DISTINCT numero_registro) FROM bridge").fetchone()
    by_tribunal = rows_of(
        """SELECT tribunal, coalesce(datajud_alias, '(sem alias)') AS datajud_alias, count(*) AS n
           FROM bridge GROUP BY 1, 2 HAVING count(*) >= 5 ORDER BY n DESC LIMIT 25""",
        ["tribunal", "datajud_alias", "n"],
    )
    invalid = con.execute("SELECT count(*) FROM bridge WHERE NOT cnj_valid").fetchone()[0]
    # coverage: share of documents / candidates whose numeroRegistro is resolvable today
    cov = rows_of(
        f"""WITH b AS (SELECT DISTINCT numero_registro FROM bridge)
            SELECT substr(m.key, 1, 4) AS year, count(*) AS documents,
                   count(b.numero_registro) AS bridged,
                   round(100.0 * count(b.numero_registro) / count(*), 1) AS pct
            FROM read_parquet('{META}') m LEFT JOIN b ON b.numero_registro = m.numero_registro
            GROUP BY 1 ORDER BY 1""",
        ["year", "documents", "bridged", "pct"],
    )
    cand_cov = None
    if list((ROOT / "data" / "interim" / "candidates" / "docs").glob("*.parquet")):
        cand_cov = rows_of(
            f"""WITH b AS (SELECT DISTINCT numero_registro FROM bridge),
                     c AS (SELECT DISTINCT key, seq_documento FROM read_parquet('{CAND}') WHERE is_candidate)
                SELECT substr(m.key, 1, 4) AS year, count(*) AS candidates,
                       count(b.numero_registro) AS bridged,
                       round(100.0 * count(b.numero_registro) / count(*), 1) AS pct
                FROM c JOIN read_parquet('{META}') m USING (key, seq_documento)
                LEFT JOIN b ON b.numero_registro = m.numero_registro
                GROUP BY 1 ORDER BY 1""",
            ["year", "candidates", "bridged", "pct"],
        )
    con.close()

    out = {
        "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "files": per_file,
        "bridge_rows": pairs[0],
        "distinct_numero_registro": pairs[1],
        "cnj_check_digit_invalid": invalid,
        "by_tribunal_top25_k_ge_5": by_tribunal,
        "document_coverage_by_year": cov,
        "candidate_coverage_by_year": cand_cov,
        "atas_ingested": sum(1 for r in per_file if r["source"] == "ata"),
        "note": ("acervo is a snapshot of pending cases: low coverage for older years is expected and is why the "
                 "atas de distribuição (2023-06-30 onwards) are needed for the historical bridge"),
        "views_created": is_file,
        "minutes": round((time.time() - t_all) / 60, 1),
    }
    json.dump(out, open(LOG / "12_ingest_stj_bridge.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "by_tribunal_top25_k_ge_5"}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
