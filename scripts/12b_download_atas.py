"""Phase 1, step 12b — download the *atas de distribuição* (authorised by the researcher on 2026-09-23).

The atas are the historical half of the bridge: every case distributed in the STJ since 2023-06-30, with the
``numeroRegistro`` ↔ ``numeroUnico`` pair that the acervo snapshot only has for pending cases (feasibility §4 and
§11.4 — the acervo alone resolves 1.3–2.2 % of the 2021–2024 candidates).

Downloads only; the parsing is step 12 (`--atas data/raw/stj_atas`), which reads **bridge fields only**: the
party and lawyer fields of these files are NOT ingested until the design-C ethics protocol is approved
(CLAUDE.md §§4–5). Measured on 2026-09-23: 1.010 JSON resources, 4.17 GB.

Every file gets a SHA-256 line in logs/raw_hashes.tsv; a file already on disk with the published size is not
fetched again, so the run is resumable.

Usage:  uv run python scripts/12b_download_atas.py [--workers 6] [--from 20230630] [--to 20261231] [--limit N]
Writes: data/raw/stj_atas/*.json (git-ignored), logs/12b_download_atas.json
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import sys
import time
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alj.manifest import record_download  # noqa: E402

CKAN = "https://dadosabertos.web.stj.jus.br/api/3/action/package_show"
DATASET = "atas-de-distribuicao"
OUT = ROOT / "data" / "raw" / "stj_atas"
LOG = ROOT / "logs"
HASHES = LOG / "raw_hashes.tsv"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=6, help="parallel downloads (the portal is slow per connection)")
    ap.add_argument("--from", dest="date_from", default="20230630", help="first ata (YYYYMMDD, inclusive)")
    ap.add_argument("--to", dest="date_to", default="20991231", help="last ata (YYYYMMDD, inclusive)")
    ap.add_argument("--limit", type=int, help="at most N files (smoke run)")
    ap.add_argument("--timeout", type=float, default=300.0)
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    LOG.mkdir(exist_ok=True)
    t0 = time.time()
    headers = {"User-Agent": "abusive-litigation-jurimetrics/0.1 (research; contact via GitHub)"}

    with httpx.Client(timeout=args.timeout, follow_redirects=True, headers=headers,
                      limits=httpx.Limits(max_connections=max(args.workers, 1) + 2)) as client:
        r = client.get(CKAN, params={"id": DATASET})
        r.raise_for_status()
        payload = r.json()
        if not payload.get("success"):
            print(f"CKAN package_show failed for {DATASET}", file=sys.stderr)
            return 2
        resources = [x for x in payload["result"]["resources"] if (x.get("format") or "").upper() == "JSON"]

        def key_of(res: dict) -> str:
            name = res.get("name") or Path(res["url"]).name
            digits = "".join(c for c in name if c.isdigit())
            return digits[:8]

        resources = sorted((x for x in resources if args.date_from <= key_of(x) <= args.date_to), key=key_of)
        if args.limit:
            resources = resources[: args.limit]
        published_bytes = sum(x.get("size") or 0 for x in resources)
        print(f"{len(resources)} atas, {round(published_bytes / 1e9, 2)} GB published", flush=True)

        def local_path(res: dict) -> Path:
            # six resources are published without the .json suffix (ata20230803…08); normalise the local name,
            # otherwise step 12 would not glob them and the days would silently go missing from the bridge
            name = res.get("name") or Path(res["url"]).name
            if not name.lower().endswith(".json"):
                name += ".json"
            return OUT / name

        pending = [x for x in resources
                   if not local_path(x).exists() or local_path(x).stat().st_size != (x.get("size") or 0)]
        print(f"{len(resources) - len(pending)} already on disk, {len(pending)} to download "
              f"with {args.workers} workers", flush=True)

        errors: list[dict] = []
        downloaded = 0
        got_bytes = 0

        def fetch(res: dict) -> int:
            local = local_path(res)
            tmp = local.with_suffix(local.suffix + ".part")
            with client.stream("GET", res["url"]) as response:
                response.raise_for_status()
                with open(tmp, "wb") as fh:
                    for chunk in response.iter_bytes(1 << 20):
                        fh.write(chunk)
            tmp.replace(local)
            record_download(local, res["url"], HASHES, root=ROOT)
            return local.stat().st_size

        if pending:
            with cf.ThreadPoolExecutor(max_workers=max(args.workers, 1)) as pool:
                futures = {pool.submit(fetch, res): res for res in pending}
                for n, future in enumerate(cf.as_completed(futures), 1):
                    res = futures[future]
                    try:
                        got_bytes += future.result()
                        downloaded += 1
                    except Exception as exc:  # report, never silently skip
                        errors.append({"file": res.get("name"), "error": str(exc)})
                        print(f"    ! {res.get('name')}: {exc}", file=sys.stderr, flush=True)
                    if n % 50 == 0 or n == len(pending):
                        elapsed = max(time.time() - t0, 1)
                        print(f"    [{n}/{len(pending)}] {round(got_bytes / 1e9, 2)} GB "
                              f"({round(got_bytes / 1e6 / elapsed, 1)} MB/s)", flush=True)

    on_disk = sorted(OUT.glob("ata*.json"))
    out = {
        "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "dataset": DATASET,
        "resources_listed": len(resources),
        "downloaded_this_run": downloaded,
        "gigabytes_downloaded": round(got_bytes / 1e9, 2),
        "files_on_disk": len(on_disk),
        "gigabytes_on_disk": round(sum(p.stat().st_size for p in on_disk) / 1e9, 2),
        "first": on_disk[0].name if on_disk else None,
        "last": on_disk[-1].name if on_disk else None,
        "errors": errors,
        "minutes": round((time.time() - t0) / 60, 1),
        "next": "uv run python scripts/12_ingest_stj_bridge.py --atas data/raw/stj_atas   # bridge fields only",
    }
    json.dump(out, open(LOG / "12b_download_atas.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "errors"}, ensure_ascii=False, indent=1))
    if errors:
        print(f"{len(errors)} file(s) failed — re-run to retry (the run is resumable)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
