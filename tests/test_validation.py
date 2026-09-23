"""Tests for the gold-set arithmetic (alj.validation) and the annotation sampling frame (alj.annotation).

The label codes are the researcher's (docs/annotation_protocol.md §2: S3/S2/S1/S0/NA), and §2 requires the
positive class to be reported with and without S2 — both paths are tested here.
"""

from __future__ import annotations

import pytest

from alj.annotation import DEFAULT_STRATA, LABEL_COLUMNS, REANNOTATION_FRACTION, worksheet_columns
from alj.validation import (
    Annotated,
    cohen_kappa,
    confusion,
    go_no_go,
    grounds_frequency,
    metrics,
    normalise_grounds,
    normalise_measure,
    normalise_status,
    per_pattern_precision,
    precision_recall_f1,
    stratum_weights,
)


def test_normalise_status_accepts_the_protocol_codes():
    assert normalise_status("S3") == "S3"
    assert normalise_status(" s2 ") == "S2"
    assert normalise_status("3") == "S3"
    assert normalise_status("NA") == "NA" and normalise_status("n/a") == "NA"
    assert normalise_status("") is None and normalise_status(None) is None
    assert normalise_status("provavelmente") is None  # unknown values are never guessed
    assert normalise_status("S9") is None


def test_normalise_grounds_keeps_only_annex_a_codes():
    assert normalise_grounds("A11; a12 ,T1198") == ("A11", "A12", "T1198")
    assert normalise_grounds("MAFE") == ("MAFE",)
    assert normalise_grounds("A21;A0;X1") == ()  # Annex A has 20 items
    assert normalise_grounds("A7;A7") == ("A7",)
    assert normalise_grounds(None) == () and normalise_grounds("") == ()


def test_normalise_measure():
    assert normalise_measure("M2") == "M2" and normalise_measure("2") == "M2"
    assert normalise_measure("m0") == "M0"
    assert normalise_measure("M9") is None and normalise_measure("") is None


def test_positive_class_with_and_without_s2():
    s3 = Annotated("a", "strict", "S3", True)
    s2 = Annotated("b", "strict", "S2", True)
    s1 = Annotated("c", "strict", "S1", True)
    assert s3.signalled() and s3.signalled(include_s2=False)
    assert s2.signalled() and not s2.signalled(include_s2=False)
    assert not s1.signalled() and not s1.signalled(include_s2=False)


def test_na_rows_are_excluded_from_the_estimates():
    rows = [
        Annotated("a", "strict", "S3", True),
        Annotated("b", "strict", "NA", True),
    ]
    cm = confusion(rows)
    assert cm == {"tp": 1.0, "fp": 0.0, "fn": 0.0, "tn": 0.0}
    assert sum(r.usable for r in rows) == 1


def test_confusion_and_metrics_raw():
    rows = [
        Annotated("a", "strict", "S3", True),
        Annotated("b", "strict", "S0", True),
        Annotated("c", "control_unflagged", "S3", False),
        Annotated("d", "control_unflagged", "S0", False),
    ]
    cm = confusion(rows)
    assert cm == {"tp": 1.0, "fp": 1.0, "fn": 1.0, "tn": 1.0}
    m = precision_recall_f1(cm["tp"], cm["fp"], cm["fn"])
    assert m["precision"] == 0.5 and m["recall"] == 0.5 and m["f1"] == 0.5
    assert metrics(rows)["f1"] == 0.5


def test_excluding_s2_moves_a_case_from_tp_to_fp():
    rows = [Annotated("a", "strict", "S2", True), Annotated("b", "strict", "S3", True)]
    assert confusion(rows)["tp"] == 2.0
    strict = confusion(rows, include_s2=False)
    assert strict == {"tp": 1.0, "fp": 1.0, "fn": 0.0, "tn": 0.0}


def test_weights_correct_the_stratified_design():
    rows = [
        Annotated("a", "strict", "S3", True),
        Annotated("b", "control_unflagged", "S3", False),
    ]
    weights = stratum_weights([
        {"stratum": "strict", "available": 100, "sampled": 1},
        {"stratum": "control_unflagged", "available": 10_000, "sampled": 1},
    ])
    assert weights == {"strict": 100.0, "control_unflagged": 10_000.0}
    cm = confusion(rows, weights)
    assert cm["tp"] == 100.0 and cm["fn"] == 10_000.0
    # recall collapses once the rare stratum is weighted back to the population — that is the point
    assert precision_recall_f1(cm["tp"], cm["fp"], cm["fn"])["recall"] == pytest.approx(100 / 10_100, abs=1e-4)


def test_stratum_weight_is_zero_when_nothing_was_sampled():
    assert stratum_weights([{"stratum": "x", "available": 10, "sampled": 0}]) == {"x": 0.0}


def test_metrics_return_none_instead_of_dividing_by_zero():
    assert precision_recall_f1(0, 0, 0) == {"precision": None, "recall": None, "f1": None}
    assert precision_recall_f1(0, 5, 0)["precision"] == 0
    assert precision_recall_f1(0, 5, 0)["f1"] is None


def test_per_pattern_precision_suppresses_small_cells():
    rows = [Annotated(f"d{i}", "strict", "S3" if i % 2 else "S0", True, ("p1",)) for i in range(10)]
    rows.append(Annotated("x", "strict", "S3", True, ("p2",)))
    out = {r["pattern_id"]: r for r in per_pattern_precision(rows)}
    assert out["p1"]["annotated"] == 10 and out["p1"]["precision"] == 0.5
    assert out["p2"]["suppressed_k_lt_5"] is True and out["p2"]["precision"] is None


def test_grounds_frequency_suppresses_small_cells():
    rows = [Annotated(f"d{i}", "strict", "S3", True, (), ("A11",)) for i in range(6)]
    rows.append(Annotated("y", "strict", "S3", True, (), ("A4",)))
    out = {r["ground"]: r for r in grounds_frequency(rows)}
    assert out["A11"]["documents"] == 6
    assert out["A4"]["documents"] is None and out["A4"]["suppressed_k_lt_5"] is True


def test_cohen_kappa_known_values():
    assert cohen_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    assert cohen_kappa(["a", "a", "b", "b"], ["b", "b", "a", "a"]) == -1.0
    assert cohen_kappa(["a", "a", "a", "a"], ["a", "a", "a", "a"]) == 1.0
    # textbook example: 2x2 table with 20/5/10/15 → kappa = 0.4
    a = ["y"] * 25 + ["n"] * 25
    b = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
    assert cohen_kappa(a, b) == pytest.approx(0.4, abs=0.01)
    assert cohen_kappa([], []) is None
    with pytest.raises(ValueError):
        cohen_kappa(["a"], ["a", "b"])


def test_go_no_go_verdicts_follow_section_7():
    table = {r["criterion"]: r for r in go_no_go(reviewed=1200, confirmed=310, precision=0.42, kappa=0.8,
                                                 bridge_rate=0.75)}
    assert all(r["verdict"] == "go" for r in table.values())
    weak = {r["criterion"]: r for r in go_no_go(reviewed=700, confirmed=200, precision=0.2, kappa=0.65)}
    assert weak["candidates reviewed"]["verdict"] == "reformulate"
    assert weak["confirmed with reasons (S3 or S2)"]["verdict"] == "reformulate"
    assert weak["lexical trigger precision"]["verdict"] == "reformulate"
    assert weak["annotation agreement (Cohen kappa)"]["verdict"] == "reformulate"
    bad = {r["criterion"]: r for r in go_no_go(reviewed=100, confirmed=10, precision=0.05, kappa=0.1)}
    assert all(r["verdict"] == "no-go" for k, r in bad.items() if "bridge" not in k)
    assert bad["bridge to DataJud for confirmed cases distributed >= 2023-06-30"]["verdict"] == "not measured yet"


def test_worksheet_layout_matches_the_protocol_labels():
    cols = worksheet_columns()
    assert cols[-len(LABEL_COLUMNS):] == list(LABEL_COLUMNS)
    assert cols[0] == "doc_id" and "stratum" in cols
    assert LABEL_COLUMNS[:4] == ("label1_status", "label2_grounds", "label3_measure", "label4_domain")
    assert {"annotator", "annotation_date", "protocol_version"} <= set(LABEL_COLUMNS)
    assert len(set(cols)) == len(cols)


def test_strata_cover_precision_and_recall():
    names = {s.name for s in DEFAULT_STRATA}
    assert {"strict", "strict_negated", "conduct_multi", "control_unflagged"} <= names
    assert sum(s.size for s in DEFAULT_STRATA) >= 1000  # go/no-go asks for >= 1000 reviewed candidates
    assert 0 < REANNOTATION_FRACTION <= 0.2
