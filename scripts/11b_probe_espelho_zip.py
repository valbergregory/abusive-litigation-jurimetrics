"""Probe — what is inside the initial ZIP of an espelhos dataset, and does it add coverage?

Step 11 ingests the monthly JSON resources and deliberately skips the single ZIP that each of the ten datasets
also publishes (the backlog uploaded when the dataset was created, 2022-05). This probe answers whether that ZIP
holds records the monthly series does not, so the decision is measured instead of assumed.

Downloads ONE dataset's ZIP (~20 MB), hashes it into logs/raw_hashes.tsv, reads it in memory and compares the
publication dates and the registration numbers with what is already in data/interim/espelhos.

Usage:  uv run python scripts/11b_probe_espelho_zip.py [--orgao corte-especial] [--keep]
Writes: logs/11b_probe_espelho_zip.json (counts only; the ZIP itself is deleted unless --keep).
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import sys
import zipfile
from pathlib import Path

import duckdb
import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alj.espelhos import clean, parse_publication  # noqa: E402
from alj.manifest import record_download  # noqa: E402

CKAN = "https://dadosabertos.web.stj.jus.br/api/3/action/package_show"
RAW = ROOT / "data" / "raw" / "stj_espelhos"
ESP = (ROOT / "data" / "interim" / "espelhos" / "espelhos" / "*.parquet").as_posix()
LOG = ROOT / "logs"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--orgao", default="corte-especial")
    ap.add_argument("--keep", action="store_true", help="keep the downloaded ZIP on disk")
    args = ap.parse_args()

    ua = {"User-Agent": "abusive-litigation-jurimetrics/0.1 (research; contact via GitHub)"}
    with httpx.Client(headers=ua, timeout=180, follow_redirects=True) as client:
        r = client.get(CKAN, params={"id": f"espelhos-de-acordaos-{args.orgao}"})
        r.raise_for_status()
        res = [x for x in r.json()["result"]["resources"] if (x.get("format") or "").upper() == "ZIP"]
        if not res:
            print(f"no ZIP resource for {args.orgao}", file=sys.stderr)
            return 2
        zip_res = res[0]
        target = RAW / args.orgao / (zip_res.get("name") or "backlog.zip")
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.stat().st_size != (zip_res.get("size") or 0):
            print(f"downloading {zip_res['name']} ({round((zip_res.get('size') or 0) / 1e6, 1)} MB)…", flush=True)
            with client.stream("GET", zip_res["url"]) as response:
                response.raise_for_status()
                with open(target, "wb") as fh:
                    for chunk in response.iter_bytes(1 << 20):
                        fh.write(chunk)
        record_download(target, zip_res["url"], LOG / "raw_hashes.tsv", root=ROOT)

    members, records, dates, regs = [], 0, [], set()
    with zipfile.ZipFile(target) as zf:
        members = zf.namelist()
        for name in members:
            if not name.lower().endswith(".json"):
                continue
            with zf.open(name) as fh:
                try:
                    data = json.load(io.TextIOWrapper(fh, encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
            for rec in (data if isinstance(data, list) else [data]):
                records += 1
                reg = clean(rec.get("numeroRegistro"))
                if reg:
                    regs.add(reg)
                _, published = parse_publication(rec.get("dataPublicacao"))
                if published:
                    dates.append(published)

    con = duckdb.connect()
    known = {row[0] for row in con.execute(
        f"SELECT DISTINCT numero_registro FROM read_parquet('{ESP}') WHERE orgao_slug = ?", [args.orgao]
    ).fetchall() if row[0]}
    con.close()
    new = regs - known

    out = {
        "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "orgao": args.orgao,
        "zip": {"name": target.name, "megabytes": round(target.stat().st_size / 1e6, 1), "members": len(members)},
        "records_in_zip": records,
        "distinct_registrations_in_zip": len(regs),
        "already_in_monthly_json": len(regs & known),
        "only_in_zip": len(new),
        "publication_dates": {"min": min(dates).isoformat() if dates else None,
                              "max": max(dates).isoformat() if dates else None},
        "conclusion": ("the ZIP adds coverage — step 11 should unpack it"
                       if len(new) > 0.01 * max(len(regs), 1)
                       else "the ZIP duplicates the monthly series — step 11 is right to skip it"),
    }
    LOG.mkdir(exist_ok=True)
    json.dump(out, open(LOG / "11b_probe_espelho_zip.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if not args.keep:
        target.unlink(missing_ok=True)
        out["zip_deleted_after_probe"] = True
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
