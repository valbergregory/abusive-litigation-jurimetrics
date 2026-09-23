"""Phase 1, step 20 — apply the versioned lexicon to the whole íntegras corpus and build the candidate set.

Two stages, because the corpus is ~3.0 M texts / 6 GB:
  A) DuckDB/RE2 pre-filter — ONE combined regex (named group per candidate-tier pattern, bounded repeats
     relaxed to a superset, see `alj.lexicon.relax_bounded_repeats`) pushed into `regexp_matches(text, …, 'i')`
     over the Parquet of step 10: 0.8 s per publication day instead of 25 s;
  B) Python `re` on the survivors only — per-hit context windows, exclusions (false friends measured in
     phase 0 §3) and negation markers. `tests/test_lexicon.py` proves stage A never drops a stage-B hit.

A hit is NOT a label (CLAUDE.md §2). This script produces reading candidates; the labels come from the
researcher's manual review (docs/annotation_protocol.md) and are stored under data/annotations/.

Writes (git-ignored, counts-only log committed):
  data/interim/candidates/docs/<key>.parquet        one row per candidate document (alj.lexicon.CANDIDATE_SCHEMA)
  data/interim/candidates/near_miss/<key>.parquet   pre-filtered documents whose every hit was excluded
  data/interim/candidates/hits/<key>.parquet   one row per hit, with its context window (HIT_SCHEMA)
  data/alj.duckdb                              views `candidates`, `candidate_hits` + table `lexicon_run_log`
  logs/20_lexicon_candidates.json              counts by year, tier, pattern and exclusion

Usage:  uv run python scripts/20_lexicon_candidates.py [--keys 20210104 20251231] [--limit N] [--force]
        uv run python scripts/20_lexicon_candidates.py --sample 2000     # smoke run, N texts per key
Idempotent: a key already logged for the same lexicon version is skipped unless --force.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import sys
import time
from pathlib import Path

import duckdb

if hasattr(sys.stdout, "reconfigure"):  # the Windows console is cp1252; logs are always UTF-8
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alj.lexicon import (  # noqa: E402
    candidates_frame,
    combined_source,
    document_summary,
    hit_rows,
    hits_frame,
    load_lexicon,
    prefilter_regex,
    scan_text,
)

TEXT_DIR = ROOT / "data" / "interim" / "stj_integras" / "text"
OUT = ROOT / "data" / "interim" / "candidates"
DB = ROOT / "data" / "alj.duckdb"
LOG = ROOT / "logs"
DEFAULT_LEXICON = ROOT / "config" / "lexicon_v2.yaml"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lexicon", default=str(DEFAULT_LEXICON))
    ap.add_argument("--keys", nargs=2, metavar=("FROM", "TO"), help="inclusive key range, e.g. 20210104 20251231")
    ap.add_argument("--limit", type=int, help="process at most N keys (after --keys)")
    ap.add_argument("--sample", type=int, help="scan at most N texts per key (smoke run; not logged as done)")
    ap.add_argument("--force", action="store_true", help="re-scan keys already logged for this lexicon version")
    ap.add_argument("--threads", type=int, default=0, help="DuckDB threads (0 = default)")
    return ap.parse_args(argv)


def select_keys(args: argparse.Namespace) -> list[str]:
    keys = sorted(p.stem for p in TEXT_DIR.glob("*.parquet"))
    if args.keys:
        lo, hi = args.keys
        keys = [k for k in keys if lo <= k <= hi]
    return keys[: args.limit] if args.limit else keys


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not TEXT_DIR.exists():
        print(f"no text Parquet in {TEXT_DIR} — run scripts/10_ingest_stj_integras.py first", file=sys.stderr)
        return 2
    lex = load_lexicon(args.lexicon)
    rx = prefilter_regex(lex)  # compiled here only to fail fast on a malformed pattern
    assert rx.groups
    combined = combined_source(lex, relaxed=True)  # superset + ~30x faster in RE2 (see relax_bounded_repeats)
    # a smoke run must never pollute the real candidate set (its Parquet would hold a sample of each day)
    docs_dir = OUT / ("sample_docs" if args.sample else "docs")
    hits_dir = OUT / ("sample_hits" if args.sample else "hits")
    # near misses: documents the pre-filter selected but where every hit was dropped by an exclusion. They are
    # the `control_flagged` stratum of step 21 (what the false-friend rules cost), so they are kept apart from
    # the candidates instead of being discarded.
    near_dir = OUT / ("sample_near_miss" if args.sample else "near_miss")
    for d in (docs_dir, hits_dir, near_dir):
        d.mkdir(parents=True, exist_ok=True)
    LOG.mkdir(exist_ok=True)

    con = duckdb.connect(str(DB))
    if args.threads:
        con.execute(f"SET threads = {args.threads}")
    con.execute(
        """CREATE TABLE IF NOT EXISTS lexicon_run_log (
               key VARCHAR, lexicon_version VARCHAR, docs_scanned INTEGER, prefiltered INTEGER,
               candidates INTEGER, hits INTEGER, seconds DOUBLE, run_at TIMESTAMP,
               PRIMARY KEY (key, lexicon_version))"""
    )
    done = {r[0] for r in con.execute("SELECT key FROM lexicon_run_log WHERE lexicon_version = ?", [lex.version]).fetchall()}

    keys = select_keys(args)
    todo = [k for k in keys if args.force or args.sample or k not in done]
    print(f"lexicon v{lex.version}: {len(lex.of_tier(*lex.candidate_tiers))} candidate-tier patterns; "
          f"{len(keys)} keys, {len(todo)} to scan", flush=True)

    t_all = time.time()
    per_key: list[dict] = []
    totals = collections.Counter()
    for n, key in enumerate(todo, 1):
        t0 = time.time()
        pq = (TEXT_DIR / f"{key}.parquet").as_posix()
        sample = f"USING SAMPLE {args.sample} ROWS" if args.sample else ""
        n_docs = con.execute(f"SELECT count(*) FROM read_parquet('{pq}') WHERE text IS NOT NULL").fetchone()[0]
        rows = con.execute(
            f"""SELECT seq_documento, key, text FROM (
                    SELECT seq_documento, key, text FROM read_parquet('{pq}')
                    WHERE text IS NOT NULL AND length(text) > 0 {sample}
                ) WHERE regexp_matches(text, ?, 'i')""",
            [combined],
        ).fetchall()

        doc_rows: list[dict] = []
        hit_records: list[dict] = []
        near_rows: list[dict] = []
        for seq, k, text in rows:
            hits = scan_text(text, lex)
            summary = document_summary(seq, k, hits, lex)
            if not summary["is_candidate"]:
                near_rows.append(summary)  # stage A matched but every hit was dropped by an exclusion
                continue
            doc_rows.append(summary)
            hit_records.extend(hit_rows(seq, k, hits))
            totals["excluded_hits"] += summary["n_excluded"]
            totals["negated_all_docs"] += int(summary["negated_all"])
        totals["near_miss"] += len(near_rows)
        if doc_rows:
            candidates_frame(doc_rows).write_parquet(docs_dir / f"{key}.parquet")
            hits_frame(hit_records).write_parquet(hits_dir / f"{key}.parquet")
        if near_rows:
            candidates_frame(near_rows).write_parquet(near_dir / f"{key}.parquet")

        secs = round(time.time() - t0, 2)
        rec = {
            "key": key,
            "docs_scanned": n_docs if not args.sample else min(n_docs, args.sample),
            "prefiltered": len(rows),
            "candidates": len(doc_rows),
            "hits": len(hit_records),
            "seconds": secs,
        }
        per_key.append(rec)
        totals["docs_scanned"] += rec["docs_scanned"]
        totals["prefiltered"] += rec["prefiltered"]
        totals["candidates"] += rec["candidates"]
        totals["hits"] += rec["hits"]
        if not args.sample:
            con.execute("DELETE FROM lexicon_run_log WHERE key = ? AND lexicon_version = ?", [key, lex.version])
            con.execute("INSERT INTO lexicon_run_log VALUES (?, ?, ?, ?, ?, ?, ?, now())",
                        [key, lex.version, rec["docs_scanned"], rec["prefiltered"], rec["candidates"], rec["hits"], secs])
        if n % 50 == 0 or n == len(todo):
            print(f"  [{n}/{len(todo)}] {key}: {rec['prefiltered']} pre-filtered, {rec['candidates']} candidates "
                  f"({secs}s) — running totals {dict(totals)}", flush=True)

    # views over everything written so far (not only this run)
    docs_glob = (docs_dir / "*.parquet").as_posix()
    hits_glob = (hits_dir / "*.parquet").as_posix()
    has_docs = any(docs_dir.glob("*.parquet"))
    if has_docs and not args.sample:
        con.execute(f"CREATE OR REPLACE VIEW candidates AS SELECT * FROM read_parquet('{docs_glob}')")
        con.execute(f"CREATE OR REPLACE VIEW candidate_hits AS SELECT * FROM read_parquet('{hits_glob}')")

    def rows_of(sql: str, cols: list[str]) -> list[dict]:
        return [dict(zip(cols, r, strict=True)) for r in con.execute(sql).fetchall()]

    stats: dict = {}
    if has_docs and not args.sample:
        stats["by_year"] = rows_of(
            """SELECT substr(key, 1, 4) AS year, count(*) AS candidates,
                      sum(CASE WHEN strict_hit THEN 1 ELSE 0 END) AS strict,
                      sum(CASE WHEN conduct_hit THEN 1 ELSE 0 END) AS conduct,
                      sum(CASE WHEN sanction_hit THEN 1 ELSE 0 END) AS sanction,
                      sum(CASE WHEN negated_all THEN 1 ELSE 0 END) AS negated_all
               FROM candidates GROUP BY 1 ORDER BY 1""",
            ["year", "candidates", "strict", "conduct", "sanction", "negated_all"],
        )
        stats["by_pattern"] = rows_of(
            """SELECT pattern_id, tier, count(*) AS hits, count(DISTINCT seq_documento) AS documents,
                      sum(CASE WHEN negated_hint THEN 1 ELSE 0 END) AS negated
               FROM candidate_hits WHERE excluded_by IS NULL GROUP BY 1, 2 ORDER BY documents DESC""",
            ["pattern_id", "tier", "hits", "documents", "negated"],
        )
        stats["dropped_by_exclusion"] = rows_of(
            "SELECT excluded_by, count(*) AS hits FROM candidate_hits WHERE excluded_by IS NOT NULL GROUP BY 1 ORDER BY 2 DESC",
            ["exclusion_id", "hits"],
        )
        stats["strict_only_docs"] = con.execute(
            "SELECT count(*) FROM candidates WHERE strict_hit AND NOT conduct_hit AND NOT sanction_hit"
        ).fetchone()[0]
        stats["docs_with_strict_and_conduct"] = con.execute(
            "SELECT count(*) FROM candidates WHERE strict_hit AND conduct_hit"
        ).fetchone()[0]
    con.close()

    out = {
        "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "lexicon": {"path": str(Path(args.lexicon).relative_to(ROOT)), "version": lex.version,
                    "patterns": len(lex.patterns), "candidate_tiers": list(lex.candidate_tiers)},
        "sample_mode": bool(args.sample),
        "keys_available": len(keys),
        "keys_scanned_this_run": len(todo),
        "totals": dict(totals),
        "prefilter_rate_pct": round(100.0 * totals["prefiltered"] / max(totals["docs_scanned"], 1), 2),
        "candidate_rate_pct": round(100.0 * totals["candidates"] / max(totals["docs_scanned"], 1), 3),
        "stage_b_precision_of_prefilter_pct": round(100.0 * totals["candidates"] / max(totals["prefiltered"], 1), 1),
        "minutes": round((time.time() - t_all) / 60, 1),
        **stats,
        "per_key_this_run": per_key,
    }
    name = "20_lexicon_candidates" + ("_sample" if args.sample else "")
    json.dump(out, open(LOG / f"{name}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k not in ("per_key_this_run", "by_pattern")},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
