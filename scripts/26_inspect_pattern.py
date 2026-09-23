"""Inspection aid — read a random sample of what a lexicon pattern actually matched.

This is how the instrument is judged before any annotation: for each pattern, look at real matches in context
and decide whether they are what the pattern is supposed to capture. A pattern that mostly matches ordinary
procedural language is not wrong — the conduct tier is meant to be broad — but the researcher may want it
narrowed, and this is the evidence for that decision.

Prints, per pattern: how many documents and hits it has, how many of its windows carry a negation marker, and a
random sample (fixed seed) of context windows. Add ``--all`` for a summary table of every pattern at once.

Usage:
    uv run python scripts/26_inspect_pattern.py --all
    uv run python scripts/26_inspect_pattern.py litigancia_predatoria --sample 10
    uv run python scripts/26_inspect_pattern.py autenticidade_postulacao --sample 5 --year 2025
Writes nothing: reading only (the context windows stay on screen; they hold decision excerpts).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alj.lexicon import load_lexicon  # noqa: E402

HITS = (ROOT / "data" / "interim" / "candidates" / "hits" / "*.parquet").as_posix()
DOCS = (ROOT / "data" / "interim" / "candidates" / "docs" / "*.parquet").as_posix()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pattern", nargs="?", help="pattern id (see config/lexicon_v2.yaml)")
    ap.add_argument("--all", action="store_true", help="summary table of every pattern")
    ap.add_argument("--sample", type=int, default=8, help="context windows to print")
    ap.add_argument("--year", help="restrict to a publication year")
    ap.add_argument("--negated", action="store_true", help="only windows that look like a rejection")
    ap.add_argument("--seed", type=int, default=20260923)
    args = ap.parse_args(argv)

    if not list(Path(HITS).parent.glob("*.parquet")):
        print("no hits yet — run scripts/20_lexicon_candidates.py first", file=sys.stderr)
        return 2

    lex = load_lexicon(ROOT / "config" / "lexicon_v2.yaml")
    con = duckdb.connect()
    con.execute(f"CREATE VIEW hits AS SELECT * FROM read_parquet('{HITS}')")
    con.execute(f"CREATE VIEW docs AS SELECT * FROM read_parquet('{DOCS}')")

    if args.all or not args.pattern:
        rows = con.execute(
            """SELECT pattern_id, tier, count(DISTINCT key || '-' || seq_documento) AS documents,
                      count(*) AS hits,
                      round(100.0 * sum(CASE WHEN negated_hint THEN 1 ELSE 0 END) / count(*), 1) AS negated_pct,
                      sum(CASE WHEN excluded_by IS NOT NULL THEN 1 ELSE 0 END) AS dropped
               FROM hits GROUP BY 1, 2 HAVING count(DISTINCT key || '-' || seq_documento) >= 5
               ORDER BY documents DESC"""
        ).fetchall()
        print(f"{'pattern':<36} {'tier':<10} {'documents':>10} {'hits':>10} {'negated%':>9} {'dropped':>8}")
        for pid, tier, docs, hits, neg, dropped in rows:
            print(f"{pid:<36} {tier:<10} {docs:>10,} {hits:>10,} {neg:>8.1f}% {dropped:>8,}".replace(",", "."))
        print(f"\n{len(rows)} patterns with >= 5 documents (k-anonymity rule). "
              f"Lexicon v{lex.version}, {len(lex.patterns)} patterns.")
        con.close()
        return 0

    try:
        pattern = lex.by_id(args.pattern)
    except KeyError:
        print(f"unknown pattern: {args.pattern}", file=sys.stderr)
        return 2

    where = ["pattern_id = ?"]
    params: list = [args.pattern]
    if args.year:
        where.append("substr(key, 1, 4) = ?")
        params.append(args.year)
    if args.negated:
        where.append("negated_hint")
    clause = " AND ".join(where)

    stats = con.execute(
        f"""SELECT count(*) , count(DISTINCT key || '-' || seq_documento),
                   sum(CASE WHEN negated_hint THEN 1 ELSE 0 END),
                   sum(CASE WHEN excluded_by IS NOT NULL THEN 1 ELSE 0 END)
            FROM hits WHERE {clause}""",
        params,
    ).fetchone()
    print(f"pattern   : {pattern.id}  [{pattern.tier}]"
          + (f"  Anexo A {', '.join(str(i) for i in pattern.annex_a)}" if pattern.annex_a else ""))
    print(f"regex     : {pattern.source}")
    if pattern.note:
        print(f"nota      : {pattern.note}")
    print(f"ocorrências: {stats[0]:,} em {stats[1]:,} documentos; {stats[2]:,} com marcador de negação; "
          f"{stats[3]:,} derrubadas por exclusão".replace(",", "."))
    print("-" * 110)

    con.execute(f"SELECT setseed({(args.seed % 10_000) / 10_000:.4f})")
    sample = con.execute(
        f"""SELECT key, seq_documento, match, context, negated_hint, excluded_by
            FROM hits WHERE {clause}
            ORDER BY hash(key || '-' || seq_documento || '-{args.seed}') LIMIT {args.sample}""",
        params,
    ).fetchall()
    for n, (key, seq, match, context, negated, excluded) in enumerate(sample, 1):
        flags = " ".join(x for x in ("[NEGADO]" if negated else "", f"[EXCLUÍDO: {excluded}]" if excluded else "") if x)
        print(f"{n}. doc_id {key}-{seq}   casou: «{match}»  {flags}")
        print(f"   …{context}…\n")
    print("Para ler a decisão inteira:  uv run python scripts/25_show_document.py <doc_id>")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
