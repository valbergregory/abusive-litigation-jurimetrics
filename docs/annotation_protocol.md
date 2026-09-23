# Annotation protocol — judicially signalled cases (draft v0.1, for the researcher's review)

**Status:** draft written by Claude Code from Recomendação CNJ 159/2024 and the phase-0 readings. Nothing has been annotated. The researcher revises this protocol before any labelling starts; labels are produced only by the researcher.

## 1. Unit and universe

- Unit: one STJ document (monocratic decision or acórdão) from the *íntegras* dataset, or one *espelho de acórdão*.
- Candidates: documents matched by the versioned lexicon (`config/lexicon_v2.yaml`, to be created). The lexicon is a **measurement instrument**, not a label; its precision and recall are reported against this gold set.

## 2. Label 1 — signalling status (mandatory)

| Code | Meaning |
|---|---|
| `S3` | The STJ itself recognises indications of abusive/predatory litigation in the case and grounds a measure on them (e.g., upholds the demand for documents, extinguishes the case, sends notice to OAB). |
| `S2` | The STJ upholds or does not disturb a lower-court finding of abusive litigation (typically Súmula 7 barrier), so the finding stands but is not re-examined. |
| `S1` | The term appears only as an allegation of a party or as a rejected preliminary ("advocacia predatória — afastada"), or as a citation of a precedent (Tema 1198) without application to the case. |
| `S0` | False positive of the lexicon (e.g., "custo de captação", "demandas repetitivas" in the IRDR sense). |
| `NA` | Text missing or unreadable. |

Positive class for modelling: `S3` and `S2` (report results with and without `S2`). `S1` and `S0` are **not** "legitimate": they are unsignalled.

## 3. Label 2 — grounds, multi-label, coded to Anexo A of Rec. CNJ 159/2024

Mark every item the decision mentions as grounds (A1–A20 as numbered in the annex). Most frequent expected from phase 0: A11 (irregular power of attorney), A12 (no documents supporting the claim), A7 (generic identical petitions), A6 (fragmented filings), A13 (concentration under few lawyers), A4 (forum unrelated to the parties), A1 (unsupported legal-aid requests). Also code `T1198` when Tema 1198 is applied and `MAFE` when the decision is only about *litigância de má-fé* (art. 80 CPC) without a massification pattern.

## 4. Label 3 — measure adopted (single choice)

`M0` none · `M1` order to amend/complete documents · `M2` extinction without merits · `M3` fine or costs · `M4` notice to OAB / MP / police · `M5` other (free text).

## 5. Label 4 — domain (single choice)

`D1` consumer/banking (consignado, revisional, dano moral) · `D2` civil other · `D3` criminal (habeas corpus reiteration) · `D4` public law/tax · `D5` labour/other.

## 6. Procedure

1. Read the full document, not the snippet. Record time spent.
2. Fill the five fields plus a free-text justification (one sentence) quoting the decisive passage by paragraph number, never by party name.
3. Re-annotate a blind 10 % sample after two weeks; compute Cohen's κ for Label 1. Target κ ≥ 0.75.
4. Store in `data/annotations/gold_v<N>.parquet` with `annotator`, `date`, `protocol_version`. Never store party or lawyer names in the annotation file.

## 7. What annotation must not do

- Do not infer intent, fraud or bad faith beyond what the decision states.
- Do not label lawyers, firms or parties. The object is the decision's reasoning.
- Do not treat lower-court findings as established facts; code them as `S2`.

---

## Appendix (added 2026-09-22 by Claude Code) — how the protocol is operationalised

This appendix does **not** change the taxonomy above: it records how the code implements it, so that revising
§§2–5 means revising one place. Nothing here is a label.

### A.1 Worksheet columns (`scripts/21_export_annotation_sample.py`)

`data/annotations/gold_v1_sample.csv` carries, per row: the document identifiers (`doc_id` = `<key>-<seq>`,
publication date, class, subject codes, `numero_registro`), the machine's hints (`patterns`, `annex_a_items`,
`tiers`, `negated_all`, `context_1..3` = ±320 characters around the three most informative hits) and the **empty**
label columns, named after this protocol: `label1_status` (§2), `label2_grounds` (§3), `label3_measure` (§4),
`label4_domain` (§5), `justification` and `minutes_spent` (§6.1–6.2), `annotator`, `annotation_date`,
`protocol_version` (§6.4). Save the filled file as `data/annotations/gold_v1.csv` (git-ignored, §6.4).

### A.2 Sampling frame (`src/alj/annotation.py`)

Step 20 flags ~4 % of the corpus, because the *conduct* and *sanction* tiers of the lexicon describe Annex A
conducts in ordinary procedural language. Reading all of them is impossible, so the gold set is a **stratified
sample with a fixed seed** (default 20260922), and it deliberately includes documents the lexicon never flagged:

| stratum | default size | why |
|---|---|---|
| `strict` | 600 | the phenomenon is named — expected `S3`/`S2` |
| `strict_negated` | 120 | the term appears inside a rejection — expected `S1`/`S0` (validity check) |
| `conduct_multi` | 300 | ≥ 2 Annex A conducts without the term — the phenomenon before the vocabulary |
| `conduct_sanction` | 180 | one conduct plus an applied measure |
| `control_flagged` | 100 | near misses (a pattern fired but an exclusion dropped it) |
| `control_unflagged` | 150 | never flagged: **the denominator of recall** |

Total ≈ 1.450 documents, which satisfies the go/no-go criterion of ≥ 1.000 reviewed candidates (§7 of the
feasibility report). Sizes are overridable (`--size strict=800`).

### A.3 Estimation (`scripts/22_validate_lexicon.py`, `src/alj/validation.py`)

* positive class `{S3, S2}`, reported **with and without `S2`**, as §2 requires;
* `NA` rows are excluded from the estimates and counted apart;
* because the sample is stratified, every estimate is reported raw **and** weighted by `available / sampled`
  (inverse sampling fraction), which is the only way the population precision and recall are interpretable;
* per-pattern precision and Annex A frequencies are published only for cells with ≥ 5 documents (CLAUDE.md §4);
* Cohen's κ on `label1_status` (and on the grounds set) from the blind round of §6.3.
