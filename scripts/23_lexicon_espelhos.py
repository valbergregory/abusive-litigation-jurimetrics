"""Phase 1, step 23 — apply the same lexicon to the *espelhos de acórdãos* (collegiate decisions).

The íntegras (step 20) and the espelhos are two independent windows on the same phenomenon: the íntegras hold the
full text of monocratic decisions and acórdãos, the espelhos hold the ementa, the decision text, the cited case
law and the legislative references of the collegiate judgments. Running the *same instrument* on both is what
allows the article to say whether the signalling vocabulary behaves alike in the two corpora (phase 0 §3 measured
0.34 % of espelhos with a strict term in one month of the Terceira Turma).

Scanned text = ``ementa`` + ``decisao`` + ``notas`` + ``informacoes_complementares`` (the fields where the court
states the grounds), never the party fields (there are none in this dataset).

Writes:
  data/interim/candidates_espelhos/{docs,hits}/<file>.parquet
  data/alj.duckdb                    views `espelho_candidates`, `espelho_candidate_hits` (when not locked)
  logs/23_lexicon_espelhos.json      counts by year, body, tier and pattern

Usage:  uv run python scripts/23_lexicon_espelhos.py [--orgaos terceira-turma …] [--force]
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alj.db import connect_or_memory  # noqa: E402
from alj.lexicon import (  # noqa: E402
    candidates_frame,
    combined_source,
    document_summary,
    hit_rows,
    hits_frame,
    load_lexicon,
    scan_text,
)

SRC = ROOT / "data" / "interim" / "espelhos" / "espelhos"
OUT = ROOT / "data" / "interim" / "candidates_espelhos"
DB = ROOT / "data" / "alj.duckdb"
LOG = ROOT / "logs"
TEXT_SQL = ("coalesce(ementa, '') || ' ' || coalesce(decisao, '') || ' ' || coalesce(notas, '') || ' ' || "
            "coalesce(informacoes_complementares, '')")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lexicon", default=str(ROOT / "config" / "lexicon_v2.yaml"))
    ap.add_argument("--orgaos", nargs="*", help="only these body slugs (default: all Parquet in the folder)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    files = sorted(SRC.glob("*.parquet"))
    if args.orgaos:
        files = [f for f in files if any(f.name.startswith(f"{o}_") for o in args.orgaos)]
    if not files:
        print(f"no espelhos Parquet in {SRC} — run scripts/11_ingest_stj_espelhos.py first", file=sys.stderr)
        return 2

    lex = load_lexicon(args.lexicon)
    combined = combined_source(lex, relaxed=True)
    (OUT / "docs").mkdir(parents=True, exist_ok=True)
    (OUT / "hits").mkdir(parents=True, exist_ok=True)
    LOG.mkdir(exist_ok=True)
    con, is_file = connect_or_memory(DB)

    t_all = time.time()
    totals: collections.Counter[str] = collections.Counter()
    per_file: list[dict] = []
    for n, path in enumerate(files, 1):
        target = OUT / "docs" / path.name
        if target.exists() and not args.force:
            continue
        rows = con.execute(
            f"""SELECT espelho_id, orgao_slug, numero_registro, data_publicacao, {TEXT_SQL} AS text
                FROM read_parquet('{path.as_posix()}')
                WHERE regexp_matches({TEXT_SQL}, ?, 'i')""",
            [combined],
        ).fetchall()
        doc_rows: list[dict] = []
        hit_records: list[dict] = []
        for espelho_id, orgao, _registro, _published, text in rows:
            hits = scan_text(text, lex)
            summary = document_summary(0, path.stem, hits, lex)
            if not summary["is_candidate"]:
                continue
            summary = {**summary, "key": f"{orgao}:{espelho_id}"}
            doc_rows.append(summary)
            hit_records.extend({**h, "key": f"{orgao}:{espelho_id}"} for h in hit_rows(0, path.stem, hits))
        if doc_rows:
            candidates_frame(doc_rows).write_parquet(target)
            hits_frame(hit_records).write_parquet(OUT / "hits" / path.name)
        totals["files"] += 1
        totals["prefiltered"] += len(rows)
        totals["candidates"] += len(doc_rows)
        totals["hits"] += len(hit_records)
        per_file.append({"file": path.name, "prefiltered": len(rows), "candidates": len(doc_rows)})
        if n % 50 == 0 or n == len(files):
            print(f"  [{n}/{len(files)}] {dict(totals)}", flush=True)

    scanned = con.execute(f"SELECT count(*) FROM read_parquet('{(SRC / '*.parquet').as_posix()}')").fetchone()[0]
    stats: dict = {}
    if any((OUT / "docs").glob("*.parquet")):
        con.execute(f"CREATE OR REPLACE VIEW espelho_candidates AS SELECT * FROM read_parquet('{(OUT / 'docs' / '*.parquet').as_posix()}')")
        con.execute(f"CREATE OR REPLACE VIEW espelho_candidate_hits AS SELECT * FROM read_parquet('{(OUT / 'hits' / '*.parquet').as_posix()}')")
        stats["by_pattern"] = [
            dict(zip(["pattern_id", "tier", "documents"], r, strict=True))
            for r in con.execute(
                """SELECT pattern_id, tier, count(DISTINCT key) AS documents FROM espelho_candidate_hits
                   WHERE excluded_by IS NULL GROUP BY 1, 2 HAVING count(DISTINCT key) >= 5 ORDER BY 3 DESC"""
            ).fetchall()
        ]
        stats["strict_documents"] = con.execute(
            "SELECT count(*) FROM espelho_candidates WHERE strict_hit"
        ).fetchone()[0]
    con.close()

    out = {
        "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "lexicon_version": lex.version,
        "espelhos_available": scanned,
        "files_scanned": totals["files"],
        "totals": dict(totals),
        "candidate_rate_pct": round(100.0 * totals["candidates"] / max(scanned, 1), 3),
        "views_created": is_file,
        **stats,
        "minutes": round((time.time() - t_all) / 60, 1),
        "per_file": per_file,
    }
    json.dump(out, open(LOG / "23_lexicon_espelhos.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k not in ("per_file", "by_pattern")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
