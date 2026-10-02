"""Validation of the lexicon against the researcher's gold set (policy §5.3, feasibility report §7).

The label codes are the researcher's, from ``docs/annotation_protocol.md`` §2:

======  =============================================================================================
``S3``  the STJ itself recognises indications of abusive/predatory litigation and grounds a measure on them
``S2``  the STJ upholds (or does not disturb) a lower-court finding — typically the Súmula 7 barrier
``S1``  the term appears only as a party's allegation, a rejected preliminary, or a citation of a precedent
``S0``  false positive of the lexicon ("custo de captação", "demandas repetitivas" in the IRDR sense)
``NA``  text missing or unreadable
======  =============================================================================================

The positive class is ``{S3, S2}``, and §2 requires reporting results **with and without S2** — hence the
``include_s2`` switch that every estimator carries. ``S1``/``S0`` are *unsignalled*, never "legitimate" (§7 of
the protocol, CLAUDE.md §3).

Pure functions only, so the arithmetic is unit-tested without touching the corpus. Two facts drive the design:

1. the gold set is a **stratified** sample (``alj.annotation``), so raw rates over the worksheet are biased
   towards the over-sampled strata; every estimate is also reported **weighted** by the inverse sampling fraction
   (``available / sampled`` per stratum, a Horvitz–Thompson estimator);
2. recall exists only because unflagged controls were annotated — without them its denominator is unknown and
   precision alone would overstate the instrument.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

#: protocol §2, from the strongest signal to no signal
SIGNALLING_STATUSES = ("S3", "S2", "S1", "S0", "NA")
POSITIVE_WITH_S2 = frozenset({"S3", "S2"})
POSITIVE_STRICT = frozenset({"S3"})
MEASURES = ("M0", "M1", "M2", "M3", "M4", "M5")  # §4
DOMAINS = ("D1", "D2", "D3", "D4", "D5")  # §5
_GROUND = re.compile(r"^(A(?:[1-9]|1[0-9]|20)|T1198|MAFE)$", re.I)  # §3


def normalise_status(value: str | None) -> str | None:
    """Accept ``S3``/``s3``/``3``/``NA`` and the obvious typos; anything unknown or blank → ``None``."""
    if value is None:
        return None
    v = str(value).strip().upper().replace(" ", "")
    if not v:
        return None
    if v in {"0", "1", "2", "3"}:
        v = f"S{v}"
    aliases = {"N/A": "NA", "NAO": "S0", "NÃO": "S0", "SO": "S0"}
    v = aliases.get(v, v)
    return v if v in SIGNALLING_STATUSES else None


def normalise_grounds(value: str | None) -> tuple[str, ...]:
    """``"A11; a12 ,T1198"`` → ``("A11", "A12", "T1198")``; unknown codes are dropped, never invented."""
    if not value:
        return ()
    parts = [p.strip().upper() for p in re.split(r"[;,/]", str(value)) if p.strip()]
    return tuple(dict.fromkeys(p for p in parts if _GROUND.match(p)))


def normalise_measure(value: str | None) -> str | None:
    if not value:
        return None
    v = str(value).strip().upper().replace(" ", "")
    if v in {"0", "1", "2", "3", "4", "5"}:
        v = f"M{v}"
    return v if v in MEASURES else None


@dataclass(frozen=True)
class Annotated:
    """One annotated document: the protocol label, the stratum it came from and what the lexicon said."""

    doc_id: str
    stratum: str
    status: str
    flagged: bool  # the lexicon made it a candidate
    patterns: tuple[str, ...] = ()
    grounds: tuple[str, ...] = ()
    measure: str | None = None

    def signalled(self, include_s2: bool = True) -> bool:
        return self.status in (POSITIVE_WITH_S2 if include_s2 else POSITIVE_STRICT)

    @property
    def usable(self) -> bool:
        """``NA`` rows (missing or unreadable text) are excluded from the estimates, and counted separately."""
        return self.status != "NA"


def stratum_weights(strata_log: list[dict]) -> dict[str, float]:
    """``available / sampled`` per stratum, from ``logs/21_export_annotation_sample.json``."""
    out: dict[str, float] = {}
    for row in strata_log:
        sampled = row.get("sampled") or 0
        out[row["stratum"]] = (row.get("available") or 0) / sampled if sampled else 0.0
    return out


def confusion(
    rows: list[Annotated], weights: dict[str, float] | None = None, *, include_s2: bool = True
) -> dict[str, float]:
    """Weighted (or raw, when ``weights`` is None) confusion of *flagged by the lexicon* × *signalled*."""
    tp = fp = fn = tn = 0.0
    for r in rows:
        if not r.usable:
            continue
        w = 1.0 if weights is None else weights.get(r.stratum, 1.0)
        positive = r.signalled(include_s2)
        if r.flagged and positive:
            tp += w
        elif r.flagged and not positive:
            fp += w
        elif not r.flagged and positive:
            fn += w
        else:
            tn += w
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def precision_recall_f1(tp: float, fp: float, fn: float) -> dict[str, float | None]:
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
    return {
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "f1": round(f1, 4) if f1 is not None else None,
    }


def metrics(
    rows: list[Annotated], weights: dict[str, float] | None = None, *, include_s2: bool = True
) -> dict[str, float | None]:
    cm = confusion(rows, weights, include_s2=include_s2)
    return {**cm, **precision_recall_f1(cm["tp"], cm["fp"], cm["fn"])}


def per_pattern_precision(
    rows: list[Annotated], min_annotated: int = 5, *, include_s2: bool = True
) -> list[dict]:
    """Share of signalled documents among the annotated documents each pattern fired on (k ≥ 5, CLAUDE.md §4)."""
    hit: Counter[str] = Counter()
    good: Counter[str] = Counter()
    for r in rows:
        if not r.usable:
            continue
        for p in set(r.patterns):
            hit[p] += 1
            good[p] += int(r.signalled(include_s2))
    out = []
    for p, n in hit.items():
        if n < min_annotated:
            out.append({"pattern_id": p, "annotated": n, "signalled": None, "precision": None,
                        "suppressed_k_lt_5": True})
            continue
        out.append({"pattern_id": p, "annotated": n, "signalled": good[p],
                    "precision": round(good[p] / n, 4), "suppressed_k_lt_5": False})
    return sorted(out, key=lambda d: (d["precision"] is None, -(d["precision"] or 0), -d["annotated"]))


def grounds_frequency(rows: list[Annotated], min_count: int = 5) -> list[dict]:
    """How often each Annex A item (protocol §3) was confirmed; cells below ``min_count`` are suppressed."""
    counter: Counter[str] = Counter()
    for r in rows:
        counter.update(set(r.grounds))
    out = [{"ground": g, "documents": n if n >= min_count else None,
            "suppressed_k_lt_5": n < min_count} for g, n in counter.items()]
    return sorted(out, key=lambda d: (d["documents"] is None, -(d["documents"] or 0), d["ground"]))


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    """Cohen's κ for two nominal annotations of the same items (None when undefined)."""
    if len(a) != len(b):
        raise ValueError("the two annotation rounds must cover the same items, in the same order")
    n = len(a)
    if n == 0:
        return None
    labels = sorted(set(a) | set(b))
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum((ca[lb] / n) * (cb[lb] / n) for lb in labels)
    if expected == 1:
        return 1.0 if observed == 1 else 0.0
    return round((observed - expected) / (1 - expected), 4)


def go_no_go(
    reviewed: int,
    confirmed: int,
    precision: float | None,
    kappa: float | None,
    bridge_rate: float | None = None,
) -> list[dict]:
    """The §7 table of the feasibility report, evaluated on real counts. Verdicts: go / reformulate / no-go."""

    def verdict(value, go, reformulate) -> str:
        if value is None:
            return "not measured yet"
        if value >= go:
            return "go"
        return "reformulate" if value >= reformulate else "no-go"

    return [
        {"criterion": "candidates reviewed", "value": reviewed, "threshold_go": 1000,
         "verdict": verdict(reviewed, 1000, 500)},
        {"criterion": "confirmed with reasons (S3 or S2)", "value": confirmed, "threshold_go": 300,
         "verdict": verdict(confirmed, 300, 150),
         "note": "150-300 -> design A only; < 150 -> descriptive study"},
        {"criterion": "lexical trigger precision", "value": precision, "threshold_go": 0.30,
         "verdict": verdict(precision, 0.30, 0.15)},
        {"criterion": "annotation agreement (Cohen kappa)", "value": kappa, "threshold_go": 0.75,
         "verdict": verdict(kappa, 0.75, 0.60)},
        {"criterion": "bridge to DataJud for confirmed cases distributed >= 2023-06-30", "value": bridge_rate,
         "threshold_go": 0.70, "verdict": verdict(bridge_rate, 0.70, 0.40),
         "note": "40-70% -> partial design B; < 40% -> design A"},
    ]


# ------------------------------------------------------------------------------------------ staged validation
# The gold set is annotated stratum by stratum (docs/COMO_ANOTAR.md §4), and the first validation is run on the
# `strict` stratum alone. The arithmetic above does not know that: with no unflagged control annotated, every
# signalled document is a true positive and recall comes out as a meaningless 1.0. The functions below say which
# estimates the strata annotated so far can support, and the script masks the others.

#: strata whose documents the lexicon made candidates (by construction of scripts/21_export_annotation_sample.py)
FLAGGED_STRATA = frozenset({"strict", "strict_negated", "conduct_multi", "conduct_sanction"})
#: strata of documents the lexicon did not make candidates: they hold the false negatives
UNFLAGGED_STRATA = frozenset({"control_flagged", "control_unflagged"})
RECALL_STRATUM = "control_unflagged"


def effective_weights(strata_log: list[dict], rows: list[Annotated]) -> dict[str, float]:
    """``available / labelled`` per stratum: the inverse sampling fraction of what was actually annotated.

    While a stratum is half done, ``available / sampled`` would under-weight it; dividing by the rows that carry a
    label (``NA`` included, since NA rows were drawn and read) keeps the Horvitz–Thompson weights right at every
    stage, and equals :func:`stratum_weights` once the stratum is complete.
    """
    labelled = Counter(r.stratum for r in rows)
    out: dict[str, float] = {}
    for row in strata_log:
        n = labelled.get(row["stratum"], 0)
        out[row["stratum"]] = (row.get("available") or 0) / n if n else 0.0
    return out


def estimability(rows: list[Annotated], strata_log: list[dict] | None = None) -> dict:
    """Which metrics the annotated strata support, and why the others are not estimable yet.

    * **precision** needs usable rows from at least one flagged stratum; it is the precision *of the annotated
      flagged strata* (``scope``) and becomes the precision of the whole candidate set only when every flagged
      stratum of the sample has been annotated (``complete``);
    * **recall / F1** need, besides that, usable rows of ``control_unflagged`` (the never-flagged documents of
      the corpus): without them the false negatives are unknown, not zero;
    * per-pattern precision and the Annex A frequencies only need annotated rows (k ≥ 5 still applies).
    """
    usable = Counter(r.stratum for r in rows if r.usable)
    labelled = Counter(r.stratum for r in rows)
    sampled = {row["stratum"]: row.get("sampled") or 0 for row in (strata_log or [])}
    flagged_done = sorted(s for s in FLAGGED_STRATA if usable.get(s))
    flagged_in_sample = sorted(s for s in FLAGGED_STRATA if sampled.get(s)) if sampled else sorted(FLAGGED_STRATA)
    complete = {s: (labelled.get(s, 0) >= sampled[s]) for s in sampled} if sampled else {}
    precision_ok = bool(flagged_done)
    recall_ok = precision_ok and bool(usable.get(RECALL_STRATUM))
    reasons = []
    if not precision_ok:
        reasons.append("precision: no usable row from a flagged stratum (strict, strict_negated, conduct_*) yet")
    if not recall_ok:
        reasons.append(f"recall/F1: need annotated rows of '{RECALL_STRATUM}' (the recall denominator)"
                       if precision_ok else "recall/F1: need flagged strata and the unflagged control")
    all_flagged_complete = bool(sampled) and all(complete.get(s, False) for s in flagged_in_sample)
    all_complete = bool(sampled) and all(complete.values())
    return {
        "precision": precision_ok,
        "precision_scope": flagged_done,
        "precision_covers_all_candidates": all_flagged_complete,
        "recall": recall_ok,
        "f1": recall_ok,
        "recall_partial_control_flagged": recall_ok and not complete.get("control_flagged", True),
        "per_pattern_precision": bool(usable),
        "grounds_frequency": bool(usable),
        "strata_complete": complete,
        "annotation_complete": all_complete,
        "not_estimable_because": reasons,
    }


def mask_metrics(m: dict, est: dict) -> dict:
    """Blank out what :func:`estimability` says the annotated strata cannot support (never a fake 1.0)."""
    out = dict(m)
    if not est["precision"]:
        out["precision"] = None
    if not est["recall"]:
        out["recall"] = None
        out["f1"] = None
    return out


def go_no_go_staged(table: list[dict], complete: bool) -> list[dict]:
    """Mark the §7 verdicts provisional while the annotation is incomplete.

    A count criterion (documents reviewed, confirmed cases) that already reached its ``go`` threshold stays
    ``go``; below it, an incomplete annotation reads ``in progress`` instead of a premature ``no-go``.
    """
    out = []
    for row in table:
        r = dict(row, provisional=not complete)
        if not complete and r["criterion"] in {"candidates reviewed", "confirmed with reasons (S3 or S2)"}:
            if r["value"] is not None and r["verdict"] != "go":
                r["verdict"] = "in progress"
        out.append(r)
    return out
