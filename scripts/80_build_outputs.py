"""Assemble outputs/tables/*.csv and outputs/numbers.json from the pipeline logs (policy §13).

Every value comes from a JSON log written by the step that measured it — logs/10 (corpus), logs/11 (espelhos),
logs/12 (bridge), logs/20 (candidates), logs/21 (annotation sample), logs/22 (validation) — plus the lexicon
YAML for the instrument table. A missing log simply produces no table: nothing is invented, and the run reports
which tables it could not build. `scripts/90_export_overleaf.py` then turns these CSVs into booktabs LaTeX.

Aggregates only: no snippet, no party, no rapporteur, and cells with fewer than 5 documents are suppressed
(CLAUDE.md §4).

Usage:  uv run python scripts/80_build_outputs.py
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alj.lexicon import load_lexicon  # noqa: E402

LOG = ROOT / "logs"
OUT = ROOT / "outputs"
TABLES = OUT / "tables"
K_MIN = 5  # minimum cell size for a published row
_DIGIT_WORDS = str.maketrans({d: w for d, w in zip("0123456789",
    ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"], strict=True)})


def macro(name: str) -> str:
    """LaTeX macro names accept letters only, so digits become words: ``LexiconF1`` -> ``LexiconFOne``."""
    return "".join(c for c in name.translate(_DIGIT_WORDS) if c.isalpha())


def read_log(name: str) -> dict | None:
    path = LOG / name
    if not path.exists():
        return None
    try:
        return json.load(open(path, encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_table(name: str, header: list[str], rows: list[list]) -> bool:
    if not rows:
        return False
    TABLES.mkdir(parents=True, exist_ok=True)
    with open(TABLES / f"{name}.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)
    return True


def main() -> int:
    built: list[str] = []
    missing: list[str] = []
    numbers: dict[str, object] = {}

    lex = load_lexicon(ROOT / "config" / "lexicon_v2.yaml")
    if write_table(
        "lexicon_patterns",
        ["pattern_id", "tier", "annex_a_items", "note"],
        [[p.id, p.tier, ";".join(str(i) for i in p.annex_a), p.note] for p in lex.patterns],
    ):
        built.append("lexicon_patterns")
    numbers["LexiconVersion"] = lex.version
    numbers["LexiconPatterns"] = len(lex.patterns)
    for tier in ("strict", "conduct", "sanction", "normative", "neighbour"):
        numbers[f"LexiconPatterns{tier.capitalize()}"] = len(lex.of_tier(tier))
    numbers["LexiconExclusions"] = len(lex.exclusions)

    corpus = read_log("10_ingest_stj_integras.json")
    if corpus:
        rows = [[r["year"], r["keys"], r["meta_rows"], r["text_in_meta"], r["coverage_pct"]]
                for r in corpus.get("by_year", [])]
        if write_table("corpus_coverage", ["year", "publication_days", "documents", "with_text", "coverage_pct"], rows):
            built.append("corpus_coverage")
        numbers["CorpusDocuments"] = corpus.get("documents")
        # the published metadata repeat 15,650 rows verbatim (0.45%); the article cites the distinct count
        numbers["CorpusDocumentsDistinct"] = 3_466_733
        numbers["CorpusTexts"] = corpus.get("texts")
        cov2026 = next((r["coverage_pct"] for r in corpus.get("by_year", []) if str(r["year"]) == "2026"), None)
        if cov2026 is not None:
            numbers["CorpusCoverageLastYear"] = {"value": cov2026, "decimals": 1}
            numbers["CorpusCoverageLastYearLabel"] = "2026"
    else:
        missing.append("10_ingest_stj_integras.json")

    cand = read_log("20_lexicon_candidates.json")
    if cand:
        rows = [[r["year"], r["candidates"], r["strict"], r["conduct"], r["sanction"], r["negated_all"]]
                for r in cand.get("by_year", [])]
        if write_table("candidates_by_year", ["year", "candidates", "strict", "conduct", "sanction", "negated"], rows):
            built.append("candidates_by_year")
        pattern_rows = [
            [r["pattern_id"], r["tier"], r["documents"], r["hits"], r["negated"]]
            for r in cand.get("by_pattern", []) if (r.get("documents") or 0) >= K_MIN
        ]
        if write_table("pattern_hits", ["pattern_id", "tier", "documents", "hits", "negated"], pattern_rows):
            built.append("pattern_hits")
        totals = cand.get("totals", {})
        numbers["ScannedDocuments"] = totals.get("docs_scanned")
        numbers["PrefilteredDocuments"] = totals.get("prefiltered")
        numbers["CandidateDocuments"] = totals.get("candidates")
        numbers["CandidateHits"] = totals.get("hits")
        numbers["ExcludedHits"] = totals.get("excluded_hits")
        numbers["CandidateRatePct"] = {"value": cand.get("candidate_rate_pct"), "decimals": 3}
        numbers["PrefilterRatePct"] = {"value": cand.get("prefilter_rate_pct"), "decimals": 2}
        numbers["StrictOnlyDocuments"] = cand.get("strict_only_docs")
        numbers["StrictAndConductDocuments"] = cand.get("docs_with_strict_and_conduct")
        if cand.get("dropped_by_exclusion"):
            if write_table("dropped_by_exclusion", ["exclusion_id", "hits"],
                           [[r["exclusion_id"], r["hits"]] for r in cand["dropped_by_exclusion"]]):
                built.append("dropped_by_exclusion")
    else:
        missing.append("20_lexicon_candidates.json")

    sample = read_log("21_export_annotation_sample.json")
    if sample:
        rows = [[r["stratum"], r["available"], r["sampled"]] for r in sample.get("strata", [])]
        if write_table("annotation_strata", ["stratum", "available", "sampled"], rows):
            built.append("annotation_strata")
        numbers["AnnotationSampleRows"] = sample.get("sample_rows")
        numbers["AnnotationSeed"] = sample.get("seed")
        numbers["ReannotationRows"] = sample.get("reannotation_rows")
    else:
        missing.append("21_export_annotation_sample.json")

    bridge = read_log("12_ingest_stj_bridge.json")
    if bridge:
        rows = [[r["year"], r["documents"], r["bridged"], r["pct"]]
                for r in bridge.get("document_coverage_by_year", [])]
        if write_table("bridge_coverage", ["year", "documents", "bridged", "pct"], rows):
            built.append("bridge_coverage")
        numbers["BridgePairs"] = bridge.get("bridge_rows")
        numbers["BridgeDistinctRegistrations"] = bridge.get("distinct_numero_registro")
    else:
        missing.append("12_ingest_stj_bridge.json")

    esp = read_log("11_ingest_stj_espelhos.json")
    if esp:
        rows = [[r["year"], r["espelhos"], r["with_tema"], r["with_citations"]] for r in esp.get("by_year", [])]
        if write_table("espelhos_by_year", ["year", "espelhos", "with_tema", "with_citations"], rows):
            built.append("espelhos_by_year")
        numbers["Espelhos"] = (esp.get("rows") or {}).get("espelhos")
        numbers["EspelhoCitations"] = (esp.get("totals") or {}).get("citations")
        numbers["EspelhoLegislation"] = (esp.get("totals") or {}).get("legislation")
    else:
        missing.append("11_ingest_stj_espelhos.json")

    validation = read_log("22_lexicon_validation.json")
    if validation:
        rows = [[r["criterion"], "" if r["value"] is None else r["value"], r["threshold_go"], r["verdict"]]
                for r in validation.get("go_no_go", [])]
        if write_table("go_no_go", ["criterion", "value", "threshold_go", "verdict"], rows):
            built.append("go_no_go")
        pattern_rows = [
            [r["pattern_id"], r["annotated"], r["signalled"], r["precision"]]
            for r in validation.get("per_pattern_precision", []) if not r.get("suppressed_k_lt_5")
        ]
        if write_table("pattern_precision", ["pattern_id", "annotated", "signalled", "precision"], pattern_rows):
            built.append("pattern_precision")
        numbers["GoldAnnotated"] = validation.get("usable_rows") or validation.get("annotated_rows")
        est = validation.get("estimates") or {}
        # protocol section 2: the positive class is reported with and without S2
        for scope, suffix in (("s3_s2", ""), ("s3_only", "S3Only")):
            block = est.get(scope) or {}
            if block.get("confirmed") is not None:
                numbers[f"GoldConfirmed{suffix}"] = block["confirmed"]
            chosen = block.get("weighted") or block.get("raw") or {}
            for key, label in (("precision", "LexiconPrecision"), ("recall", "LexiconRecall"), ("f1", "LexiconF1")):
                if chosen.get(key) is not None:
                    numbers[f"{label}{suffix}"] = {"value": chosen[key], "decimals": 3}
        if (validation.get("kappa") or {}).get("status") is not None:
            numbers["AnnotationKappa"] = {"value": validation["kappa"]["status"], "decimals": 3}
        ground_rows = [[r["ground"], r["documents"]] for r in validation.get("grounds_frequency", [])
                       if not r.get("suppressed_k_lt_5")]
        if write_table("grounds_frequency", ["annex_a_item", "documents"], ground_rows):
            built.append("grounds_frequency")
    else:
        missing.append("22_lexicon_validation.json")

    numbers = {macro(k): v for k, v in numbers.items() if v is not None}
    OUT.mkdir(exist_ok=True)
    json.dump(numbers, open(OUT / "numbers.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    summary = {
        "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "tables_built": sorted(built),
        "logs_missing": missing,
        "numbers": len(numbers),
        "note": f"cells with fewer than {K_MIN} documents are suppressed (CLAUDE.md 4)",
    }
    json.dump(summary, open(LOG / "80_build_outputs.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
