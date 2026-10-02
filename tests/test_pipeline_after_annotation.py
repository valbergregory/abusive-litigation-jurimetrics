"""End-to-end check of everything that runs after the labels exist: 27 → 28 → 22 → 80 → 81 → 90.

The scripts, ``src/alj`` and ``config/`` are copied into a temporary root (the scripts resolve every path from
their own location), the step logs they read are synthetic, and so is the gold set (tests/fixtures_gold.py).
No real data, no network; the real ``logs/`` and ``outputs/`` of the repository are never touched.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fixtures_gold import SIZES, blank_rows, complete, strata_log, strict_only, write_csv

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = ("22_validate_lexicon.py", "27_check_worksheet.py", "28_plan_batches.py", "80_build_outputs.py",
           "81_build_figures.py", "90_export_overleaf.py")


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / "scripts").mkdir()
    for name in SCRIPTS:
        shutil.copy2(REPO / "scripts" / name, tmp_path / "scripts" / name)
    shutil.copytree(REPO / "src", tmp_path / "src", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(REPO / "config", tmp_path / "config")
    logs = tmp_path / "logs"
    logs.mkdir()
    years = ["2023", "2024", "2025"]
    (logs / "20_lexicon_candidates.json").write_text(json.dumps({
        "totals": {"docs_scanned": 1000, "prefiltered": 100, "candidates": 50, "hits": 80, "excluded_hits": 2},
        "candidate_rate_pct": 5.0, "prefilter_rate_pct": 10.0,
        "by_year": [{"year": y, "candidates": 10 + i, "strict": 5 + i, "conduct": 6, "sanction": 7,
                     "negated_all": 1} for i, y in enumerate(years)],
        "by_pattern": [{"pattern_id": "litigancia_predatoria", "tier": "strict", "hits": 30, "documents": 20,
                        "negated": 1},
                       {"pattern_id": "extincao_sem_merito", "tier": "sanction", "hits": 40, "documents": 30,
                        "negated": 0}],
    }), encoding="utf-8")
    (logs / "21_export_annotation_sample.json").write_text(json.dumps(
        {**strata_log(), "sample_rows": sum(SIZES.values()), "reannotation_rows": 6}), encoding="utf-8")
    (logs / "12_ingest_stj_bridge.json").write_text(json.dumps({
        "bridge_rows": 100, "distinct_numero_registro": 90,
        "document_coverage_by_year": [{"year": y, "documents": 100, "bridged": 80, "pct": 80.0} for y in years],
        "candidate_coverage_by_year": [{"year": y, "candidates": 10, "bridged": 9, "pct": 90.0} for y in years],
    }), encoding="utf-8")
    return tmp_path


def run(root: Path, script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(root / "scripts" / script), *args], cwd=root,
                          capture_output=True, text=True, encoding="utf-8", timeout=180)


def test_partial_gold_strict_only(root: Path):
    ann = root / "data" / "annotations"
    write_csv(ann / "gold_v1.csv", strict_only(blank_rows()), delimiter=";")  # as the pt-BR Excel saves it

    check = run(root, "27_check_worksheet.py")
    assert check.returncode == 0, check.stdout + check.stderr
    assert "20 de 61 anotados" in check.stdout
    log27 = json.loads((root / "logs" / "27_check_worksheet.json").read_text(encoding="utf-8"))
    assert log27["errors"] == 0 and log27["progress"]["done"] == 20
    assert "Tstrict-000" not in json.dumps(log27)  # counts only; the per-row list stays in data/annotations

    val = run(root, "22_validate_lexicon.py")
    assert val.returncode == 0, val.stdout + val.stderr
    assert "NÃO estimáveis" in val.stdout
    log = json.loads((root / "logs" / "22_lexicon_validation.json").read_text(encoding="utf-8"))
    assert log["annotation_complete"] is False and log["flagged_source"].startswith("stratum")
    assert log["estimable"]["precision"] and not log["estimable"]["recall"]
    raw = log["estimates"]["s3_s2"]["raw"]
    assert raw["precision"] == 0.75 and raw["recall"] is None and raw["f1"] is None
    assert log["estimates"]["s3_s2"]["weighted"]["precision"] == 0.75  # one stratum: weights cancel
    assert all(r["provisional"] for r in log["go_no_go"])
    assert next(r for r in log["go_no_go"] if r["criterion"] == "candidates reviewed")["verdict"] == "in progress"

    # step 80 keeps a partial validation out of the manuscript unless asked for a preview
    out = run(root, "80_build_outputs.py")
    assert out.returncode == 0, out.stderr
    numbers = json.loads((root / "outputs" / "numbers.json").read_text(encoding="utf-8"))
    assert "LexiconPrecision" not in numbers and not (root / "outputs" / "tables" / "go_no_go.csv").exists()
    preview = run(root, "80_build_outputs.py", "--allow-partial-gold")
    assert preview.returncode == 0, preview.stderr
    numbers = json.loads((root / "outputs" / "numbers.json").read_text(encoding="utf-8"))
    assert numbers["LexiconPrecision"]["value"] == 0.75 and "LexiconRecall" not in numbers
    assert (root / "outputs" / "tables" / "go_no_go.csv").exists()
    run(root, "80_build_outputs.py")  # back to the default: the preview tables are removed again
    assert not (root / "outputs" / "tables" / "go_no_go.csv").exists()


def test_complete_gold_runs_through_to_overleaf(root: Path):
    ann = root / "data" / "annotations"
    rows = complete(blank_rows())
    write_csv(ann / "gold_v1.csv", rows)
    blind = [dict(r) for r in rows if r["stratum"] == "strict"][:6]
    write_csv(ann / "gold_v1_reannotation.csv", blind)
    for r in blind:
        r["annotation_date"] = "2026-10-20"  # ≥ 14 days after the synthetic first round of 2026-10-01
    blind[5]["label1_status"] = "S1" if blind[5]["label1_status"] != "S1" else "S3"  # one disagreement
    write_csv(ann / "gold_v1_reannotation_done.csv", blind)

    check = run(root, "27_check_worksheet.py")
    assert check.returncode == 0, check.stdout + check.stderr
    assert "2026-10-15" in check.stdout  # earliest blind start = 2026-10-01 + 14 days

    plan = run(root, "28_plan_batches.py", "--per-day", "25", "--start", "2026-10-05", "--ordered-worksheet")
    assert plan.returncode == 0, plan.stdout + plan.stderr
    assert (ann / "plano_lotes.csv").exists() and (ann / "gold_v1_sample_ordenado.csv").exists()
    again = run(root, "28_plan_batches.py")
    assert again.returncode == 2  # the plan is never overwritten silently

    val = run(root, "22_validate_lexicon.py")
    assert val.returncode == 0, val.stdout + val.stderr
    log = json.loads((root / "logs" / "22_lexicon_validation.json").read_text(encoding="utf-8"))
    assert log["annotation_complete"] is True and log["na_rows"] == 1
    raw = log["estimates"]["s3_s2"]["raw"]
    assert (raw["tp"], raw["fp"], raw["fn"], raw["tn"]) == (20, 23, 1, 16)
    assert raw["precision"] == round(20 / 43, 4) and raw["recall"] == round(20 / 21, 4)
    s3 = log["estimates"]["s3_only"]["raw"]
    assert s3["precision"] == round(15 / 43, 4) and s3["recall"] == round(15 / 16, 4)
    assert log["estimates"]["s3_s2"]["weighted"]["precision"] == round(350 / 1306, 4)
    assert log["kappa"]["n_pairs"] == 6 and log["kappa"]["status"] is not None
    assert log["kappa"]["timing"]["too_soon"] == 0
    assert not any(r["provisional"] for r in log["go_no_go"])
    assert rows[0]["doc_id"] not in json.dumps(log)  # the committed log carries aggregates only

    for script in ("80_build_outputs.py", "81_build_figures.py", "90_export_overleaf.py"):
        res = run(root, script)
        assert res.returncode == 0, f"{script}\n{res.stdout}\n{res.stderr}"
    numbers = json.loads((root / "outputs" / "numbers.json").read_text(encoding="utf-8"))
    assert numbers["GoldConfirmed"] == 21 and numbers["GoldAnnotated"] == len(rows) - 1
    assert "LexiconRecall" in numbers and "LexiconFOne" in numbers and "AnnotationKappa" in numbers
    over = root / "outputs" / "overleaf"
    tex = (over / "numbers.tex").read_text(encoding="utf-8")
    assert r"\newcommand{\LexiconPrecision}" in tex and r"\newcommand{\LexiconRecallSThreeOnly}" in tex
    for table in ("go_no_go", "annotation_strata", "candidates_by_year", "bridge_coverage", "lexicon_patterns"):
        assert (over / "tables" / f"{table}.tex").exists(), table
    assert (over / "tables" / "grounds_frequency.tex").exists()  # A11 confirmed in 16 synthetic rows (k >= 5)
    for fig in ("fig_strict_by_year", "fig_candidates_by_tier", "fig_bridge_coverage", "fig_pattern_hits"):
        assert (over / "figures" / f"{fig}.pdf").exists(), fig
