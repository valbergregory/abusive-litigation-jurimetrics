"""Annotation aid — split the worksheet into daily batches (~25 documents) in the recommended order.

The order is the one of docs/COMO_ANOTAR.md §4 (strict → strict_negated → conduct_multi → conduct_sanction →
control_flagged → control_unflagged). Inside each stratum the order is **pseudo-random and fixed** (SHA-256 of
seed + doc_id, the seed of step 21 by default): the worksheet itself is sorted by publication date, so stopping
halfway through a stratum in worksheet order would leave the oldest decisions annotated and the partial
validation of step 22 biased; in the plan's order any prefix is a random subsample of its stratum.

The plan depends only on doc_id and stratum — never on a label or on the machine's hints — and nothing here
suggests a code. Rows already labelled keep their place and are marked as done.

Writes (data/annotations/ is git-ignored):
  plano_lotes.csv                lote; data_sugerida; ordem; stratum; doc_id; feito    (`;`, opens in Excel pt-BR)
  gold_v1_sample_ordenado.csv    with --ordered-worksheet: the worksheet with `lote` and `ordem` first, rows
                                 in the plan's order (for starting from scratch; no column is dropped)
  logs/28_plan_batches.json      counts and dates only

The blind round (§6.3) is dated too: the documents of gold_v1_reannotation.csv may be re-annotated only ≥ 14
days after the planned date of the last of them in the first round.

Usage:
  uv run python scripts/28_plan_batches.py                         # 25/day, weekdays, starting today
  uv run python scripts/28_plan_batches.py --per-day 30 --start 2026-10-05 --all-days
  uv run python scripts/28_plan_batches.py --ordered-worksheet     # also write the reordered worksheet
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alj.worksheet import (  # noqa: E402
    REANNOTATION_MIN_DAYS,
    batch_dates,
    plan_batches,
    read_worksheet,
)

ANN = ROOT / "data" / "annotations"
LOG = ROOT / "logs"
DEFAULT_SEED = 20260922


def default_source(ann: Path) -> Path:
    for name in ("gold_v1.xlsx", "gold_v1.csv", "gold_v1_sample.csv"):
        if (ann / name).exists():
            return ann / name
    return ann / "gold_v1_sample.csv"


def seed_from_log(log_dir: Path) -> int:
    try:
        return int(json.load(open(log_dir / "21_export_annotation_sample.json", encoding="utf-8"))["seed"])
    except (OSError, KeyError, ValueError, json.JSONDecodeError):
        return DEFAULT_SEED


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--worksheet", help="default: gold_v1.xlsx, else gold_v1.csv, else gold_v1_sample.csv")
    ap.add_argument("--ann-dir", default=str(ANN))
    ap.add_argument("--per-day", type=int, default=25)
    ap.add_argument("--start", type=dt.date.fromisoformat, default=dt.date.today(), help="AAAA-MM-DD")
    ap.add_argument("--all-days", action="store_true", help="also plan Saturdays and Sundays")
    ap.add_argument("--seed", type=int, help="default: the seed of step 21 (logs/21_…json)")
    ap.add_argument("--ordered-worksheet", action="store_true")
    ap.add_argument("--force", action="store_true", help="overwrite an existing plano_lotes.csv")
    ap.add_argument("--log-dir", default=str(LOG))
    args = ap.parse_args(argv)

    ann = Path(args.ann_dir)
    log_dir = Path(args.log_dir)
    src = Path(args.worksheet) if args.worksheet else default_source(ann)
    if not src.exists():
        print(f"worksheet not found: {src}", file=sys.stderr)
        return 2
    plan_path = ann / "plano_lotes.csv"
    if plan_path.exists() and not args.force:
        print(f"{plan_path} already exists; the plan should stay stable while you work. Use --force to redo it.",
              file=sys.stderr)
        return 2

    seed = args.seed if args.seed is not None else seed_from_log(log_dir)
    header, rows = read_worksheet(src)
    plan = plan_batches(rows, per_day=args.per_day, seed=seed)
    n_batches = max((p["lote"] for p in plan), default=0)
    dates = batch_dates(n_batches, args.start, weekdays_only=not args.all_days)
    for p in plan:
        p["data_sugerida"] = dates[p["lote"] - 1].isoformat()

    ann.mkdir(parents=True, exist_ok=True)
    cols = ["lote", "data_sugerida", "ordem", "stratum", "doc_id", "feito"]
    with open(plan_path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter=";")
        w.writeheader()
        for p in plan:
            w.writerow({**p, "feito": "sim" if p["feito"] else ""})

    ordered_path = None
    if args.ordered_worksheet:
        ordered_path = ann / "gold_v1_sample_ordenado.csv"
        if ordered_path.exists() and not args.force:
            print(f"{ordered_path} already exists (use --force)", file=sys.stderr)
            return 2
        by_id = {(r.get("doc_id") or "").strip(): r for r in rows}
        with open(ordered_path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=["lote", "ordem", *header], extrasaction="ignore")
            w.writeheader()
            for p in plan:
                w.writerow({"lote": p["lote"], "ordem": p["ordem"], **by_id[p["doc_id"]]})

    blind = None
    re_path = ann / "gold_v1_reannotation.csv"
    if re_path.exists():
        _, re_rows = read_worksheet(re_path)
        date_of = {p["doc_id"]: p["data_sugerida"] for p in plan}
        planned = [date_of[r["doc_id"]] for r in re_rows if r.get("doc_id") in date_of]
        if planned:
            last = dt.date.fromisoformat(max(planned))
            blind = {"docs": len(re_rows), "last_first_round_planned": last.isoformat(),
                     "earliest_blind_start": (last + dt.timedelta(days=REANNOTATION_MIN_DAYS)).isoformat()}

    strata_span: dict[str, list[int]] = {}
    for p in plan:
        span = strata_span.setdefault(p["stratum"], [p["lote"], p["lote"]])
        span[1] = p["lote"]
    print(f"{len(plan)} documentos em {n_batches} lotes de até {args.per_day} "
          f"({'todos os dias' if args.all_days else 'dias úteis'}), de {dates[0] if dates else '-'} "
          f"a {dates[-1] if dates else '-'}; semente {seed}")
    for name, (a, b) in strata_span.items():
        print(f"  {name:<18} lotes {a:>3}–{b:<3} ({dates[a - 1]} a {dates[b - 1]})")
    done = sum(p["feito"] for p in plan)
    if done:
        print(f"  {done} documentos já anotados (marcados 'sim' na coluna feito)")
    if blind:
        print(f"rodada cega: {blind['docs']} documentos; pelo plano, a partir de {blind['earliest_blind_start']} "
              f"(≥ {REANNOTATION_MIN_DAYS} dias após {blind['last_first_round_planned']}). "
              "Confirme com scripts/27_check_worksheet.py, que usa as datas reais.")
    print(f"plano: {plan_path}" + (f"\nplanilha ordenada: {ordered_path}" if ordered_path else ""))

    log_dir.mkdir(parents=True, exist_ok=True)
    json.dump({
        "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": src.name,
        "documents": len(plan),
        "per_day": args.per_day,
        "batches": n_batches,
        "weekdays_only": not args.all_days,
        "first_date": dates[0].isoformat() if dates else None,
        "last_date": dates[-1].isoformat() if dates else None,
        "seed": seed,
        "by_stratum": {k: {"documents": n, "batches": strata_span[k]}
                       for k, n in Counter(p["stratum"] for p in plan).items()},
        "already_done": done,
        "blind_round": blind,
    }, open(log_dir / "28_plan_batches.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
