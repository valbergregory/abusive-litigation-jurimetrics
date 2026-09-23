"""Phase 1, step 11 — download and ingest the *espelhos de acórdãos* of the ten STJ judging bodies.

For each CKAN dataset (``espelhos-de-acordaos-<órgão>``) the script reads ``package_show`` at run time (no
hard-coded resource URL), downloads the monthly JSON files that are missing locally — ~105 MB per body, ~1 GB in
total — and parses them into Parquet with `alj.espelhos`. Every download appends a SHA-256 line to
logs/raw_hashes.tsv (CLAUDE.md §7); a file already on disk with the published size is not downloaded again.

The initial ZIP of each dataset is ingested too (since 2026-09-23). It is NOT a duplicate of the monthly
series: the probe in `scripts/11b_probe_espelho_zip.py` measured 14,223 records for the Corte Especial alone,
published between 1989 and 2022-06, with 92 registrations in common with the monthly files. Use `--no-zips` to
skip them.

Writes:
  data/raw/stj_espelhos/<orgao>/<file>.json          the published files (git-ignored)
  data/interim/espelhos/{espelhos,citations,legislation}/<orgao>_<file>.parquet
  data/alj.duckdb                                    views `espelhos`, `espelho_citations`, `espelho_legislation`
  logs/raw_hashes.tsv, logs/11_ingest_stj_espelhos.json

Usage:  uv run python scripts/11_ingest_stj_espelhos.py [--orgaos terceira-turma …] [--workers 6] [--no-download]
        uv run python scripts/11_ingest_stj_espelhos.py --limit-files 2      # smoke run
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alj.db import connect_or_memory, create_views  # noqa: E402
from alj.espelhos import read_espelhos, read_espelhos_zip  # noqa: E402
from alj.manifest import record_download  # noqa: E402

CKAN = "https://dadosabertos.web.stj.jus.br/api/3/action/package_show"
ORGAOS = (
    "corte-especial",
    "primeira-secao",
    "segunda-secao",
    "terceira-secao",
    "primeira-turma",
    "segunda-turma",
    "terceira-turma",
    "quarta-turma",
    "quinta-turma",
    "sexta-turma",
)
RAW = ROOT / "data" / "raw" / "stj_espelhos"
INTERIM = ROOT / "data" / "interim" / "espelhos"
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
    ap.add_argument("--orgaos", nargs="*", default=list(ORGAOS), choices=list(ORGAOS))
    ap.add_argument("--no-download", action="store_true", help="parse only what is already on disk")
    ap.add_argument("--no-zips", action="store_true", help="skip the initial backlog ZIP of each dataset")
    ap.add_argument("--limit-files", type=int, help="at most N published files per body (smoke run)")
    ap.add_argument("--limit-records", type=int, help="at most N records per file (smoke run)")
    ap.add_argument("--force", action="store_true", help="re-parse files whose Parquet already exists")
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--workers", type=int, default=6, help="parallel downloads (the portal is slow per connection)")
    return ap.parse_args(argv)


def resources(client: httpx.Client, slug: str) -> list[dict]:
    r = client.get(CKAN, params={"id": f"espelhos-de-acordaos-{slug}"})
    r.raise_for_status()
    payload = r.json()
    if not payload.get("success"):
        raise RuntimeError(f"CKAN package_show failed for {slug}")
    return payload["result"]["resources"]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    salt = load_salt()
    for sub in ("espelhos", "citations", "legislation"):
        (INTERIM / sub).mkdir(parents=True, exist_ok=True)
    LOG.mkdir(exist_ok=True)

    t_all = time.time()
    per_orgao: list[dict] = []
    totals = {"files": 0, "downloaded": 0, "bytes": 0, "espelhos": 0, "citations": 0, "legislation": 0, "zips": 0}
    with httpx.Client(timeout=args.timeout, follow_redirects=True,
                      limits=httpx.Limits(max_connections=max(args.workers, 1) + 2),
                      headers={"User-Agent": "abusive-litigation-jurimetrics/0.1 (research; contact via GitHub)"}) as client:
        # 1) resource inventory (one CKAN call per body), 2) parallel download, 3) sequential parse.
        # The published files are ~1.7 MB each and the portal serves one connection slowly (~80 kB/s), so the
        # downloads run in a small thread pool; everything is resumable because a file whose size matches the
        # published size is never fetched again.
        inventory: dict[str, list[dict]] = {}
        for slug in args.orgaos:
            try:
                res = resources(client, slug)
            except Exception as exc:  # network or CKAN problem: report, never invent
                print(f"  {slug}: CKAN unavailable ({exc})", file=sys.stderr)
                per_orgao.append({"orgao": slug, "error": str(exc)})
                continue
            jsons = sorted((r for r in res if (r.get("format") or "").upper() == "JSON"),
                           key=lambda r: r.get("name") or "")
            zips = [] if args.no_zips else [r for r in res if (r.get("format") or "").upper() == "ZIP"]
            totals["zips"] += len(zips)
            chosen = jsons[: args.limit_files] if args.limit_files else jsons
            inventory[slug] = chosen + zips
            (RAW / slug).mkdir(parents=True, exist_ok=True)
            print(f"  {slug}: {len(chosen)} JSON + {len(zips)} ZIP resources", flush=True)

        def local_path(slug: str, r: dict) -> Path:
            return RAW / slug / (r.get("name") or Path(r["url"]).name)

        def needs_download(slug: str, r: dict) -> bool:
            local = local_path(slug, r)
            size = r.get("size") or 0
            return not local.exists() or bool(size and local.stat().st_size != size)

        pending = [(slug, r) for slug, rs in inventory.items() for r in rs if needs_download(slug, r)]
        if pending and not args.no_download:
            print(f"  downloading {len(pending)} file(s) with {args.workers} workers", flush=True)

            def fetch(item: tuple[str, dict]) -> tuple[str, Path, int]:
                slug, r = item
                local = local_path(slug, r)
                tmp = local.with_suffix(local.suffix + ".part")
                with client.stream("GET", r["url"]) as response:
                    response.raise_for_status()
                    with open(tmp, "wb") as fh:
                        for chunk in response.iter_bytes(1 << 20):
                            fh.write(chunk)
                tmp.replace(local)
                record_download(local, r["url"], HASHES, root=ROOT)
                return slug, local, local.stat().st_size

            with cf.ThreadPoolExecutor(max_workers=max(args.workers, 1)) as pool:
                futures = {pool.submit(fetch, item): item for item in pending}
                for n, future in enumerate(cf.as_completed(futures), 1):
                    slug, r = futures[future]
                    try:
                        _, local, size = future.result()
                    except Exception as exc:
                        print(f"    ! {slug}/{r.get('name')}: {exc}", file=sys.stderr)
                        continue
                    totals["downloaded"] += 1
                    totals["bytes"] += size
                    if n % 25 == 0 or n == len(pending):
                        print(f"    [{n}/{len(pending)}] {round(totals['bytes'] / 1e6, 1)} MB", flush=True)

        for slug, jsons in inventory.items():
            t0 = time.time()
            n_esp = n_cit = n_leg = 0
            downloaded = sum(1 for r in jsons if not needs_download(slug, r))
            for r in jsons:
                local = local_path(slug, r)
                if not local.exists():
                    continue
                is_zip = local.suffix.lower() == ".zip"
                stem = f"{slug}_{'zip_' if is_zip else ''}{local.stem}"
                target = INTERIM / "espelhos" / f"{stem}.parquet"
                if target.exists() and not args.force and not args.limit_records:
                    continue
                reader = read_espelhos_zip if is_zip else read_espelhos
                esp, cit, leg = reader(local, orgao_slug=slug, salt=salt, limit=args.limit_records)
                if esp.height:
                    esp.write_parquet(target)
                if cit.height:
                    cit.write_parquet(INTERIM / "citations" / f"{stem}.parquet")
                if leg.height:
                    leg.write_parquet(INTERIM / "legislation" / f"{stem}.parquet")
                n_esp += esp.height
                n_cit += cit.height
                n_leg += leg.height
            per_orgao.append({"orgao": slug, "json_resources": len(jsons), "files_on_disk": downloaded,
                              "espelhos": n_esp, "citations": n_cit, "legislation": n_leg,
                              "seconds": round(time.time() - t0, 1)})
            totals["files"] += len(jsons)
            totals["espelhos"] += n_esp
            totals["citations"] += n_cit
            totals["legislation"] += n_leg
            print(f"  {slug}: {downloaded}/{len(jsons)} files on disk, {n_esp} espelhos, "
                  f"{n_cit} citations, {n_leg} legislative refs ({round(time.time() - t0, 1)}s)", flush=True)

    con, is_file = connect_or_memory(DB)  # the database may be locked by another step; stats still work
    stats: dict = {"views_created": is_file}
    create_views(con, ROOT, ["espelhos", "espelho_citations", "espelho_legislation"])
    if any((INTERIM / "espelhos").glob("*.parquet")):
        stats["rows"] = {
            "espelhos": con.execute("SELECT count(*) FROM espelhos").fetchone()[0],
            "distinct_numero_registro": con.execute("SELECT count(DISTINCT numero_registro) FROM espelhos").fetchone()[0],
        }
        stats["by_year"] = [
            dict(zip(["year", "espelhos", "with_tema", "with_citations"], row, strict=True))
            for row in con.execute(
                """SELECT year(data_publicacao) AS year, count(*),
                          sum(CASE WHEN tema IS NOT NULL THEN 1 ELSE 0 END),
                          sum(CASE WHEN n_citations > 0 THEN 1 ELSE 0 END)
                   FROM espelhos WHERE data_publicacao IS NOT NULL GROUP BY 1 ORDER BY 1"""
            ).fetchall()
        ]
        stats["by_orgao"] = [
            dict(zip(["orgao", "espelhos"], row, strict=True))
            for row in con.execute("SELECT orgao_slug, count(*) FROM espelhos GROUP BY 1 ORDER BY 2 DESC").fetchall()
        ]
    if any((INTERIM / "legislation").glob("*.parquet")):
        stats["top_legislation"] = [
            dict(zip(["kind", "number", "year", "n"], row, strict=True))
            for row in con.execute(
                """SELECT kind, number, year, count(*) AS n FROM espelho_legislation
                   GROUP BY 1, 2, 3 HAVING count(*) >= 5 ORDER BY n DESC LIMIT 15"""
            ).fetchall()
        ]
    con.close()

    out = {
        "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "orgaos": per_orgao,
        "totals": {**totals, "megabytes_downloaded": round(totals["bytes"] / 1e6, 1)},
        "note": ("the initial ZIP of each dataset is ingested since 2026-09-23: it holds the historical backlog "
                 "(measured back to 1989) and is not a duplicate of the monthly series — see logs/11b_probe_espelho_zip.json"),
        **stats,
        "minutes": round((time.time() - t_all) / 60, 1),
    }
    json.dump(out, open(LOG / "11_ingest_stj_espelhos.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k not in ("orgaos", "top_legislation")},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
