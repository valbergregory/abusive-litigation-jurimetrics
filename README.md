# Detecting Patterns of Abusive Litigation

*An Explainable and Human-Centered Jurimetric Framework* — research repository (Python + SQL/DuckDB).

A jurimetric study of Brazilian judicial decisions that explicitly recognise indications of abusive or
predatory litigation (Recomendação CNJ 159/2024, Anexo A; STJ Tema Repetitivo 1198), compared with
similar unsignalled cases, to learn which temporal, textual and procedural patterns are associated with
judicial signalling. The unit of analysis is the decision's reasoning, never a person: the framework is a
triage aid for human review, not an automated decision and not an accusation against a party, lawyer or
law firm. Unsignalled cases are treated as unsignalled, not as "legitimate".

Design and decision records are in `docs/feasibility_report.md` (Portuguese) and `docs/RESUME_HERE.md`;
the manual-review taxonomy is in `docs/annotation_protocol.md`.

## Data and sources

All sources are public. Every raw file is recorded with its SHA-256, size, date, licence and source in
`logs/raw_hashes.tsv`; raw data are not committed.

| Source | Provider | Content used | Licence |
|---|---|---|---|
| Íntegras de decisões terminativas e acórdãos do DJe | STJ Portal de Dados Abertos (CKAN) | Full text and metadata of every published decision, daily files since 2021-01-04 | CC-BY |
| Espelhos de acórdãos (Corte Especial, Seções, Turmas) | STJ Portal de Dados Abertos (CKAN) | Structured record of collegiate judgments: ementa, decision text, cited case law, legislative references; monthly files since 2022-05 plus the initial backlog | CC-BY |
| Acervo em tramitação and atas de distribuição | STJ Portal de Dados Abertos (CKAN) | `numeroRegistro` ↔ CNJ `numeroUnico` bridge (bridge fields only; party and lawyer fields are not ingested); atas start 2023-06-30 | CC-BY |
| Precedentes qualificados | STJ Portal de Dados Abertos (CKAN) | Registry of repetitive themes (Tema 1198) | CC-BY |
| DataJud API Pública | CNJ | Class, subject codes, judging body and the full list of `movimentos` of the bridged cases, in the STJ and in the court of origin | CNJ terms of use (Res. CNJ 331/2020) |
| Tabelas Processuais Unificadas (SGT) | CNJ | Code tables for classes, subjects and movements | public |
| Recomendação CNJ 159/2024, Resolução CNJ 615/2025 | CNJ | Normative basis of the lexicon and of the safeguards | public |

Field-level notes on each source are in `docs/data_dictionary_confirmed.md`.

## Repository structure

```
scripts/        numbered steps: 00-02 source probes; 10-12 ingestion (íntegras, espelhos, bridge);
                19 DuckDB views; 20-28 lexicon, annotation sample and annotation aids;
                30-31 DataJud trajectories and trajectory covariates; 80-91 tables, figures,
                Overleaf export and reference verification
dodo.py         doit DAG wiring the steps
src/alj/        shared modules: stj_integras, espelhos, bridge, cnj, datajud, trajectories, lexicon,
                annotation, validation, worksheet, manifest, db, export_overleaf
config/         versioned measurement instruments: lexicon_v2.yaml (regex patterns in tiers strict,
                conduct, sanction, normative, neighbour, with exclusions and negation markers) and
                movement_groups.yaml (CNJ TPU movement groups used as trajectory covariates)
docs/           feasibility_report.md, RUNBOOK.md, RESUME_HERE.md, annotation_protocol.md,
                COMO_ANOTAR.md, COMO_CONFERIR_O_LEXICO.md, data_dictionary_confirmed.md, literature_map.md
data/           raw downloads, interim Parquet, alj.duckdb, annotations     [git-ignored]
logs/           one JSON log per step (counts only) and raw_hashes.tsv
outputs/        tables/*.csv, figures/, numbers.json assembled from the logs; cells with fewer
                than five documents are suppressed
tests/          pytest (no network, no data)
```

### Database (`data/alj.duckdb`)

The Parquet files under `data/interim/` are the source of truth; the DuckDB file holds views over them,
rebuilt by `scripts/19_refresh_duckdb_views.py` (`src/alj/db.py`):

| View | Content |
|---|---|
| `documents`, `document_text` | Íntegras metadata (rapporteur stored as a salted hash) and full text |
| `candidates`, `candidate_hits` | Documents matched by the lexicon; one row per hit with its context window, exclusion and negation hint |
| `bridge` | `numeroRegistro` ↔ `numeroUnico`, CNJ segment, court and DataJud alias |
| `espelhos`, `espelho_citations`, `espelho_legislation` | Espelhos records, cited precedents and legislative references |
| `datajud_targets`, `datajud_cases`, `datajud_movimentos` | Cases requested from DataJud, their attributes and movements |
| `datajud_features` | One row of trajectory covariates per case |

Manual labels (`docs/annotation_protocol.md`: signalling status S3/S2/S1/S0/NA, grounds coded to
Anexo A, measure adopted, domain) live in `data/annotations/`, which is git-ignored.

## Reproduce

Python 3.13 (`pyproject.toml`, `uv.lock`).

```bash
python -m pip install --user uv
uv sync --extra dev
uv run pytest -q

uv run doit list            # tasks and their descriptions
uv run doit                 # default tasks: candidates, annotation_sample, outputs, figures, overleaf
uv run doit espelhos        # network tasks must be asked for by name
uv run doit trajectories
```

`docs/RUNBOOK.md` lists every step with its command, inputs and outputs. The íntegras are read from a
local mirror (`scripts/10_ingest_stj_integras.py --source DIR`); downloads and ingestion steps are
resumable and idempotent. `uv run doit validate` runs only once `data/annotations/gold_v1.csv` exists.

## Credentials

None are stored. The DataJud public key is read from the CNJ wiki page at run time
(`src/alj/datajud.py`). Optional environment variable: `ALJ_STJ_MIRROR` (path of the local íntegras
mirror used by step 10).

## Data handling and safeguards

From `docs/feasibility_report.md` §6, `docs/annotation_protocol.md` §7 and the ingestion code: public
records only; no automated decision and mandatory human review; no inference of intent, fraud or bad
faith beyond what the decision states; no labelling of lawyers, firms or parties; party and lawyer
fields of the atas are not ingested; rapporteur names are stored as salted hashes with the salt outside
the repository; reporting is aggregated by judging body and period, never by rapporteur, and cells
with fewer than five documents are suppressed; annotation files and text snippets never leave the
local machine; LGPD principles of purpose, minimisation and pseudonymisation apply.

## Licence and citation

Code: MIT (`LICENSE`). Documentation under `docs/`: CC BY 4.0 (`LICENSING.md`). Data are not part of
this repository and remain subject to the terms of their publishers (STJ, CNJ, IBGE). Cite via
`CITATION.cff`.
