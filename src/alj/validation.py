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
