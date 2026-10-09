"""Phase 2, step 31 — trajectory covariates per case, from the movements collected by step 30.

Two modes:

``--vocabulary``
    lists the movement codes actually present in the collected data, with how many cases carry each one in the
    signalled and in the unsignalled group (k ≥ 5). This is what ``config/movement_groups.yaml`` is built from:
    the groups must name codes this corpus uses, not codes a table says exist.

default
    builds one row per case with the covariates defined in ``alj.trajectories.feature_sql`` plus one count and
    one first-occurrence timestamp per movement group, and reports the descriptive comparison between the two
    groups (medians, shares, by year, k ≥ 5).

Nothing here is a label (CLAUDE.md §2): ``grupo`` records whether the case's STJ decisions carried lexicon
signals, and the comparison group is "not signalled", never "legitimate" (§3). The descriptive comparison is a
measurement of the two groups' trajectories, not evidence that either group litigated abusively.

Writes:
  data/interim/datajud/features/features.parquet   one row per case (view `datajud_features`)
  logs/31_trajectory_features.json                 counts, descriptive comparison, config version
  logs/31_movement_vocabulary.json                 with --vocabulary

Usage:
  uv run python scripts/31_trajectory_features.py --vocabulary --top 60
  uv run python scripts/31_trajectory_features.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alj.db import connect_or_memory, create_views  # noqa: E402
from alj.trajectories import feature_sql, load_movement_groups  # noqa: E402

CASES = (ROOT / "data" / "interim" / "datajud" / "cases" / "*.parquet").as_posix()
MOVES = (ROOT / "data" / "interim" / "datajud" / "movimentos" / "*.parquet").as_posix()
TARGETS = (ROOT / "data" / "interim" / "datajud" / "targets" / "*.parquet").as_posix()
OUT = ROOT / "data" / "interim" / "datajud" / "features"
CONFIG = ROOT / "config" / "movement_groups.yaml"
DB = ROOT / "data" / "alj.duckdb"
LOG = ROOT / "logs"
K = 5  # k-anonymity floor for every reported breakdown (CLAUDE.md §4)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vocabulary", action="store_true", help="list the movement codes present in the data")
    ap.add_argument("--top", type=int, default=60, help="codes to list with --vocabulary")
    ap.add_argument("--config", default=str(CONFIG), help="movement groups (versioned instrument)")
    return ap.parse_args(argv)


def views(con) -> dict:
    con.execute(f"CREATE OR REPLACE VIEW dj_cases AS SELECT * FROM read_parquet('{CASES}')")
    con.execute(f"CREATE OR REPLACE VIEW dj_moves AS SELECT * FROM read_parquet('{MOVES}')")
    con.execute(f"CREATE OR REPLACE VIEW dj_targets AS SELECT * FROM read_parquet('{TARGETS}')")
    return {
        "cases": con.execute("SELECT count(*) FROM dj_cases").fetchone()[0],
        "movements": con.execute("SELECT count(*) FROM dj_moves").fetchone()[0],
        "targets": con.execute("SELECT count(*) FROM dj_targets").fetchone()[0],
    }


def rows_of(con, sql: str, cols: list[str]) -> list[dict]:
    return [dict(zip(cols, row, strict=True)) for row in con.execute(sql).fetchall()]


def integrity(con) -> dict:
    """Checks that must hold on the collection; each one is a count that should be zero.

    They are recorded in the log on every run, because a silent breach here (a case that is not a target, a
    movement without its case, a duplicated document) would travel unnoticed into every later number.
    """
    def count(sql: str) -> int:
        return con.execute(sql).fetchone()[0]

    return {
        "cases_not_in_targets": count(
            """SELECT count(*) FROM (SELECT DISTINCT numero_processo, alias FROM dj_cases) c
               LEFT JOIN (SELECT DISTINCT numero_processo, alias FROM dj_targets) t
                 USING (numero_processo, alias) WHERE t.numero_processo IS NULL"""
        ),
        "case_numbers_not_20_digits": count(
            "SELECT count(*) FROM dj_cases WHERE numero_processo IS NULL OR length(numero_processo) <> 20"
        ),
        "duplicate_documents": count(
            "SELECT count(*) FROM (SELECT numero_processo, grau, es_id FROM dj_cases GROUP BY 1, 2, 3 "
            "HAVING count(*) > 1)"
        ),
        "movements_out_of_order_within_a_document": count(
            """SELECT count(*) FROM (
                   SELECT data_hora, lag(data_hora) OVER (PARTITION BY es_id ORDER BY ordem) AS prev
                   FROM dj_moves WHERE data_hora IS NOT NULL)
               WHERE prev IS NOT NULL AND data_hora < prev"""
        ),
        "movements_without_their_case": count(
            """SELECT count(*) FROM (SELECT DISTINCT es_id FROM dj_moves) m
               LEFT JOIN (SELECT DISTINCT es_id FROM dj_cases) c USING (es_id) WHERE c.es_id IS NULL"""
        ),
        "cases_with_nonzero_sigilo": count("SELECT count(*) FROM dj_cases WHERE nivel_sigilo > 0"),
    }


def vocabulary(con, top: int) -> list[dict]:
    """Movement codes by how many *cases* carry them, split by group — the evidence for the config."""
    return rows_of(
        con,
        f"""WITH per_case AS (
                SELECT DISTINCT m.codigo, m.nome, m.numero_processo, m.alias FROM dj_moves m),
            joined AS (
                SELECT p.codigo, p.nome, t.grupo
                FROM per_case p JOIN (SELECT DISTINCT numero_processo, alias, grupo FROM dj_targets) t
                  ON t.numero_processo = p.numero_processo AND t.alias = p.alias)
            SELECT codigo, any_value(nome) AS nome,
                   count(*) FILTER (WHERE grupo = 'candidato') AS casos_sinalizados,
                   count(*) FILTER (WHERE grupo = 'comparacao_nao_sinalizado') AS casos_nao_sinalizados,
                   count(*) AS casos
            FROM joined GROUP BY codigo
            HAVING count(*) >= {K}
            ORDER BY casos DESC LIMIT {top}""",
        ["codigo", "nome", "casos_sinalizados", "casos_nao_sinalizados", "casos"],
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    LOG.mkdir(exist_ok=True)
    if not list(Path(CASES).parent.glob("*.parquet")):
        print("no trajectories yet — run scripts/30_fetch_datajud_trajectories.py first", file=sys.stderr)
        return 2
    t0 = time.time()
    con, _ = connect_or_memory(":memory:")  # read the Parquet directly; never lock the database for a read
    counts = views(con)
    print(f"{counts['cases']:,} case documents, {counts['movements']:,} movements, "
          f"{counts['targets']:,} targets".replace(",", "."), flush=True)

    if args.vocabulary:
        codes = vocabulary(con, args.top)
        out = {
            "run_at": dt.datetime.now().isoformat(timespec="seconds"),
            "counts": counts,
            "k_anonymity_floor": K,
            "codes": codes,
            "note": ("case counts per movement code; the two groups are 'signalled by the lexicon' and 'not "
                     "signalled' — never 'abusive' and 'legitimate' (CLAUDE.md §§2-3)"),
            "next": "write config/movement_groups.yaml with the codes that matter, then run step 31 without --vocabulary",
        }
        json.dump(out, open(LOG / "31_movement_vocabulary.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"{'código':>8} {'casos':>9} {'sinaliz.':>9} {'não sin.':>9}  movimento")
        for row in codes:
            print(f"{row['codigo']:>8} {row['casos']:>9,} {row['casos_sinalizados']:>9,} "
                  f"{row['casos_nao_sinalizados']:>9,}  {(row['nome'] or '')[:60]}".replace(",", "."))
        con.close()
        return 0

    groups = load_movement_groups(args.config)
    OUT.mkdir(parents=True, exist_ok=True)
    sql = feature_sql(groups, cases="dj_cases", movimentos="dj_moves", targets="dj_targets")
    target = (OUT / "features.parquet").as_posix()
    con.execute(f"COPY ({sql}) TO '{target}' (FORMAT PARQUET)")
    con.execute(f"CREATE OR REPLACE VIEW feat AS SELECT * FROM read_parquet('{target}')")

    group_cols = [g.id for g in groups.groups]
    comparison = rows_of(
        con,
        f"""SELECT grupo,
                   count(*) AS casos,
                   count(*) FILTER (WHERE nao_encontrado_no_datajud) AS nao_encontrados,
                   round(avg(n_movimentos), 1) AS media_movimentos,
                   median(n_movimentos) AS mediana_movimentos,
                   median(dias_entre_movimentos) AS mediana_dias,
                   median(dias_desde_ajuizamento) AS mediana_dias_ajuizamento,
                   round(avg(n_orgaos_movimento), 2) AS media_orgaos,
                   {", ".join(f"round(100.0 * avg(CASE WHEN n_{c} > 0 THEN 1 ELSE 0 END), 1) AS pct_{c}"
                              for c in group_cols)}
            FROM feat GROUP BY 1 HAVING count(*) >= {K} ORDER BY 1""",
        ["grupo", "casos", "nao_encontrados", "media_movimentos", "mediana_movimentos", "mediana_dias",
         "mediana_dias_ajuizamento", "media_orgaos"] + [f"pct_{c}" for c in group_cols],
    )
    by_year = rows_of(
        con,
        f"""SELECT pub_year, grupo, count(*) AS casos, median(n_movimentos) AS mediana_movimentos,
                   median(dias_entre_movimentos) AS mediana_dias
            FROM feat GROUP BY 1, 2 HAVING count(*) >= {K} ORDER BY 1, 2""",
        ["pub_year", "grupo", "casos", "mediana_movimentos", "mediana_dias"],
    )
    strict = rows_of(
        con,
        f"""SELECT strict_hit, count(*) AS casos, median(n_movimentos) AS mediana_movimentos,
                   median(dias_entre_movimentos) AS mediana_dias
            FROM feat WHERE grupo = 'candidato' GROUP BY 1 HAVING count(*) >= {K} ORDER BY 1""",
        ["strict_hit", "casos", "mediana_movimentos", "mediana_dias"],
    )
    total = con.execute("SELECT count(*) FROM feat").fetchone()[0]
    checks = integrity(con)
    breached = {k: v for k, v in checks.items() if v and k != "cases_with_nonzero_sigilo"}
    # Data quality measured on 2026-10-09: the same case is sometimes published as several DataJud documents of
    # the same grau with overlapping movement lists, so the raw row count inflates the movement volume.
    quality = {
        "cases_with_several_documents_in_the_same_grau": con.execute(
            """SELECT count(*) FROM (SELECT numero_processo, alias, grau FROM dj_cases
               GROUP BY 1, 2, 3 HAVING count(*) > 1)"""
        ).fetchone()[0],
        "movement_rows": con.execute("SELECT count(*) FROM dj_moves").fetchone()[0],
        "distinct_movements": con.execute(
            """SELECT count(*) FROM (SELECT DISTINCT numero_processo, alias, codigo, data_hora, orgao_codigo
               FROM dj_moves)"""
        ).fetchone()[0],
    }
    quality["inflation_if_not_deduplicated"] = (
        round(quality["movement_rows"] / quality["distinct_movements"], 3) if quality["distinct_movements"] else None
    )
    con.close()

    db, is_file = connect_or_memory(DB)
    created = create_views(db, ROOT, ["datajud_features"])
    db.close()

    out = {
        "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "movement_groups_version": groups.version,
        "movement_groups": [{"id": g.id, "label": g.label, "label_en": g.label_en or g.label,
                             "codes": list(g.codes), "name_contains": list(g.name_contains)}
                            for g in groups.groups],
        "counts": counts,
        "feature_rows": total,
        "integrity": checks,
        "data_quality": quality,
        "k_anonymity_floor": K,
        "comparison_by_group": comparison,
        "by_year_and_group": by_year,
        "candidates_by_strict_term": strict,
        "caveat": ("trajectory covariates, not labels: 'candidato' means the case's STJ decisions carried lexicon "
                   "signals and 'comparacao_nao_sinalizado' means they did not (CLAUDE.md §§2-3). The comparison "
                   "is descriptive and unmatched; matching comes with the researcher's gold set"),
        "views_created": is_file and bool(created.get("datajud_features")),
        "minutes": round((time.time() - t0) / 60, 1),
    }
    json.dump(out, open(LOG / "31_trajectory_features.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "movement_groups"}, ensure_ascii=False, indent=1))
    if breached:
        print(f"integrity breached: {breached} — the feature table is written, but do not use it until this is "
              f"explained", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
