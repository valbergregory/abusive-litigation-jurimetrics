"""Phase 1, step 10 — ingest the full STJ *íntegras* corpus (metadata + texts) into Parquet + DuckDB.

Reads the daily/monthly files from a local mirror (default: the sibling repository
`STJ-Moral-Damages-Jurimetrics/data/raw/stj_integras/{metadata,texts}`, downloaded on 2026-09-07/08 with SHA-256
checksums; override with `--source DIR` or env `ALJ_STJ_MIRROR`). Nothing is downloaded here: if a key is missing
from the mirror it is reported in the log, and `scripts/06`-style download stays a separate, explicitly authorised step.

Writes (all git-ignored, counts-only log committed):
  data/interim/stj_integras/meta/<key>.parquet   normalised metadata (rapporteur salted-hashed; no party names)
  data/interim/stj_integras/text/<key>.parquet   texts (seq_documento, member, nchar, text_sha256, text)
  data/alj.duckdb                                views `documents`, `document_text` + table `ingest_log`
  logs/raw_hashes.tsv                            one SHA-256 line per source file used (appended, de-duplicated)
  logs/10_ingest_stj_integras.json               per-key and per-year counts (metadata rows, text rows, coverage)

Usage:  uv run python scripts/10_ingest_stj_integras.py [--source DIR] [--keys 20210104 20211231] [--limit N] [--force]
Idempotent: keys whose two Parquet files exist are skipped unless --force. ~3.5 M documents / 11.4 GB of ZIPs:
about 30–60 min on the reference machine; run in the background.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alj.stj_integras import file_sha256, key_of, read_metadata, read_texts  # noqa: E402

DEFAULT_MIRROR = ROOT.parent / "STJ-Moral-Damages-Jurimetrics" / "data" / "raw" / "stj_integras"
INTERIM = ROOT / "data" / "interim" / "stj_integras"
DB = ROOT / "data" / "alj.duckdb"
LOG = ROOT / "logs"
HASHES = LOG / "raw_hashes.tsv"
SALT_FILE = ROOT / ".secrets" / "salt"


def load_salt() -> bytes:
    SALT_FILE.parent.mkdir(exist_ok=True)
    if not SALT_FILE.exists():
        SALT_FILE.write_bytes(os.urandom(32))
    return SALT_FILE.read_bytes()


def record_hash(path: Path, url_hint: str, seen: set[str]) -> None:
    """Append `sha256<TAB>size<TAB>date<TAB>licence<TAB>source<TAB>file` to logs/raw_hashes.tsv (once per file)."""
    name = path.name
    if name in seen:
        return
    line = "\t".join(
        [file_sha256(path), str(path.stat().st_size), dt.date.today().isoformat(), "CC-BY (STJ open data)", url_hint, name]
    )
    with open(HASHES, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    seen.add(name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=os.environ.get("ALJ_STJ_MIRROR", str(DEFAULT_MIRROR)))
    ap.add_argument("--keys", nargs=2, metavar=("FROM", "TO"), help="inclusive key range, e.g. 20210104 20211231")
    ap.add_argument("--limit", type=int, default=None, help="process at most N keys (smoke test)")
    ap.add_argument("--force", action="store_true", help="re-parse keys that already have Parquet files")
    a = ap.parse_args()

    src = Path(a.source)
    meta_dir, text_dir = src / "metadata", src / "texts"
    if not meta_dir.is_dir() or not text_dir.is_dir():
        print(f"mirror not found: {src} (expected metadata/ and texts/). Nothing downloaded; stop.", file=sys.stderr)
        return 2
    (INTERIM / "meta").mkdir(parents=True, exist_ok=True)
    (INTERIM / "text").mkdir(parents=True, exist_ok=True)
    LOG.mkdir(exist_ok=True)
    salt = load_salt()

    metas = {key_of(p.name): p for p in meta_dir.glob("metadados*.json")}
    zips = {key_of(p.name): p for p in text_dir.glob("textos*.zip")}
    keys = sorted(set(metas) | set(zips))
    if a.keys:
        keys = [k for k in keys if a.keys[0] <= k <= a.keys[1]]
    todo = [k for k in keys if a.force or not ((INTERIM / "meta" / f"{k}.parquet").exists() and (INTERIM / "text" / f"{k}.parquet").exists())]
    if a.limit:
        todo = todo[: a.limit]
    print(f"keys in mirror: {len(keys)} | to process: {len(todo)} | source: {src}")

    seen = set()
    if HASHES.exists():
        seen = {ln.rstrip("\n").split("\t")[-1] for ln in open(HASHES, encoding="utf-8") if ln.strip()}
    per_key: list[dict] = []
    t_all = time.time()
    for i, k in enumerate(todo, 1):
        t0 = time.time()
        rec = {"key": k, "meta_file": metas.get(k) is not None, "zip_file": zips.get(k) is not None, "meta_rows": 0, "text_rows": 0, "text_in_meta": 0}
        meta = read_metadata(metas[k], salt) if k in metas else None
        text = read_texts(zips[k]) if k in zips else None
        if meta is not None:
            meta.write_parquet(INTERIM / "meta" / f"{k}.parquet", compression="zstd")
            record_hash(metas[k], "dadosabertos.web.stj.jus.br / integras-de-decisoes-terminativas-e-acordaos-do-diario-da-justica", seen)
            rec["meta_rows"] = meta.height
        if text is not None:
            text.write_parquet(INTERIM / "text" / f"{k}.parquet", compression="zstd")
            record_hash(zips[k], "dadosabertos.web.stj.jus.br / integras-de-decisoes-terminativas-e-acordaos-do-diario-da-justica", seen)
            rec["text_rows"] = text.height
        if meta is not None and text is not None:
            rec["text_in_meta"] = text.join(meta.select("seq_documento"), on="seq_documento", how="semi").height
        rec["seconds"] = round(time.time() - t0, 2)
        per_key.append(rec)
        if i % 50 == 0 or i == len(todo):
            print(f"[{i}/{len(todo)}] {k}: meta={rec['meta_rows']} text={rec['text_rows']} | {(time.time() - t_all) / 60:.1f} min", flush=True)

    # DuckDB layer: views over the Parquet folders (no copy) + ingest log table
    con = duckdb.connect(str(DB))
    mp, tp = str(INTERIM / "meta" / "*.parquet").replace("\\", "/"), str(INTERIM / "text" / "*.parquet").replace("\\", "/")
    con.execute(f"CREATE OR REPLACE VIEW documents AS SELECT * FROM read_parquet('{mp}')")
    con.execute(f"CREATE OR REPLACE VIEW document_text AS SELECT seq_documento, key, member, nchar, text_sha256, text FROM read_parquet('{tp}')")
    con.execute("CREATE TABLE IF NOT EXISTS ingest_log (key VARCHAR PRIMARY KEY, meta_file BOOLEAN, zip_file BOOLEAN, meta_rows INTEGER, text_rows INTEGER, text_in_meta INTEGER, seconds DOUBLE, ingested_at TIMESTAMP)")
    for r in per_key:
        con.execute("DELETE FROM ingest_log WHERE key = ?", [r["key"]])
        con.execute("INSERT INTO ingest_log VALUES (?, ?, ?, ?, ?, ?, ?, now())", [r["key"], r["meta_file"], r["zip_file"], r["meta_rows"], r["text_rows"], r["text_in_meta"], r["seconds"]])
    # coverage is measured on the Parquet files themselves (not on ingest_log), so it survives interrupted runs
    con.execute("""CREATE OR REPLACE TABLE key_coverage AS
        SELECT m.key, count(*) AS meta_rows, count(t.seq_documento) AS text_in_meta
        FROM documents m LEFT JOIN (SELECT DISTINCT seq_documento FROM document_text) t USING (seq_documento) GROUP BY 1""")
    summary = con.execute(
        """SELECT substr(key, 1, 4) AS year, count(*) AS keys, sum(meta_rows) AS meta_rows, sum(text_in_meta) AS text_in_meta,
                  round(100.0 * sum(text_in_meta) / nullif(sum(meta_rows), 0), 1) AS coverage_pct
           FROM key_coverage GROUP BY 1 ORDER BY 1"""
    ).fetchall()
    n_docs = con.execute("SELECT count(*) FROM documents").fetchone()[0]
    n_txt = con.execute("SELECT count(*) FROM document_text").fetchone()[0]
    tipo = dict(con.execute("SELECT tipo_documento, count(*) FROM documents GROUP BY 1").fetchall())
    low = con.execute("SELECT key, meta_rows, text_in_meta FROM key_coverage WHERE meta_rows > 0 AND text_in_meta < 0.5 * meta_rows ORDER BY key").fetchall()
    con.close()

    out = {
        "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": str(src),
        "keys_in_mirror": len(keys),
        "keys_processed_this_run": len(todo),
        "documents": n_docs,
        "texts": n_txt,
        "by_tipo_documento": tipo,
        "by_year": [dict(zip(["year", "keys", "meta_rows", "text_in_meta", "coverage_pct"], r, strict=True)) for r in summary],
        "low_coverage_keys": [dict(zip(["key", "meta_rows", "text_in_meta"], r, strict=True)) for r in low],
        "zip_present_but_empty_or_unreadable": [r["key"] for r in per_key if r["zip_file"] and r["text_rows"] == 0],
        "missing_meta": [k for k in keys if k not in metas],
        "missing_zip": [k for k in keys if k not in zips],
        "minutes": round((time.time() - t_all) / 60, 1),
        "per_key_this_run": per_key,
    }
    json.dump(out, open(LOG / "10_ingest_stj_integras.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k not in ("per_key_this_run",)}, ensure_ascii=False, indent=1))
    print("by_year:", collections.OrderedDict((r[0], r[5]) for r in summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
