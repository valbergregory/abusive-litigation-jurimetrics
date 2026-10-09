"""Phase 2, step 30 — procedural trajectories from the DataJud public API (design B).

The bridge (step 12) resolved 91,2 % of the 2024 candidates and 92,8 % of the 2025 ones into CNJ unified numbers
(feasibility §13.2), which is what design B needs: for each bridged case this step reads the case's class, subject
codes, judging body and the **full list of movimentos** from the public endpoint of the court it came from.

Two groups are collected, with the same instrument and in the same request pattern:

* ``candidato`` — every bridged case with at least one candidate document (lexicon v2.2);
* ``comparacao_nao_sinalizado`` — a seeded draw of bridged cases **never** signalled by the lexicon, taken from
  the same (publication year × court) cells and sized by ``--comparison-ratio``. CLAUDE.md §3: these are *not
  signalled*, never "legitimate"; and this is a sampling frame, not yet a matched design — matching happens in
  the analysis, with the researcher's gold set.

No label is produced or implied here. Trajectories are covariates, measured identically for both groups.

Measured on 2026-10-09, one connection to ``api_publica_tjsp``: 50 numbers per request → 42 s and 1,2 cases/s;
200 → 22 s and 9,1 cases/s; 500 → 13 s and 38,9 cases/s; 1.000 → 24 s and 42,1 cases/s. **The cost is per query,
not per case**, so the default batch is 500 (≈ 10 MB per response, comfortably inside ``--size``) and not the
small batch one would reach for by default. Trimming the ``_source`` to the stored leaf fields cuts the payload
by 28 % and changes nothing in the time, so the whole allow-list is requested and kept in the raw shard.

The comparison draw is ordered by ``hash(numero_processo || seed)``, so raising ``--comparison-ratio`` later with
the same seed *adds* cases without changing the ones already drawn — the pool can grow as the matching design
firms up. The run resumes per court against the recorded request (``<alias>.request.json``), not against the mere
existence of the shard, so a smoke run with ``--limit`` cannot make the full collection skip that court.

Privacy: the request asks for ``alj.datajud.CASE_FIELDS`` only, so nothing else reaches disk; the log reports any
new top-level field at the source instead of ingesting it (CLAUDE.md §§4–5).

Writes:
  data/interim/datajud/targets/targets.parquet      the target frame (reproducible, seeded)
  data/interim/datajud/cases/<alias>.parquet        CASE_SCHEMA, one row per case × grau
  data/interim/datajud/movimentos/<alias>.parquet   MOVEMENT_SCHEMA, one row per movement
  data/raw/datajud/trajectories/<alias>.jsonl.gz    raw responses (hashed in logs/raw_hashes.tsv)
  logs/30_fetch_datajud_trajectories.json           coverage per court and per year, timings, field check

Usage:
  uv run python scripts/30_fetch_datajud_trajectories.py --limit 500            # smoke run (one alias at a time)
  uv run python scripts/30_fetch_datajud_trajectories.py                        # full collection
  uv run python scripts/30_fetch_datajud_trajectories.py --years 2024,2025 --comparison-ratio 1.0
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import gzip
import json
import sys
import threading
import time
from pathlib import Path

import httpx
import polars as pl

if hasattr(sys.stdout, "reconfigure"):  # the Windows console is cp1252; logs are always UTF-8
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alj.datajud import (  # noqa: E402
    LICENCE,
    SEARCH_URL,
    TARGET_SCHEMA,
    WIKI_URL,
    batched,
    frames,
    iter_sources,
    parse_public_key,
    terms_body,
    total_hits,
    unexpected_fields,
)
from alj.db import connect_or_memory, create_views  # noqa: E402
from alj.manifest import file_identity, record_download  # noqa: E402

META = (ROOT / "data" / "interim" / "stj_integras" / "meta" / "*.parquet").as_posix()
BRIDGE = (ROOT / "data" / "interim" / "bridge" / "*.parquet").as_posix()
CAND = (ROOT / "data" / "interim" / "candidates" / "docs" / "*.parquet").as_posix()
OUT = ROOT / "data" / "interim" / "datajud"
RAW = ROOT / "data" / "raw" / "datajud" / "trajectories"
DB = ROOT / "data" / "alj.duckdb"
LOG = ROOT / "logs"
HASHES = LOG / "raw_hashes.tsv"

HEADERS = {"User-Agent": "abusive-litigation-jurimetrics/0.1 (research; contact via GitHub)"}
RETRY_STATUS = {408, 429, 500, 502, 503, 504}


def br(n: int) -> str:
    """Thousands with a dot, as the researcher reads them (pt-BR), without touching the rest of the sentence."""
    return f"{n:,}".replace(",", ".")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--years", default="", help="publication years of the STJ document, comma separated (default: all)")
    ap.add_argument("--comparison-ratio", type=float, default=1.0,
                    help="unsignalled cases per candidate case, drawn from the same year x court cell (0 = none)")
    ap.add_argument("--batch", type=int, default=500, help="case numbers per request (measured: the cost is per "
                                                           "query, not per case — see the module docstring)")
    ap.add_argument("--size", type=int, default=10000, help="max documents per response (a batch that would "
                                                            "overflow it is split, never paginated)")
    ap.add_argument("--workers", type=int, default=4, help="parallel requests (be polite with a public API)")
    ap.add_argument("--flush-every", type=int, default=4,
                    help="requests per Parquet shard: keeps memory flat on the big state courts")
    ap.add_argument("--limit", type=int, help="at most N target cases (smoke run)")
    ap.add_argument("--only", help="restrict to one alias, e.g. api_publica_tjsp")
    ap.add_argument("--force", action="store_true", help="re-fetch aliases already on disk")
    ap.add_argument("--seed", default="20261009", help="seed of the comparison draw (recorded in the log)")
    ap.add_argument("--no-raw", action="store_true", help="do not keep the raw responses")
    ap.add_argument("--timeout", type=float, default=120.0)
    return ap.parse_args(argv)


def build_targets(args: argparse.Namespace) -> pl.DataFrame:
    """The target frame: bridged candidate cases + the seeded comparison draw. Deterministic for a given seed.

    A case with *any* candidate decision is a candidate, and the comparison pool excludes every candidate case,
    so no case is in both groups. With ``--years`` the exclusion is evaluated inside the window, so a case
    signalled only outside it could be drawn as comparison — one more reason the default is all bridged years.
    """
    years = [y.strip() for y in args.years.split(",") if y.strip()]
    year_clause = ""
    if years:
        year_clause = " AND pub_year IN (" + ", ".join(f"'{y}'" for y in years) + ")"
    con = connect_or_memory(":memory:")[0]
    con.execute(
        f"""CREATE TABLE doc AS
            WITH m AS (SELECT DISTINCT key, seq_documento, numero_registro FROM read_parquet('{META}')),
                 b AS (SELECT DISTINCT numero_registro, cnj_digits, datajud_alias FROM read_parquet('{BRIDGE}')
                       WHERE datajud_alias IS NOT NULL AND cnj_valid),
                 c AS (SELECT DISTINCT key, seq_documento, strict_hit FROM read_parquet('{CAND}') WHERE is_candidate)
            SELECT b.cnj_digits AS numero_processo, b.datajud_alias AS alias, substr(m.key, 1, 4) AS pub_year,
                   c.key IS NOT NULL AS is_cand, coalesce(c.strict_hit, false) AS strict_hit
            FROM m JOIN b ON b.numero_registro = m.numero_registro
            LEFT JOIN c ON c.key = m.key AND c.seq_documento = m.seq_documento"""
    )
    con.execute(
        f"""CREATE TABLE cand_t AS
            SELECT numero_processo, alias, 'candidato' AS grupo, min(pub_year) AS pub_year,
                   max(strict_hit) AS strict_hit, cast(count(*) AS INTEGER) AS n_documentos
            FROM doc WHERE is_cand{year_clause} GROUP BY 1, 2, 3"""
    )
    if args.comparison_ratio > 0:
        con.execute(
            f"""CREATE TABLE comp_t AS
                WITH pool AS (
                    SELECT numero_processo, alias, min(pub_year) AS pub_year,
                           cast(count(*) AS INTEGER) AS n_documentos
                    FROM doc WHERE NOT is_cand{year_clause}
                      AND numero_processo NOT IN (SELECT numero_processo FROM cand_t)
                    GROUP BY 1, 2),
                quota AS (SELECT alias, pub_year,
                                 cast(ceil(count(*) * {args.comparison_ratio}) AS BIGINT) AS q
                          FROM cand_t GROUP BY 1, 2),
                ranked AS (
                    SELECT p.*, q.q,
                           row_number() OVER (PARTITION BY p.alias, p.pub_year
                                              ORDER BY hash(p.numero_processo || '{args.seed}')) AS rn
                    FROM pool p JOIN quota q ON q.alias = p.alias AND q.pub_year = p.pub_year)
                SELECT numero_processo, alias, 'comparacao_nao_sinalizado' AS grupo, pub_year,
                       false AS strict_hit, n_documentos
                FROM ranked WHERE rn <= q"""
        )
    else:
        con.execute("CREATE TABLE comp_t AS SELECT * FROM cand_t WHERE false")
    frame = con.execute(
        """SELECT numero_processo, alias, grupo, pub_year, strict_hit, n_documentos FROM cand_t
           UNION ALL BY NAME
           SELECT numero_processo, alias, grupo, pub_year, strict_hit, n_documentos FROM comp_t
           ORDER BY alias, grupo, numero_processo"""
    ).pl()
    con.close()
    return frame.cast(TARGET_SCHEMA)  # type: ignore[arg-type]


def forget_manifest_line(path: Path) -> None:
    """Drop the manifest line of ``path`` so a re-collected shard is hashed again.

    The manifest is append-once per file *identity* (``alj.manifest``), which is right for downloads that never
    change. A re-run of this step rewrites the raw shard, so the old SHA-256 would describe a file that no longer
    exists; the line is removed and recorded again instead of left stale.
    """
    if not HASHES.exists():
        return
    identity = file_identity(path, ROOT)
    lines = HASHES.read_text(encoding="utf-8").splitlines()
    kept = [ln for ln in lines if ln.rsplit("\t", 1)[-1] != identity]
    if len(kept) != len(lines):
        HASHES.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")


def fetch_batch(client: httpx.Client, key: str, alias: str, numbers: list[str], size: int) -> list[dict]:
    """The documents of one batch of case numbers. Splits the batch instead of paginating, retries on 429/5xx."""
    body = terms_body(numbers, size=size)
    last: Exception | None = None
    for attempt in range(5):
        try:
            response = client.post(
                SEARCH_URL.format(alias=alias), json=body, headers={**HEADERS, "Authorization": f"APIKey {key}"}
            )
            if response.status_code in RETRY_STATUS:
                last = httpx.HTTPStatusError(f"HTTP {response.status_code}", request=response.request,
                                             response=response)
                time.sleep(2**attempt)
                continue
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            last = exc
            time.sleep(2**attempt)
            continue
        if total_hits(payload) > size and len(numbers) > 1:  # a batch too wide for one response: split it
            half = len(numbers) // 2
            return (fetch_batch(client, key, alias, numbers[:half], size)
                    + fetch_batch(client, key, alias, numbers[half:], size))
        return list(iter_sources(payload))
    raise RuntimeError(f"{alias}: batch of {len(numbers)} failed after 5 attempts ({last})")


def main(argv: list[str] | None = None) -> int:  # noqa: C901 — one linear collection, kept in one place
    args = parse_args(argv)
    for folder in (OUT / "targets", OUT / "cases", OUT / "movimentos", RAW, LOG):
        folder.mkdir(parents=True, exist_ok=True)
    if not list(Path(BRIDGE).parent.glob("*.parquet")):
        print("no bridge yet — run scripts/12_ingest_stj_bridge.py first", file=sys.stderr)
        return 2
    t_all = time.time()

    targets = build_targets(args)
    if args.only:
        targets = targets.filter(pl.col("alias") == args.only)
    if args.limit:
        targets = targets.head(args.limit)
    if not targets.height:
        print("no targets — check --years/--only", file=sys.stderr)
        return 1
    targets.write_parquet(OUT / "targets" / "targets.parquet")
    by_group = dict(targets.group_by("grupo").len().iter_rows())
    print(f"{br(targets.height)} target cases in {targets['alias'].n_unique()} courts "
          f"({by_group}); seed {args.seed}", flush=True)

    with httpx.Client(timeout=args.timeout, follow_redirects=True, headers=HEADERS,
                      limits=httpx.Limits(max_connections=max(args.workers, 1) + 2)) as client:
        key = parse_public_key(client.get(WIKI_URL).text)  # CLAUDE.md §8: never hard-coded
        print(f"public API key read from the wiki ({len(key)} chars)", flush=True)

        per_alias: list[dict] = []
        new_fields: dict[str, list[str]] = {}
        errors: list[dict] = []
        lock = threading.Lock()

        for alias, group in targets.group_by("alias", maintain_order=True):
            alias = alias[0] if isinstance(alias, tuple) else alias
            numbers = group["numero_processo"].to_list()
            # Resume by *request*, not by file: a smoke run with --limit leaves a partial shard, and skipping it
            # because the file exists would drop that court from the collection in silence.
            receipt = OUT / "cases" / f"{alias}.request.json"
            request_id = {"requested": len(numbers), "years": args.years, "seed": args.seed,
                          "comparison_ratio": args.comparison_ratio}
            if receipt.exists() and not args.force:
                done = json.loads(receipt.read_text(encoding="utf-8"))
                if {k: done.get(k) for k in request_id} == request_id:
                    print(f"  skip {alias} (already collected for this request)")
                    per_alias.append({"alias": alias, "skipped": True, **done})
                    continue
            t0 = time.time()
            for stale in (list((OUT / "cases").glob(f"{alias}*.parquet"))
                          + list((OUT / "movimentos").glob(f"{alias}*.parquet"))):
                stale.unlink()  # a previous, differently-shaped run must not leave shards behind
            raw_path = RAW / f"{alias}.jsonl.gz"
            raw_mode = "wt"
            found_numbers: set[str] = set()
            n_documents = n_movements = 0
            # The big state courts have tens of thousands of cases with ~100 movements each, so a wave of
            # requests is turned into Parquet and released instead of held until the court is finished.
            chunks = list(batched(numbers, args.batch))
            for shard, wave in enumerate(batched(chunks, args.flush_every)):
                sources: list[dict] = []
                with cf.ThreadPoolExecutor(max_workers=max(args.workers, 1)) as pool:
                    futures = {
                        pool.submit(fetch_batch, client, key, alias, chunk, args.size): chunk for chunk in wave
                    }
                    for future in cf.as_completed(futures):
                        try:
                            got = future.result()
                        except Exception as exc:  # report, never silently skip
                            errors.append({"alias": alias, "numbers": len(futures[future]), "error": str(exc)[:300]})
                            print(f"    ! {alias}: {exc}", file=sys.stderr, flush=True)
                            continue
                        with lock:
                            sources.extend(got)
                if not sources:
                    continue
                for source in sources[:200]:  # the source is homogeneous; checking a slice is enough and cheap
                    extra = unexpected_fields(source)
                    if extra:
                        new_fields[alias] = sorted(set(new_fields.get(alias, [])) | set(extra))
                cases, movements = frames(sources, alias=alias)
                cases.write_parquet(OUT / "cases" / f"{alias}-{shard:03d}.parquet")
                movements.write_parquet(OUT / "movimentos" / f"{alias}-{shard:03d}.parquet")
                found_numbers.update(cases["numero_processo"].to_list())
                n_documents += cases.height
                n_movements += movements.height
                if not args.no_raw:
                    with gzip.open(raw_path, raw_mode, encoding="utf-8") as fh:
                        for source in sources:
                            fh.write(json.dumps(source, ensure_ascii=False) + "\n")
                    raw_mode = "at"  # successive gzip members: still one readable .jsonl.gz
                del sources, cases, movements

            if not args.no_raw and raw_path.exists():
                forget_manifest_line(raw_path)
                record_download(raw_path, f"DataJud {alias} (_search terms on numeroProcesso)", HASHES,
                                licence=LICENCE, root=ROOT)
            receipt.write_text(
                json.dumps({**request_id, "found_cases": len(found_numbers), "documents": n_documents,
                            "movements": n_movements,
                            "collected_at": dt.datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False),
                encoding="utf-8",
            )
            per_alias.append({
                "alias": alias,
                "requested": len(numbers),
                "found_cases": len(found_numbers),
                "documents": n_documents,
                "movements": n_movements,
                "coverage_pct": round(100.0 * len(found_numbers) / len(numbers), 1),
                "seconds": round(time.time() - t0, 1),
                "skipped": False,
            })
            print(f"  {alias}: {br(len(found_numbers))}/{br(len(numbers))} cases, "
                  f"{br(n_movements)} movements ({round(time.time() - t0, 1)}s)", flush=True)

    con, is_file = connect_or_memory(DB)
    views = create_views(con, ROOT, ["datajud_targets", "datajud_cases", "datajud_movimentos"])

    def rows_of(sql: str, cols: list[str]) -> list[dict]:
        return [dict(zip(cols, row, strict=True)) for row in con.execute(sql).fetchall()]

    coverage = movements_stats = None
    if views.get("datajud_cases"):
        coverage = rows_of(
            """WITH t AS (SELECT * FROM datajud_targets), c AS (SELECT DISTINCT numero_processo FROM datajud_cases)
               SELECT t.pub_year, t.grupo, count(*) AS targets, count(c.numero_processo) AS found,
                      round(100.0 * count(c.numero_processo) / count(*), 1) AS pct
               FROM t LEFT JOIN c ON c.numero_processo = t.numero_processo
               GROUP BY 1, 2 HAVING count(*) >= 5 ORDER BY 1, 2""",
            ["pub_year", "grupo", "targets", "found", "pct"],
        )
        movements_stats = rows_of(
            """SELECT t.grupo, count(DISTINCT c.numero_processo) AS cases,
                      round(avg(c.n_movimentos), 1) AS mean_movements,
                      median(c.n_movimentos) AS median_movements,
                      max(c.n_movimentos) AS max_movements
               FROM datajud_cases c JOIN datajud_targets t ON t.numero_processo = c.numero_processo
               GROUP BY 1 HAVING count(*) >= 5 ORDER BY 1""",
            ["grupo", "cases", "mean_movements", "median_movements", "max_movements"],
        )
    con.close()

    done = [r for r in per_alias if not r["skipped"]]
    out = {
        "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "design": "B — judicial signalling + procedural trajectory (researcher's decision of 2026-09-23)",
        "years": args.years or "all bridged years",
        "comparison_ratio": args.comparison_ratio,
        "seed": args.seed,
        "target_cases": targets.height,
        "targets_by_group": {k: v for k, v in by_group.items()},
        "aliases": len(per_alias),
        "requested": sum(r.get("requested", 0) for r in done),
        "found_cases": sum(r.get("found_cases", 0) for r in done),
        "documents": sum(r.get("documents", 0) for r in done),
        "movements": sum(r.get("movements", 0) for r in done),
        "per_alias": per_alias,
        "coverage_by_year_and_group_k_ge_5": coverage,
        "movements_by_group_k_ge_5": movements_stats,
        "new_fields_at_the_source": new_fields or None,
        "errors": errors,
        "views_created": is_file,
        "note": ("trajectories are covariates measured identically for both groups; they are not labels, and the "
                 "comparison group is 'not signalled', never 'legitimate' (CLAUDE.md §§2-3)"),
        "minutes": round((time.time() - t_all) / 60, 1),
        "next": "uv run python scripts/19_refresh_duckdb_views.py   # then step 22 once the gold set exists",
    }
    json.dump(out, open(LOG / "30_fetch_datajud_trajectories.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k not in {"per_alias", "errors"}},
                     ensure_ascii=False, indent=1))
    if new_fields:
        print(f"the source grew fields: {new_fields} — check them before ingesting", file=sys.stderr)
    if errors:
        print(f"{len(errors)} batch(es) failed — re-run with --force for those aliases", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
