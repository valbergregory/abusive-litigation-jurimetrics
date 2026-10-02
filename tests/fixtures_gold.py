"""Synthetic gold-set fixtures for the tests of the annotation tools and of the post-annotation pipeline.

Everything here is invented for the tests: doc_ids are ``T<stratum><n>``, the "labels" are arithmetic patterns
chosen to give known metrics, and no row corresponds to a real document or to a judgement of the researcher.
"""

from __future__ import annotations

import csv
from pathlib import Path

from alj.annotation import worksheet_columns

#: a small sample with the six strata of step 21, in the worksheet's own alphabetical-then-date order
SIZES = {"strict": 20, "strict_negated": 6, "conduct_multi": 10, "conduct_sanction": 8,
         "control_flagged": 5, "control_unflagged": 12}
AVAILABLE = {"strict": 200, "strict_negated": 6, "conduct_multi": 400, "conduct_sanction": 800,
             "control_flagged": 500, "control_unflagged": 100_000}


def blank_rows() -> list[dict]:
    rows = []
    for stratum in sorted(SIZES):
        for i in range(SIZES[stratum]):
            row = dict.fromkeys(worksheet_columns(), "")
            row.update(doc_id=f"T{stratum}-{i:03d}", key="20250101", seq_documento=str(i), stratum=stratum,
                       data_publicacao=f"2025-01-{1 + i % 28:02d}",
                       patterns="litigancia_predatoria" if stratum.startswith("strict") else
                       ("procuracao_irregular;peticoes_padronizadas" if stratum.startswith("conduct") else ""))
            rows.append(row)
    return rows


def fill(row: dict, status: str, *, grounds: str = "", measure: str = "M0", domain: str = "D1",
         date: str = "2026-10-01") -> dict:
    row.update(label1_status=status, label2_grounds=grounds, label3_measure=measure, label4_domain=domain,
               justification="par. 7 (synthetic)", minutes_spent="3", annotator="TT",
               annotation_date=date, protocol_version="v0.1")
    return row


def strict_only(rows: list[dict]) -> list[dict]:
    """Only the `strict` stratum labelled: 15 S3, 5 S1 → precision of the stratum 0.75; recall not estimable."""
    out = []
    for r in rows:
        r = dict(r)
        if r["stratum"] == "strict":
            i = int(r["doc_id"][-3:])
            fill(r, "S3", grounds="A11;A12", measure="M2") if i < 15 else fill(r, "S1")
        out.append(r)
    return out


def complete(rows: list[dict]) -> list[dict]:
    """Every stratum labelled, with known counts (see tests/test_pipeline_after_annotation.py)."""
    out = []
    for r in strict_only(rows):
        r = dict(r)
        i = int(r["doc_id"][-3:])
        s = r["stratum"]
        if s == "strict_negated":
            fill(r, "S1")
        elif s == "conduct_multi":
            fill(r, "S2", grounds="A7", measure="M1") if i < 5 else fill(r, "S0")
        elif s == "conduct_sanction":
            fill(r, "S0") if i else fill(r, "NA", domain="")
        elif s == "control_flagged":
            fill(r, "S0")
        elif s == "control_unflagged":
            fill(r, "S3", grounds="A11", measure="M2") if i == 0 else fill(r, "S0")
        out.append(r)
    return out


def strata_log() -> dict:
    return {"seed": 20260922, "strata": [
        {"stratum": s, "available": AVAILABLE[s], "sampled": n, "requested": n} for s, n in SIZES.items()]}


def write_csv(path: Path, rows: list[dict], delimiter: str = ",", bom: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig" if bom else "utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter=delimiter)
        w.writeheader()
        w.writerows(rows)
    return path
