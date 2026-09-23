"""Phase 1, step 21 — draw the stratified annotation sample and write the researcher's worksheet.

Reads the Parquet of steps 10 and 20 directly (no lock on data/alj.duckdb, so it can run while step 20 is still
writing), draws one sample per stratum with a fixed seed (``--seed``, default 20260922) and writes:

  data/annotations/gold_v1_sample.csv          the worksheet to fill (UTF-8 BOM, opens straight in Excel)
  data/annotations/gold_v1_reannotation.csv    10% of the same rows, shuffled, hints stripped (κ check)
  data/annotations/README_annotation.md        what to fill, what never leaves the machine
  logs/21_export_annotation_sample.json        stratum sizes, seed, counts (no snippets)

Everything under data/annotations/ is git-ignored: the rows carry decision snippets, and the repository is public.

Usage:  uv run python scripts/21_export_annotation_sample.py [--seed N] [--max-year 2025]
        uv run python scripts/21_export_annotation_sample.py --size strict=800 --size conduct_multi=200
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import duckdb

if hasattr(sys.stdout, "reconfigure"):  # the Windows console is cp1252; logs are always UTF-8
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alj.annotation import (  # noqa: E402
    DEFAULT_STRATA,
    HINT_COLUMNS,
    LABEL_COLUMNS,
    REANNOTATION_FRACTION,
    worksheet_columns,
)

META = (ROOT / "data" / "interim" / "stj_integras" / "meta" / "*.parquet").as_posix()
TEXT = (ROOT / "data" / "interim" / "stj_integras" / "text" / "*.parquet").as_posix()
CAND = (ROOT / "data" / "interim" / "candidates" / "docs" / "*.parquet").as_posix()
HITS = (ROOT / "data" / "interim" / "candidates" / "hits" / "*.parquet").as_posix()
NEAR = ROOT / "data" / "interim" / "candidates" / "near_miss"
OUT = ROOT / "data" / "annotations"
LOG = ROOT / "logs"
BOM = b"\xef\xbb\xbf"  # Excel needs it to read UTF-8 accents in a .csv


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=20260922)
    ap.add_argument("--max-year", default="2025", help="drop later years (2026 text coverage is 27.8%%, §10)")
    ap.add_argument("--min-year", default="2021")
    ap.add_argument("--size", action="append", default=[], metavar="NAME=N", help="override one stratum size")
    ap.add_argument("--out", default=str(OUT))
    return ap.parse_args(argv)


def resolve_sizes(args: argparse.Namespace) -> dict[str, int]:
    sizes = {s.name: s.size for s in DEFAULT_STRATA}
    for item in args.size:
        name, _, value = item.partition("=")
        if name not in sizes:
            raise SystemExit(f"unknown stratum: {name} (known: {', '.join(sizes)})")
        sizes[name] = int(value)
    return sizes


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    sizes = resolve_sizes(args)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    LOG.mkdir(exist_ok=True)
    if not list(Path(CAND).parent.glob("*.parquet")):
        print("no candidates yet — run scripts/20_lexicon_candidates.py first", file=sys.stderr)
        return 2

    con = duckdb.connect()  # in-memory: reads the Parquet, never locks data/alj.duckdb
    # the published metadata files repeat some documents verbatim (15,650 rows, 0.45%: e.g. seq 190666544 of
    # 20230525 appears 17 times), so the metadata view is deduplicated before any join, or the sample would
    # carry the same decision several times
    con.execute(f"CREATE VIEW meta AS SELECT DISTINCT * FROM read_parquet('{META}')")
    con.execute(f"CREATE VIEW txt AS SELECT seq_documento, key, nchar FROM read_parquet('{TEXT}')")
    con.execute(f"CREATE VIEW cand AS SELECT * FROM read_parquet('{CAND}')")
    con.execute(f"CREATE VIEW hits AS SELECT * FROM read_parquet('{HITS}')")
    near_glob = (NEAR / "*.parquet").as_posix()
    if list(NEAR.glob("*.parquet")):
        con.execute(f"CREATE VIEW near AS SELECT * FROM read_parquet('{near_glob}')")
    else:  # step 20 ran before the near_miss output existed
        con.execute("CREATE VIEW near AS SELECT * FROM cand WHERE FALSE")
    year_filter = f"substr(m.key, 1, 4) BETWEEN '{args.min_year}' AND '{args.max_year}'"

    # one row per candidate document, with the three most informative context windows (strict first, then
    # conduct, then sanction; a rejected window last) and the count of distinct Annex A conducts
    con.execute(
        f"""CREATE TABLE base AS
        WITH kept AS (
            SELECT h.*, CASE h.tier WHEN 'strict' THEN 0 WHEN 'conduct' THEN 1 WHEN 'sanction' THEN 2 ELSE 3 END AS tier_rank
            FROM hits h WHERE h.excluded_by IS NULL
        ), ranked AS (
            SELECT *, row_number() OVER (PARTITION BY key, seq_documento
                                         ORDER BY negated_hint, tier_rank, start) AS rn
            FROM kept
        ), ctx AS (
            SELECT key, seq_documento,
                   max(CASE WHEN rn = 1 THEN context END) AS context_1,
                   max(CASE WHEN rn = 2 THEN context END) AS context_2,
                   max(CASE WHEN rn = 3 THEN context END) AS context_3,
                   count(DISTINCT CASE WHEN tier = 'conduct' THEN pattern_id END) AS n_conduct_patterns,
                   count(DISTINCT CASE WHEN tier = 'sanction' THEN pattern_id END) AS n_sanction_patterns
            FROM ranked GROUP BY 1, 2
        )
        SELECT c.key, c.seq_documento, m.data_publicacao, m.tipo_documento, m.classe, m.processo,
               m.numero_registro, m.assuntos_leaf, t.nchar,
               c.patterns, c.annex_a_items, c.tiers, c.n_hits, c.negated_all,
               c.strict_hit, c.conduct_hit, c.sanction_hit,
               x.n_conduct_patterns, x.n_sanction_patterns, x.context_1, x.context_2, x.context_3
        FROM cand c
        JOIN meta m USING (key, seq_documento)
        LEFT JOIN txt t USING (key, seq_documento)
        LEFT JOIN ctx x ON x.key = c.key AND x.seq_documento = c.seq_documento
        WHERE {year_filter}"""
    )

    strata_sql = {
        "strict": "SELECT * FROM base WHERE strict_hit AND NOT negated_all",
        "strict_negated": "SELECT * FROM base WHERE strict_hit AND negated_all",
        "conduct_multi": "SELECT * FROM base WHERE NOT strict_hit AND n_conduct_patterns >= 2",
        "conduct_sanction": (
            "SELECT * FROM base WHERE NOT strict_hit AND n_conduct_patterns >= 1 AND n_sanction_patterns >= 1 "
            "AND n_conduct_patterns < 2"
        ),
        # controls come from the corpus, not from the candidate set
        # near misses come from the near_miss Parquet of step 20 (a run older than 2026-09-22 has none, and the
        # stratum is then reported as available 0 — it fills on the next full run of step 20)
        "control_flagged": (
            f"""SELECT n.key, n.seq_documento, m.data_publicacao, m.tipo_documento, m.classe, m.processo,
                       m.numero_registro, m.assuntos_leaf, t.nchar,
                       n.patterns, n.annex_a_items, n.tiers, n.n_hits, n.negated_all,
                       n.strict_hit, n.conduct_hit, n.sanction_hit,
                       0 AS n_conduct_patterns, 0 AS n_sanction_patterns,
                       NULL AS context_1, NULL AS context_2, NULL AS context_3
                FROM near n JOIN meta m USING (key, seq_documento) LEFT JOIN txt t USING (key, seq_documento)
                WHERE {year_filter}"""
        ),
        "control_unflagged": (
            f"""SELECT m.key, m.seq_documento, m.data_publicacao, m.tipo_documento, m.classe, m.processo,
                       m.numero_registro, m.assuntos_leaf, t.nchar,
                       '' AS patterns, '' AS annex_a_items, '' AS tiers, 0 AS n_hits, FALSE AS negated_all,
                       FALSE AS strict_hit, FALSE AS conduct_hit, FALSE AS sanction_hit,
                       0 AS n_conduct_patterns, 0 AS n_sanction_patterns,
                       NULL AS context_1, NULL AS context_2, NULL AS context_3
                FROM meta m JOIN txt t USING (key, seq_documento)
                WHERE {year_filter} AND t.nchar > 500
                  AND NOT EXISTS (SELECT 1 FROM cand c WHERE c.key = m.key AND c.seq_documento = m.seq_documento)"""
        ),
    }

    frames = []
    strata_log = []
    for name, sql in strata_sql.items():
        available = con.execute(f"SELECT count(*) FROM ({sql})").fetchone()[0]
        n = min(sizes[name], available)
        con.execute(f"SELECT setseed({(args.seed % 10_000) / 10_000:.4f})")
        rows = con.execute(
            f"CREATE OR REPLACE TABLE s_{name} AS SELECT '{name}' AS stratum, * FROM ({sql}) "
            f"ORDER BY hash(key || '-' || seq_documento || '-{args.seed}') LIMIT {n}"
        )
        assert rows is not None
        frames.append(f"SELECT * FROM s_{name}")
        strata_log.append({"stratum": name, "available": available, "sampled": n, "requested": sizes[name]})
        print(f"  {name:<18} available {available:>8}  sampled {n:>5}")

    cols = worksheet_columns()
    label_sql = ", ".join(f"'' AS {c}" for c in LABEL_COLUMNS)
    con.execute(
        f"""CREATE TABLE sample AS
        SELECT key || '-' || seq_documento AS doc_id, key, seq_documento, data_publicacao, tipo_documento,
               classe, processo, numero_registro, assuntos_leaf, nchar,
               stratum, patterns, annex_a_items, tiers, n_hits, negated_all,
               context_1, context_2, context_3, {label_sql}
        FROM ({" UNION ALL ".join(frames)})"""
    )
    total = con.execute("SELECT count(*) FROM sample").fetchone()[0]
    dupes = con.execute("SELECT count(*) - count(DISTINCT doc_id) FROM sample").fetchone()[0]
    if dupes:
        con.execute("CREATE OR REPLACE TABLE sample AS SELECT * FROM sample QUALIFY row_number() OVER (PARTITION BY doc_id) = 1")
        total = con.execute("SELECT count(*) FROM sample").fetchone()[0]

    worksheet = out_dir / "gold_v1_sample.csv"
    reann = out_dir / "gold_v1_reannotation.csv"
    select_cols = ", ".join(cols)
    con.execute(f"COPY (SELECT {select_cols} FROM sample ORDER BY stratum, data_publicacao, doc_id) "
                f"TO '{worksheet.as_posix()}' (HEADER, DELIMITER ',')")
    n_re = max(1, round(total * REANNOTATION_FRACTION))
    blind_cols = [c for c in cols if c not in set(HINT_COLUMNS) - {"context_1", "context_2", "context_3"}]
    con.execute(
        f"COPY (SELECT {', '.join(blind_cols)} FROM sample "
        f"ORDER BY hash(doc_id || '-blind-{args.seed}') LIMIT {n_re}) "
        f"TO '{reann.as_posix()}' (HEADER, DELIMITER ',')"
    )
    for path in (worksheet, reann):  # DuckDB writes plain UTF-8; the BOM is what makes Excel read the accents
        raw = path.read_bytes()
        if not raw.startswith(BOM):
            path.write_bytes(BOM + raw)
    by_year = con.execute(
        "SELECT substr(key, 1, 4) AS year, stratum, count(*) FROM sample GROUP BY 1, 2 ORDER BY 1, 2"
    ).fetchall()
    con.close()

    readme = out_dir / "README_annotation.md"
    readme.write_text(
        f"""# Annotation worksheet — gold set v1

Generated by `scripts/21_export_annotation_sample.py` on {dt.date.today().isoformat()} with seed {args.seed},
lexicon v2 (`config/lexicon_v2.yaml`), years {args.min_year}–{args.max_year}.

**This folder is git-ignored. The rows contain excerpts of decisions; the repository is public.**

## What to fill (one row per document) — the codes are yours, from docs/annotation_protocol.md

| column | protocol | values |
|---|---|---|
| `label1_status` | §2 | `S3` recognised and grounded a measure · `S2` upheld a lower-court finding · `S1` allegation/rejected/cited only · `S0` false positive of the lexicon · `NA` text missing |
| `label2_grounds` | §3 | Annex A items as `A1`…`A20`, plus `T1198` and `MAFE`; `;`-separated, multi-label |
| `label3_measure` | §4 | `M0` none · `M1` amend/complete documents · `M2` extinction without merits · `M3` fine/costs · `M4` notice to OAB/MP · `M5` other |
| `label4_domain` | §5 | `D1` consumer/banking · `D2` civil other · `D3` criminal · `D4` public law/tax · `D5` labour/other |
| `justification` | §6.2 | one sentence quoting the decisive passage by paragraph, never by party name |
| `minutes_spent`, `annotator`, `annotation_date`, `protocol_version` | §6 | bookkeeping |

Read the full document, not the snippet (§6.1). Leave `label1_status` blank if you could not decide; blank rows
are counted as "not annotated", never guessed. `patterns`, `annex_a_items`, `tiers` and the `context_*` columns
are the machine's hints — they are **not** labels and may be wrong (measuring that is the point).

## Order of work

1. `strict` stratum first (the phenomenon is named) — it calibrates the ladder.
2. `strict_negated` next: allegations the court **rejected**; these should end up `S1`/`S0`.
3. `conduct_multi` and `conduct_sanction`: the phenomenon described without the term.
4. Controls (`control_flagged`, `control_unflagged`): mostly `S0`; they give the recall denominator.
5. When done, save as `gold_v1.csv` in this folder and run `scripts/22_validate_lexicon.py`
   (it reports the positive class with and without `S2`, as §2 requires).
6. `gold_v1_reannotation.csv` is {n_re} of the same documents without the hint columns: annotate it blind after
   two weeks (§6.3), save as `gold_v1_reannotation_done.csv`, and step 22 reports Cohen's κ (go/no-go: κ ≥ 0.75).
""",
        encoding="utf-8",
    )

    out = {
        "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "seed": args.seed,
        "years": [args.min_year, args.max_year],
        "strata": strata_log,
        "sample_rows": total,
        "duplicates_removed": dupes,
        "reannotation_rows": n_re,
        "by_year_stratum": [dict(zip(["year", "stratum", "n"], r, strict=True)) for r in by_year],
        "files": {"worksheet": str(worksheet.relative_to(ROOT)), "reannotation": str(reann.relative_to(ROOT)),
                  "readme": str(readme.relative_to(ROOT))},
    }
    json.dump(out, open(LOG / "21_export_annotation_sample.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "by_year_stratum"}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
