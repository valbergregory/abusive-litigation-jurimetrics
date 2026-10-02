"""Annotation aid — check the worksheet being filled and show the progress (no label is produced or changed).

Reads the researcher's worksheet (``gold_v1.xlsx`` while he works in Excel, or the saved ``gold_v1.csv``; `,` or
`;` separator) and reports, without touching the file:

* **errors** — a code that is not in docs/annotation_protocol.md §§2–5, a missing column, a duplicated doc_id, a
  date or a minutes value that cannot be read: step 22 would skip or misread these rows;
* **warnings** — combinations the protocol makes unlikely (S3 with M0, S3/S2 without grounds, S0 with grounds,
  MAFE together with Annex A items, NA with grounds, empty justification…): to look at again, never corrected;
* **progress** per stratum in the order of docs/COMO_ANOTAR.md §4, with the hours left at 2–4 min/document and
  at the researcher's own pace (mean of ``minutes_spent``);
* the **next batch** of the plan written by ``scripts/28_plan_batches.py`` (if it exists);
* the **blind round** (§6.3): from which date ``gold_v1_reannotation.csv`` may be annotated (≥ 14 days after the
  last first-round date of the same documents), and, when it is being filled, pairs done too soon.

Writes:
  data/annotations/_verificacao.csv     one line per issue (doc_id, column, message) — git-ignored folder
  logs/27_check_worksheet.json          counts only (no doc_id, no label, no snippet)

Exit code 1 when there are errors, 0 otherwise.

Usage:
  uv run python scripts/27_check_worksheet.py                        # gold_v1.xlsx, else gold_v1.csv
  uv run python scripts/27_check_worksheet.py --gold data/annotations/gold_v1.csv --show 50
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
    MINUTES_PER_DOC,
    check_worksheet,
    is_labelled,
    progress,
    read_worksheet,
    reannotation_gaps,
    reannotation_schedule,
)

ANN = ROOT / "data" / "annotations"
LOG = ROOT / "logs"


def default_gold(ann: Path) -> Path:
    for name in ("gold_v1.xlsx", "gold_v1.csv", "gold_v1_sample.csv"):
        if (ann / name).exists():
            return ann / name
    return ann / "gold_v1.csv"


def next_batch(plan_path: Path, done_ids: set[str]) -> dict | None:
    if not plan_path.exists():
        return None
    _, plan = read_worksheet(plan_path)
    pending = [p for p in plan if p.get("doc_id") not in done_ids]
    if not pending:
        return {"lote": None, "pending": 0}
    lote = pending[0].get("lote")
    in_lote = [p for p in plan if p.get("lote") == lote]
    todo = [p for p in in_lote if p.get("doc_id") not in done_ids]
    return {"lote": lote, "data_sugerida": in_lote[0].get("data_sugerida"), "size": len(in_lote),
            "todo": [p["doc_id"] for p in todo], "stratum": sorted({p.get("stratum", "") for p in todo}),
            "batches_left": len({p.get("lote") for p in pending})}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gold", help="worksheet to check (default: gold_v1.xlsx, else gold_v1.csv, in data/annotations)")
    ap.add_argument("--ann-dir", default=str(ANN))
    ap.add_argument("--reannotation", help="blind-round file (default: <ann-dir>/gold_v1_reannotation.csv)")
    ap.add_argument("--reannotation-done", help="filled blind round (default: <ann-dir>/gold_v1_reannotation_done.csv)")
    ap.add_argument("--plan", help="batch plan of step 28 (default: <ann-dir>/plano_lotes.csv)")
    ap.add_argument("--log-dir", default=str(LOG))
    ap.add_argument("--show", type=int, default=25, help="how many issues to print per severity")
    args = ap.parse_args(argv)

    ann = Path(args.ann_dir)
    gold = Path(args.gold) if args.gold else default_gold(ann)
    if not gold.exists():
        print(f"worksheet not found: {gold}", file=sys.stderr)
        return 2
    header, rows = read_worksheet(gold)
    issues = check_worksheet(header, rows)
    errors = [i for i in issues if i.severity == "erro"]
    warnings = [i for i in issues if i.severity == "aviso"]
    prog = progress(rows)
    p = prog.as_dict()

    print(f"planilha: {gold.name} — {len(rows)} linhas")
    print(f"\nPROGRESSO: {p['done']} de {p['total']} anotados ({p['pct_done']}%), faltam {p['remaining']}")
    print(f"  {'estrato (ordem do COMO_ANOTAR)':<32}{'feitos':>8}{'total':>8}{'faltam':>8}{'%':>8}")
    for s in p["by_stratum"]:
        print(f"  {s['stratum']:<32}{s['done']:>8}{s['total']:>8}{s['remaining']:>8}{s['pct']:>8}")
    lo, hi = MINUTES_PER_DOC
    lo_h, hi_h = p["hours_left_at_2_to_4_min"]
    print(f"  tempo restante: {lo_h}–{hi_h} h a {lo}–{hi} min/doc"
          f" (≈ {round(p['remaining'] / 25)} dias de 25 documentos)")
    if p["own_pace_min_per_doc"]:
        print(f"  no seu ritmo medido ({p['own_pace_min_per_doc']} min/doc): {p['hours_left_at_own_pace']} h")

    plan_path = Path(args.plan) if args.plan else ann / "plano_lotes.csv"
    done_ids = {(r.get("doc_id") or "").strip() for r in rows if is_labelled(r)}
    nb = next_batch(plan_path, done_ids)
    if nb and nb["lote"]:
        print(f"\nPRÓXIMO LOTE: {nb['lote']} (data sugerida {nb['data_sugerida']}; faltam {len(nb['todo'])} "
              f"de {nb['size']}; {nb['batches_left']} lote(s) restantes) — estrato {', '.join(nb['stratum'])}")
        for d in nb["todo"]:
            print(f"  {d}")
    elif nb:
        print("\nPLANO DE LOTES: todos os documentos do plano estão anotados")

    re_path = Path(args.reannotation) if args.reannotation else ann / "gold_v1_reannotation.csv"
    sched = gaps = None
    if re_path.exists():
        _, re_rows = read_worksheet(re_path)
        sched = reannotation_schedule(rows, [r.get("doc_id", "") for r in re_rows])
        print(f"\nRODADA CEGA (§6.3, κ): {sched['reannotation_docs']} documentos; "
              f"{sched['done_in_first_round']} já anotados na 1ª rodada, {sched['pending_in_first_round']} pendentes")
        if sched["earliest_blind_start"]:
            ready = dt.date.fromisoformat(sched["earliest_blind_start"]) <= dt.date.today()
            print(f"  pode começar a partir de {sched['earliest_blind_start']} "
                  f"({'JÁ PODE' if ready else 'ainda não'}) — ≥ {sched['min_days']} dias após {sched['last_first_round_date']}")
        else:
            why = ("faltam documentos na 1ª rodada" if sched["pending_in_first_round"]
                   else "há anotações sem annotation_date")
            print(f"  ainda sem data: {why}. Não abra {re_path.name} antes disso (cegueira).")
        done_path = Path(args.reannotation_done) if args.reannotation_done else ann / "gold_v1_reannotation_done.csv"
        if done_path.exists():
            _, second = read_worksheet(done_path)
            gaps = reannotation_gaps(rows, second)
            print(f"  rodada cega preenchida: {gaps['pairs']} pares; {gaps['too_soon']} feitos cedo demais; "
                  f"{gaps['undated']} sem data")

    print(f"\nERROS: {len(errors)}  (linhas que o passo 22 ignoraria ou leria errado)")
    for i in errors[: args.show]:
        print(f"  [{i.doc_id}] {i.column}: {i.message}")
    if len(errors) > args.show:
        print(f"  … mais {len(errors) - args.show} (lista completa em _verificacao.csv)")
    by_kind = Counter((i.column, i.message.split(" (")[0]) for i in warnings)
    print(f"\nAVISOS: {len(warnings)}  (para rever; nada é corrigido automaticamente)")
    for (col, msg), n in by_kind.most_common(args.show):
        print(f"  {n:>4} × {col}: {msg}")

    if issues and ann.exists():
        out_csv = ann / "_verificacao.csv"
        with open(out_csv, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["gravidade", "doc_id", "coluna", "mensagem"])
            w.writerows([i.severity, i.doc_id, i.column, i.message] for i in issues)
        print(f"\nlista completa: {out_csv}")

    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "worksheet": gold.name,
        "rows": len(rows),
        "errors": len(errors),
        "warnings": len(warnings),
        "issues_by_column": dict(Counter(f"{i.severity}:{i.column}" for i in issues).most_common()),
        "progress": p,
        "reannotation": sched,
        "reannotation_timing": gaps,
        "note": "counts only; the per-row list stays in data/annotations/_verificacao.csv (git-ignored)",
    }
    json.dump(summary, open(log_dir / "27_check_worksheet.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
