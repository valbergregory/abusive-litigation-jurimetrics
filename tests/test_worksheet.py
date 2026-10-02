"""Tests for the annotation aids (alj.worksheet) and the staged-validation helpers (alj.validation).

Synthetic rows only (tests/fixtures_gold.py); nothing here is, or suggests, a label of a real document.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fixtures_gold import SIZES, blank_rows, complete, fill, strata_log, strict_only, write_csv

from alj.validation import (
    Annotated,
    effective_weights,
    estimability,
    go_no_go,
    go_no_go_staged,
    mask_metrics,
    metrics,
    stratum_weights,
)
from alj.worksheet import (
    RECOMMENDED_ORDER,
    batch_dates,
    check_header,
    check_row,
    check_worksheet,
    parse_date,
    plan_batches,
    progress,
    read_worksheet,
    reannotation_gaps,
    reannotation_schedule,
)


def _row(**kw) -> dict:
    r = blank_rows()[0]
    r["stratum"] = "strict"
    return fill(r, **kw) if "status" in kw else r


def _cols(issues, severity=None):
    return {i.column for i in issues if severity is None or i.severity == severity}


# ------------------------------------------------------------------------------------------------- reading


@pytest.mark.parametrize("delimiter", [",", ";"])
def test_read_worksheet_accepts_comma_and_semicolon(tmp_path, delimiter):
    rows = strict_only(blank_rows())
    path = write_csv(tmp_path / "g.csv", rows, delimiter=delimiter)
    header, back = read_worksheet(path)
    assert "label1_status" in header and len(back) == len(rows)
    assert back[0]["doc_id"] == rows[0]["doc_id"]
    assert sum(bool(r["label1_status"]) for r in back) == SIZES["strict"]


def test_read_worksheet_reads_xlsx_with_excel_types(tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["doc_id", "stratum", "label1_status", "minutes_spent", "annotation_date"])
    ws.append(["T-1", "strict", "S3", 3.0, dt.datetime(2026, 10, 1)])
    ws.append([None, None, None, None, None])  # Excel leaves empty rows at the end
    wb.save(tmp_path / "g.xlsx")
    header, rows = read_worksheet(tmp_path / "g.xlsx")
    assert header == ["doc_id", "stratum", "label1_status", "minutes_spent", "annotation_date"]
    assert rows == [{"doc_id": "T-1", "stratum": "strict", "label1_status": "S3", "minutes_spent": "3",
                     "annotation_date": "2026-10-01"}]


def test_parse_date_formats():
    assert parse_date("2026-10-02") == dt.date(2026, 10, 2)
    assert parse_date("02/10/2026") == dt.date(2026, 10, 2)
    assert parse_date("2026-10-02 14:30:00") == dt.date(2026, 10, 2)
    assert parse_date("ontem") is None and parse_date("") is None


# ------------------------------------------------------------------------------------------------ checking


def test_clean_row_has_no_issue():
    assert check_row(_row(status="S3", grounds="A11;T1198", measure="M2")) == []
    assert check_row(_row()) == []  # blank = not annotated, never an error


def test_invalid_codes_are_errors():
    r = _row(status="S3", grounds="A21;A11;X", measure="M9", domain="D7")
    errs = _cols(check_row(r), "erro")
    assert {"label2_grounds", "label3_measure", "label4_domain"} <= errs
    assert _cols(check_row(_row(status="S9")), "erro") == {"label1_status"}
    bad_min = _row(status="S1")
    bad_min["minutes_spent"] = "três"
    assert "minutes_spent" in _cols(check_row(bad_min), "erro")
    bad_date = _row(status="S1")
    bad_date["annotation_date"] = "semana passada"
    assert "annotation_date" in _cols(check_row(bad_date), "erro")


def test_protocol_combinations_are_warnings_not_errors():
    cases = {
        "S3 with M0": (_row(status="S3", grounds="A11", measure="M0"), "label3_measure"),
        "S2 without grounds": (_row(status="S2", grounds="", measure="M1"), "label2_grounds"),
        "S0 with grounds": (_row(status="S0", grounds="A4"), "label2_grounds"),
        "MAFE with Annex A": (_row(status="S3", grounds="MAFE;A11", measure="M3"), "label2_grounds"),
        "NA with grounds": (_row(status="NA", grounds="A11"), "label1_status"),
    }
    for name, (row, col) in cases.items():
        issues = check_row(row)
        assert not _cols(issues, "erro"), name
        assert col in _cols(issues, "aviso"), name


def test_partial_row_and_missing_bookkeeping_are_flagged():
    r = _row()
    r["label2_grounds"] = "A11"  # grounds typed, status still blank
    assert "label1_status" in _cols(check_row(r), "aviso")
    r = _row(status="S1")
    r.update(justification="", minutes_spent="", annotator="", annotation_date="", protocol_version="")
    assert {"justification", "minutes_spent", "annotator", "annotation_date", "protocol_version"} <= _cols(
        check_row(r), "aviso")


def test_missing_columns_and_duplicates(tmp_path):
    rows = blank_rows()
    header = list(rows[0])
    assert check_header(header) == []
    assert {i.column for i in check_header([c for c in header if c != "label3_measure"])} == {"label3_measure"}
    rows[1]["doc_id"] = rows[0]["doc_id"]
    issues = check_worksheet(header, rows)
    assert any(i.column == "doc_id" and i.severity == "erro" for i in issues)


# ------------------------------------------------------------------------------------------------ progress


def test_progress_follows_the_recommended_order_and_estimates_hours():
    p = progress(strict_only(blank_rows()))
    assert [s.stratum for s in p.strata] == list(RECOMMENDED_ORDER)
    d = p.as_dict()
    total = sum(SIZES.values())
    assert d["total"] == total and d["done"] == SIZES["strict"]
    assert d["by_stratum"][0] == {"stratum": "strict", "total": 20, "done": 20, "remaining": 0, "pct": 100.0, "na": 0}
    remaining = total - SIZES["strict"]
    assert d["hours_left_at_2_to_4_min"] == [round(remaining * 2 / 60, 1), round(remaining * 4 / 60, 1)]
    assert d["own_pace_min_per_doc"] == 3.0


# ------------------------------------------------------------------------------------------------- batches


def test_plan_batches_order_size_and_stability():
    rows = blank_rows()
    plan = plan_batches(rows, per_day=7, seed=1)
    assert [p["ordem"] for p in plan] == list(range(1, len(rows) + 1))
    assert max(p["lote"] for p in plan) == -(-len(rows) // 7)
    strata_seq = [p["stratum"] for p in plan]
    assert strata_seq == sorted(strata_seq, key=RECOMMENDED_ORDER.index)  # strict first, controls last
    assert plan == plan_batches(list(reversed(rows)), per_day=7, seed=1)  # independent of the input order
    assert plan != plan_batches(rows, per_day=7, seed=2)
    within = [p["doc_id"] for p in plan if p["stratum"] == "strict"]
    assert within != sorted(within)  # pseudo-random inside the stratum, not by date
    with pytest.raises(ValueError):
        plan_batches(rows, per_day=0)


def test_plan_ignores_labels():
    a = plan_batches(blank_rows(), seed=3)
    b = plan_batches(complete(blank_rows()), seed=3)
    assert [(p["lote"], p["doc_id"]) for p in a] == [(p["lote"], p["doc_id"]) for p in b]
    assert all(p["feito"] for p in b) and not any(p["feito"] for p in a)


def test_batch_dates_skip_weekends():
    friday = dt.date(2026, 10, 2)
    assert batch_dates(3, friday) == [friday, dt.date(2026, 10, 5), dt.date(2026, 10, 6)]
    assert batch_dates(2, friday, weekdays_only=False) == [friday, dt.date(2026, 10, 3)]


# --------------------------------------------------------------------------------------------- blind round


def test_reannotation_schedule_waits_for_all_docs_and_two_weeks():
    rows = [r for r in strict_only(blank_rows()) if r["stratum"] == "strict"]
    rows[0]["annotation_date"] = "2026-10-01"
    rows[1]["annotation_date"] = "2026-10-03"
    ids = [rows[0]["doc_id"], rows[1]["doc_id"]]
    s = reannotation_schedule(rows, ids)
    assert s["pending_in_first_round"] == 0 and s["earliest_blind_start"] == "2026-10-17"
    pending = reannotation_schedule(rows, [*ids, "Tcontrol_unflagged-000"])
    assert pending["pending_in_first_round"] == 1 and pending["earliest_blind_start"] is None


def test_reannotation_gaps_counts_pairs_done_too_soon():
    first = [r for r in strict_only(blank_rows()) if r["stratum"] == "strict"][:2]
    second = [fill(dict(first[0]), "S3", date="2026-10-20"), fill(dict(first[1]), "S1", date="2026-10-05")]
    assert reannotation_gaps(first, second) == {"pairs": 2, "too_soon": 1, "undated": 0, "min_days": 14}


# ------------------------------------------------------------------------------------------ staged validation


def _annotated(rows: list[dict]) -> list[Annotated]:
    flagged = {"strict", "strict_negated", "conduct_multi", "conduct_sanction"}
    return [Annotated(r["doc_id"], r["stratum"], r["label1_status"], r["stratum"] in flagged)
            for r in rows if r["label1_status"]]


def test_strict_only_stage_gives_precision_but_not_recall():
    rows = _annotated(strict_only(blank_rows()))
    est = estimability(rows, strata_log()["strata"])
    assert est["precision"] and est["precision_scope"] == ["strict"]
    assert not est["precision_covers_all_candidates"]
    assert not est["recall"] and not est["f1"] and not est["annotation_complete"]
    assert any("control_unflagged" in why for why in est["not_estimable_because"])
    raw = metrics(rows)
    assert raw["recall"] == 1.0  # the arithmetic alone would claim perfect recall …
    masked = mask_metrics(raw, est)
    assert masked["precision"] == 0.75 and masked["recall"] is None and masked["f1"] is None  # … so it is masked


def test_complete_stage_estimates_everything():
    rows = _annotated(complete(blank_rows()))
    est = estimability(rows, strata_log()["strata"])
    assert est["precision"] and est["recall"] and est["annotation_complete"]
    assert est["precision_covers_all_candidates"] and not est["not_estimable_because"]


def test_effective_weights_use_the_labelled_rows():
    log = strata_log()["strata"]
    partial = _annotated(strict_only(blank_rows()))
    w = effective_weights(log, partial)
    assert w["strict"] == 200 / 20 and w["control_unflagged"] == 0.0
    full = _annotated(complete(blank_rows()))
    assert effective_weights(log, full) == stratum_weights(log)  # identical once every stratum is done


def test_go_no_go_is_provisional_while_incomplete():
    table = go_no_go(reviewed=600, confirmed=450, precision=0.7, kappa=None)
    staged = {r["criterion"]: r for r in go_no_go_staged(table, complete=False)}
    assert staged["candidates reviewed"]["verdict"] == "in progress"  # not a premature no-go
    assert staged["confirmed with reasons (S3 or S2)"]["verdict"] == "go"  # already past the threshold
    assert all(r["provisional"] for r in staged.values())
    final = go_no_go_staged(table, complete=True)
    assert not any(r["provisional"] for r in final) and final[0]["verdict"] == "reformulate"
