"""Sampling frame and worksheet layout for the researcher's manual review (docs/annotation_protocol.md).

Step 20 flags far more documents than anyone can read: the *conduct* and *sanction* tiers match ordinary
procedural vocabulary on purpose (Annex A describes conducts, not terms of art). So the gold set is a
**stratified sample with a fixed seed**, not the whole candidate set, and it deliberately includes documents the
lexicon did NOT flag — without them precision can be computed and recall cannot (go/no-go criteria, §7 of the
feasibility report).

Strata (defaults in :data:`DEFAULT_STRATA`):

==========================  ============================================================================
``strict``                  a strict-tier pattern fired and was not negated — the phenomenon is named
``strict_negated``          a strict-tier pattern fired inside a rejection ("afastada a alegação")
``conduct_multi``           no strict term, but ≥ 2 distinct Annex A conducts — the unnamed phenomenon
``conduct_sanction``        no strict term, one conduct plus an applied measure/sanction
``control_flagged``         pre-filtered documents that survived no pattern (near misses)
``control_unflagged``       random documents the lexicon never touched — the recall denominator
==========================  ============================================================================

The worksheet carries the mechanical hints (which patterns fired, which Annex A items, whether the window looks
like a rejection) and the **empty label columns of the protocol** (§§2–5: ``label1_status`` S3/S2/S1/S0/NA,
``label2_grounds`` A1…A20/T1198/MAFE, ``label3_measure`` M0…M5, ``label4_domain`` D1…D5, plus the §6 bookkeeping).
Filling them is the researcher's job (CLAUDE.md §2); the codes are his, not this module's.
"""

from __future__ import annotations

from dataclasses import dataclass

#: the label columns are exactly the four labels of docs/annotation_protocol.md §§2–5 plus its §6 bookkeeping
LABEL_COLUMNS: tuple[str, ...] = (
    "label1_status",  # §2: S3 | S2 | S1 | S0 | NA
    "label2_grounds",  # §3: multi-label, ';'-separated — A1…A20, T1198, MAFE
    "label3_measure",  # §4: M0 | M1 | M2 | M3 | M4 | M5
    "label4_domain",  # §5: D1 | D2 | D3 | D4 | D5
    "justification",  # §6.2: one sentence quoting the decisive passage by paragraph, never by party name
    "minutes_spent",  # §6.1
    "annotator",  # §6.4
    "annotation_date",  # §6.4
    "protocol_version",  # §6.4
)

META_COLUMNS: tuple[str, ...] = (
    "doc_id",
    "key",
    "seq_documento",
    "data_publicacao",
    "tipo_documento",
    "classe",
    "processo",
    "numero_registro",
    "assuntos_leaf",
    "nchar",
)

HINT_COLUMNS: tuple[str, ...] = (
    "stratum",
    "patterns",
    "annex_a_items",
    "tiers",
    "n_hits",
    "negated_all",
    "context_1",
    "context_2",
    "context_3",
)


@dataclass(frozen=True)
class Stratum:
    name: str
    size: int
    where: str
    rationale: str


DEFAULT_STRATA: tuple[Stratum, ...] = (
    Stratum(
        "strict",
        600,
        "strict_hit AND NOT negated_all",
        "core class: the decision names litigancia predatoria/abusiva, assedio processual - expected S3/S2",
    ),
    Stratum(
        "strict_negated",
        120,
        "strict_hit AND negated_all",
        "validity: allegations the court rejected must end up S1/S0, not S3/S2",
    ),
    Stratum(
        "conduct_multi",
        300,
        "NOT strict_hit AND n_conduct_patterns >= 2",
        "the phenomenon described without the term — where the framework can add value",
    ),
    Stratum(
        "conduct_sanction",
        180,
        "NOT strict_hit AND conduct_hit AND sanction_hit",
        "conduct plus an applied measure: the intensity end of the ladder",
    ),
    Stratum(
        "control_flagged",
        100,
        "prefiltered but no pattern survived",
        "near misses: measures the cost of the exclusions",
    ),
    Stratum(
        "control_unflagged",
        150,
        "random documents with text, never flagged",
        "recall denominator: without it only precision is estimable",
    ),
)

#: fraction of the sample re-exported blind for the κ agreement check (go/no-go: κ ≥ 0.75)
REANNOTATION_FRACTION = 0.10


def worksheet_columns() -> list[str]:
    return [*META_COLUMNS, *HINT_COLUMNS, *LABEL_COLUMNS]


def stratum_by_name(name: str, strata: tuple[Stratum, ...] = DEFAULT_STRATA) -> Stratum:
    for s in strata:
        if s.name == name:
            return s
    raise KeyError(name)
