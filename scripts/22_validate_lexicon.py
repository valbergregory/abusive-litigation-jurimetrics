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
  logs/22_lexicon_validation.json   aggregates only (counts, rates, verdicts) — no doc_id, no snippet

Staged runs (added 2026-10-02). The gold set can be validated while it is being filled — e.g. with only the 600
`strict` rows done. Blank rows are "not annotated"; the weights become ``available / labelled`` per stratum, and
the log says, in `estimable`, which metrics the strata annotated so far support: precision as soon as a candidate
stratum has labels (scoped to those strata), recall and F1 only once `control_unflagged` has labels (before
that they are reported as null, never as a fake 1.0). The go/no-go table is marked `provisional` until every
stratum is complete. Step 80 leaves partial validations out of the manuscript numbers unless asked.

Usage:  uv run python scripts/22_validate_lexicon.py [--gold FILE] [--self-test]
`--self-test` runs the arithmetic on a small synthetic gold set (no corpus needed), so the pipeline can be
checked before any annotation exists.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
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
    FLAGGED_STRATA,
    Annotated,
    cohen_kappa,
    effective_weights,
    estimability,
    go_no_go,
    go_no_go_staged,
    grounds_frequency,
    mask_metrics,
    metrics,
    normalise_grounds,
    normalise_measure,
    normalise_status,
    per_pattern_precision,
    stratum_weights,
)
from alj.worksheet import progress, read_worksheet, reannotation_gaps  # noqa: E402

ANN = ROOT / "data" / "annotations"
CAND = (ROOT / "data" / "interim" / "candidates" / "docs" / "*.parquet").as_posix()
LOG = ROOT / "logs"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gold", default=str(ANN / "gold_v1.csv"))
    ap.add_argument("--reannotation", default=str(ANN / "gold_v1_reannotation_done.csv"))
    ap.add_argument("--sample-log", default=str(LOG / "21_export_annotation_sample.json"))
    ap.add_argument("--candidates", default=CAND,
                    help="glob of the step-20 candidate Parquet; when it matches nothing, 'flagged' is read from "
                         "the stratum (identical by construction of step 21)")
    ap.add_argument("--log-dir", default=str(LOG), help="where the JSON log is written (tests use a tmp dir)")
    ap.add_argument("--self-test", action="store_true", help="run the metrics on a synthetic gold set and exit")
    return ap.parse_args(argv)


def read_gold(path: Path) -> list[dict]:
    """The filled worksheet, with ',' or ';' as separator (the pt-BR Excel saves CSV with ';')."""
    return read_worksheet(path)[1]


def flagged_from_candidates(pattern: str) -> set[str] | None:
    """doc_ids the lexicon made candidates, from step 20; None when the Parquet is not on this machine."""
    if not glob.glob(pattern):
        return None
    con = duckdb.connect()
    try:
        return {r[0] for r in con.execute(
            f"SELECT key || '-' || seq_documento FROM read_parquet('{pattern}') WHERE is_candidate"
        ).fetchall()}
    finally:
        con.close()


def to_annotated(rows: list[dict], flagged_ids: set[str] | None = None) -> tuple[list[Annotated], dict]:
    """Rows with an empty or unreadable label are skipped and counted, never guessed.

    ``flagged`` comes from the candidate set when ``flagged_ids`` is given; otherwise from the stratum (the four
    candidate strata of step 21 are, by construction, exactly the lexicon's candidates in the sample).
    """
    out: list[Annotated] = []
    skipped = {"blank": 0, "unknown_code": 0}
    for r in rows:
        raw = r.get("label1_status")
        status = normalise_status(raw)
        if status is None:
            skipped["blank" if not (raw or "").strip() else "unknown_code"] += 1
            continue
        doc_id = r["doc_id"]
        stratum = (r.get("stratum") or "unknown").strip()
        patterns = tuple(p for p in (r.get("patterns") or "").split(";") if p)
        flagged = stratum in FLAGGED_STRATA if flagged_ids is None else doc_id in flagged_ids
        out.append(
            Annotated(
                doc_id=doc_id,
                stratum=stratum,
                status=status,
                flagged=flagged,
                patterns=patterns,
                grounds=normalise_grounds(r.get("label2_grounds")),
                measure=normalise_measure(r.get("label3_measure")),
            )
        )
    return out, skipped


def estimate(rows: list[Annotated], weights: dict[str, float], est: dict | None = None) -> dict:
    """Raw and weighted metrics, each with and without S2 (protocol §2).

    With ``est`` (from :func:`alj.validation.estimability`), what the annotated strata cannot support is blanked
    — e.g. recall before any ``control_unflagged`` row is annotated, which would otherwise read 1.0.
    """
    out: dict[str, dict] = {}
    for include_s2 in (True, False):
        key = "s3_s2" if include_s2 else "s3_only"
        raw = metrics(rows, include_s2=include_s2)
        weighted = metrics(rows, weights, include_s2=include_s2) if weights else None
        if est is not None:
            raw = mask_metrics(raw, est)
            weighted = mask_metrics(weighted, est) if weighted else None
        out[key] = {
            "raw": raw,
            "weighted": weighted,
            "confirmed": sum(r.signalled(include_s2) for r in rows if r.usable),
        }
    return out


def describe_stage(est: dict, prog: dict) -> list[str]:
    """Plain-Portuguese lines for the terminal: what the strata annotated so far allow to estimate."""
    lines = [f"anotados: {prog['done']} de {prog['total']} ({prog['pct_done']}%)"]
    for s in prog["by_stratum"]:
        mark = "completo" if s["remaining"] == 0 else f"faltam {s['remaining']}"
        lines.append(f"  {s['stratum']:<18} {s['done']:>4}/{s['total']:<4} {mark}")
    if est["precision"]:
        scope = ", ".join(est["precision_scope"])
        whole = ("todo o conjunto de candidatos" if est["precision_covers_all_candidates"]
                 else f"só dos estratos anotados ({scope}), não do léxico inteiro")
        lines.append(f"precisão: ESTIMÁVEL — {whole}")
    else:
        lines.append("precisão: ainda não estimável")
    if est["recall"]:
        extra = " (control_flagged incompleto: os quase-acertos ainda não entram)" \
            if est["recall_partial_control_flagged"] else ""
        lines.append(f"revocação e F1: ESTIMÁVEIS{extra}")
    else:
        lines.append("revocação e F1: NÃO estimáveis — falta anotar control_unflagged (o denominador)")
    lines.append("precisão por padrão e frequência do Anexo A: " +
                 ("estimáveis (células com k >= 5)" if est["per_pattern_precision"] else "ainda não"))
    if not est["annotation_complete"]:
        lines.append("go/no-go: PROVISÓRIO até o fim da anotação")
    return lines


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

    flagged_ids = flagged_from_candidates(args.candidates)
    flagged_source = "candidates parquet (step 20)" if flagged_ids is not None else "stratum (step 21 design)"

    rows = read_gold(gold)
    annotated, skipped = to_annotated(rows, flagged_ids)
    prog = progress(rows).as_dict()
    if not annotated:
        print("no usable label in the gold set yet (all rows blank)", file=sys.stderr)
        return 2

    sample_log = json.load(open(args.sample_log, encoding="utf-8")) if Path(args.sample_log).exists() else {}
    strata_log = sample_log.get("strata", [])
    if not strata_log:  # without step 21's log, the worksheet itself says how many rows each stratum has
        strata_log = [{"stratum": s["stratum"], "available": None, "sampled": s["total"]} for s in prog["by_stratum"]]
    est_ok = estimability(annotated, strata_log)
    has_population = any(r.get("available") for r in strata_log)
    weights = effective_weights(strata_log, annotated) if has_population else {}
    est = estimate(annotated, weights, est_ok)

    kappa: float | None = None
    kappa_grounds: float | None = None
    kappa_n = 0
    gaps = None
    re_path = Path(args.reannotation)
    if re_path.exists():
        second_rows = read_gold(re_path)
        second, _ = to_annotated(second_rows, flagged_ids)
        first_by_id = {a.doc_id: a for a in annotated}
        pairs = [(first_by_id[b.doc_id], b) for b in second if b.doc_id in first_by_id]
        kappa_n = len(pairs)
        if pairs:
            kappa = cohen_kappa([a.status for a, _ in pairs], [b.status for _, b in pairs])
            kappa_grounds = cohen_kappa([";".join(a.grounds) for a, _ in pairs],
                                        [";".join(b.grounds) for _, b in pairs])
        gaps = reannotation_gaps(rows, second_rows)

    headline = est["s3_s2"]
    precision = (headline["weighted"] or headline["raw"])["precision"]
    complete = est_ok["annotation_complete"]
    out = {
        "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "gold": gold.name,
        "protocol_positive_class": "S3 and S2 (headline); S3 only reported alongside, per protocol section 2",
        "flagged_source": flagged_source,
        "annotation_complete": complete,
        "estimable": est_ok,
        "progress": prog,
        "rows_in_file": len(rows),
        "annotated_rows": len(annotated),
        "usable_rows": sum(a.usable for a in annotated),
        "na_rows": sum(not a.usable for a in annotated),
        "skipped_rows": skipped,
        "by_status": {s: n for s, n in Counter(a.status for a in annotated).most_common()},
        "by_stratum": {s: n for s, n in Counter(a.stratum for a in annotated).most_common()},
        "by_measure": {s: n for s, n in Counter(a.measure for a in annotated if a.measure).most_common()},
        "weights": {k: round(v, 4) for k, v in weights.items()},
        "estimates": est,
        "per_pattern_precision": per_pattern_precision(annotated),
        "grounds_frequency": grounds_frequency(annotated),
        "kappa": {"n_pairs": kappa_n, "status": kappa, "grounds": kappa_grounds, "timing": gaps},
        "go_no_go": go_no_go_staged(
            go_no_go(reviewed=sum(a.usable for a in annotated), confirmed=headline["confirmed"],
                     precision=precision, kappa=kappa),
            complete,
        ),
    }
    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(log_dir / "22_lexicon_validation.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in out.items()
                      if k not in ("per_pattern_precision", "grounds_frequency", "progress", "estimable")},
                     ensure_ascii=False, indent=1))
    print("\n" + "\n".join(describe_stage(est_ok, prog)))
    if gaps and gaps["too_soon"]:
        print(f"ATENÇÃO: {gaps['too_soon']} documento(s) da rodada cega reanotados < {gaps['min_days']} dias "
              "depois da primeira anotação (protocolo §6.3)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
