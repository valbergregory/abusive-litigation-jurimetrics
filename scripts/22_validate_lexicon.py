"""Phase 1, step 22 — validate the lexicon against the researcher's gold set and evaluate the go/no-go table.

Labels are the protocol's own codes (docs/annotation_protocol.md §2: S3/S2/S1/S0/NA). Its §2 requires reporting
the positive class **with and without S2**, so every estimate is produced twice; §§3–4 (grounds A1…A20/T1198/MAFE
and measures M0…M5) are summarised too. Estimates are also weighted by the inverse sampling fraction of each
stratum, because the gold set is a stratified sample (step 21), and NA rows are excluded and counted apart.

Reads (nothing is invented: every missing input is reported and the script stops):
  data/annotations/gold_v1.csv                    the filled worksheet of step 21
  data/annotations/gold_v1_reannotation_done.csv  optional blind round, for Cohen's κ
  logs/21_export_annotation_sample.json           stratum sizes, for the inverse-sampling weights
  data/interim/candidates/docs/*.parquet          what the lexicon said about each document

Writes:
  logs/22_lexicon_validation.json

Usage:  uv run python scripts/22_validate_lexicon.py [--gold FILE] [--self-test]
`--self-test` runs the arithmetic on a small synthetic gold set (no corpus needed), so the pipeline can be
checked before any annotation exists.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

import duckdb

if hasattr(sys.stdout, "reconfigure"):  # the Windows console is cp1252; logs are always UTF-8
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alj.validation import (  # noqa: E402
    Annotated,
    cohen_kappa,
    go_no_go,
    grounds_frequency,
    metrics,
    normalise_grounds,
    normalise_measure,
    normalise_status,
    per_pattern_precision,
    stratum_weights,
)

ANN = ROOT / "data" / "annotations"
CAND = (ROOT / "data" / "interim" / "candidates" / "docs" / "*.parquet").as_posix()
LOG = ROOT / "logs"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gold", default=str(ANN / "gold_v1.csv"))
    ap.add_argument("--reannotation", default=str(ANN / "gold_v1_reannotation_done.csv"))
    ap.add_argument("--sample-log", default=str(LOG / "21_export_annotation_sample.json"))
    ap.add_argument("--self-test", action="store_true", help="run the metrics on a synthetic gold set and exit")
    return ap.parse_args(argv)


def read_gold(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def to_annotated(rows: list[dict], flagged_ids: set[str] | None = None) -> tuple[list[Annotated], dict]:
    """Rows with an empty or unreadable label are skipped and counted, never guessed."""
    out: list[Annotated] = []
    skipped = {"blank": 0, "unknown_code": 0}
    for r in rows:
        raw = r.get("label1_status")
        status = normalise_status(raw)
        if status is None:
            skipped["blank" if not (raw or "").strip() else "unknown_code"] += 1
            continue
        doc_id = r["doc_id"]
        patterns = tuple(p for p in (r.get("patterns") or "").split(";") if p)
        flagged = bool(patterns) if flagged_ids is None else doc_id in flagged_ids
        out.append(
            Annotated(
                doc_id=doc_id,
                stratum=r.get("stratum", "unknown"),
                status=status,
                flagged=flagged,
                patterns=patterns,
                grounds=normalise_grounds(r.get("label2_grounds")),
                measure=normalise_measure(r.get("label3_measure")),
            )
        )
    return out, skipped


def estimate(rows: list[Annotated], weights: dict[str, float]) -> dict:
    """Raw and weighted metrics, each with and without S2 (protocol §2)."""
    out: dict[str, dict] = {}
    for include_s2 in (True, False):
        key = "s3_s2" if include_s2 else "s3_only"
        out[key] = {
            "raw": metrics(rows, include_s2=include_s2),
            "weighted": metrics(rows, weights, include_s2=include_s2) if weights else None,
            "confirmed": sum(r.signalled(include_s2) for r in rows if r.usable),
        }
    return out


def self_test() -> dict:
    rows = [
        Annotated("a", "strict", "S3", True, ("litigancia_predatoria",), ("A11", "A12"), "M2"),
        Annotated("b", "strict", "S2", True, ("litigancia_predatoria", "procuracao_irregular"), ("A11",), "M1"),
        Annotated("c", "strict", "S1", True, ("litigancia_predatoria",), (), "M0"),
        Annotated("d", "conduct_multi", "S0", True, ("gratuidade_sem_comprovacao", "peticoes_padronizadas")),
        Annotated("e", "control_unflagged", "S3", False, (), ("A7",), "M2"),
        Annotated("f", "control_unflagged", "S0", False, ()),
        Annotated("g", "strict", "NA", True, ("litigancia_predatoria",)),
    ]
    weights = stratum_weights([
        {"stratum": "strict", "available": 3000, "sampled": 4},
        {"stratum": "conduct_multi", "available": 40000, "sampled": 1},
        {"stratum": "control_unflagged", "available": 2_000_000, "sampled": 2},
    ])
    est = estimate(rows, weights)
    return {
        "rows": len(rows),
        "estimates": est,
        "per_pattern": per_pattern_precision(rows, min_annotated=1),
        "grounds": grounds_frequency(rows, min_count=1),
        "kappa_example": cohen_kappa(["S0", "S1", "S3", "S0"], ["S0", "S0", "S3", "S0"]),
        "go_no_go": go_no_go(reviewed=sum(r.usable for r in rows), confirmed=est["s3_s2"]["confirmed"],
                             precision=est["s3_s2"]["raw"]["precision"], kappa=0.81),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    LOG.mkdir(exist_ok=True)
    if args.self_test:
        out = {"run_at": dt.datetime.now().isoformat(timespec="seconds"), "mode": "self-test", **self_test()}
        print(json.dumps(out, ensure_ascii=False, indent=1))
        json.dump(out, open(LOG / "22_lexicon_validation_selftest.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        return 0

    gold = Path(args.gold)
    if not gold.exists():
        print(f"gold set not found: {gold}\n"
              f"fill the worksheet written by scripts/21_export_annotation_sample.py and save it as {gold.name}.\n"
              f"To check the arithmetic meanwhile: uv run python scripts/22_validate_lexicon.py --self-test",
              file=sys.stderr)
        return 2

    con = duckdb.connect()
    flagged_ids = {r[0] for r in con.execute(
        f"SELECT key || '-' || seq_documento FROM read_parquet('{CAND}') WHERE is_candidate"
    ).fetchall()}
    con.close()

    rows = read_gold(gold)
    annotated, skipped = to_annotated(rows, flagged_ids)
    if not annotated:
        print("no usable label in the gold set yet (all rows blank)", file=sys.stderr)
        return 2

    sample_log = json.load(open(args.sample_log, encoding="utf-8")) if Path(args.sample_log).exists() else {}
    weights = stratum_weights(sample_log.get("strata", []))
    est = estimate(annotated, weights)

    kappa: float | None = None
    kappa_grounds: float | None = None
    kappa_n = 0
    re_path = Path(args.reannotation)
    if re_path.exists():
        second, _ = to_annotated(read_gold(re_path), flagged_ids)
        first_by_id = {a.doc_id: a for a in annotated}
        pairs = [(first_by_id[b.doc_id], b) for b in second if b.doc_id in first_by_id]
        kappa_n = len(pairs)
        if pairs:
            kappa = cohen_kappa([a.status for a, _ in pairs], [b.status for _, b in pairs])
            kappa_grounds = cohen_kappa([";".join(a.grounds) for a, _ in pairs],
                                        [";".join(b.grounds) for _, b in pairs])

    headline = est["s3_s2"]
    precision = (headline["weighted"] or headline["raw"])["precision"]
    out = {
        "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "gold": str(gold.relative_to(ROOT)),
        "protocol_positive_class": "S3 and S2 (headline); S3 only reported alongside, per protocol section 2",
        "rows_in_file": len(rows),
        "annotated_rows": len(annotated),
        "usable_rows": sum(a.usable for a in annotated),
        "na_rows": sum(not a.usable for a in annotated),
        "skipped_rows": skipped,
        "by_status": {s: n for s, n in Counter(a.status for a in annotated).most_common()},
        "by_stratum": {s: n for s, n in Counter(a.stratum for a in annotated).most_common()},
        "by_measure": {s: n for s, n in Counter(a.measure for a in annotated if a.measure).most_common()},
        "estimates": est,
        "per_pattern_precision": per_pattern_precision(annotated),
        "grounds_frequency": grounds_frequency(annotated),
        "kappa": {"n_pairs": kappa_n, "status": kappa, "grounds": kappa_grounds},
        "go_no_go": go_no_go(reviewed=sum(a.usable for a in annotated), confirmed=headline["confirmed"],
                             precision=precision, kappa=kappa),
    }
    json.dump(out, open(LOG / "22_lexicon_validation.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in out.items()
                      if k not in ("per_pattern_precision", "grounds_frequency")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
