# Detecting Patterns of Abusive Litigation

*An Explainable and Human-Centered Jurimetric Framework* — research repository (Python + SQL).

**Status (2026-09-22):** phase 0 (feasibility) closed on 2026-09-05; phase 1 corpus work runs end to end —
the íntegras (3.48 M documents), the espelhos de acórdãos (165.8 k, with their citations and legislative
references), the `numeroRegistro` ↔ CNJ bridge from the acervo snapshot, the versioned lexicon v2 and the
stratified annotation worksheet. **No label, no model and no result exists yet**: the gold set is annotated by
the researcher (`docs/annotation_protocol.md`), and the study design (A / B / B+C) is still his decision.
Read [docs/feasibility_report.md](docs/feasibility_report.md) (Portuguese, the decision document) and
[docs/RESUME_HERE.md](docs/RESUME_HERE.md) before anything else.

## What this project is

A jurimetric study of Brazilian judicial decisions that *explicitly* recognise indications of abusive or predatory litigation (Recomendação CNJ 159/2024; STJ Tema Repetitivo 1198), compared with similar unsignalled cases, to learn which temporal, textual and procedural patterns are associated with judicial signalling. The system is a **triage aid for human review**, never an automated decision, never an accusation against a person, law firm or party.

## Data sources (all public, all verified in phase 0)

| Source | Use | Caveat |
|---|---|---|
| STJ open data — *íntegras* of decisions (daily ZIP + JSON since 2021) | full text and metadata of the signalling corpus | text coverage drops in 2026; texts contain party names |
| STJ open data — *espelhos de acórdãos* (monthly JSON since 2022) | structured ementa, cited precedents, cited legislation | curated subset of judgments |
| STJ open data — *acervo em tramitação* and *atas de distribuição* | bridge `numeroRegistro` ↔ CNJ `numeroUnico`; atas also hold parties/lawyers (**not used unless the ethics protocol of design C is approved**) | atas start 2023-06-30 |
| CNJ DataJud public API | classe, assunto, órgão, município IBGE, movimentos, duration, in STJ and in the tribunal of origin | `dataAjuizamento` is a 14-digit string: filter by `movimentos.dataHora`, parse client-side |
| CNJ SGT tables, IBGE | code books, territorial normalisation | |

## Layout

```
scripts/        numbered, reproducible steps (00–02 feasibility probes; 10–23 phase 1; 80/90 study export)
dodo.py         doit DAG wiring the steps (`uv run doit list`)
src/alj/        shared modules: cnj, stj_integras, espelhos, bridge, lexicon, annotation, validation, db, manifest
config/         versioned measurement instruments — `lexicon_v2.yaml` (47 patterns in five tiers)
data/raw/       downloads (git-ignored; SHA-256 in logs/raw_hashes.tsv)
data/interim/   parquet / duckdb intermediates (git-ignored)
logs/           JSON logs of every probe and pipeline step (never containing personal data)
```

## Environment and tests

```bash
python -m pip install --user uv
python -m uv sync
python -m uv run pytest -q
```

Full step-by-step instructions, with what each step reads and writes: [docs/RUNBOOK.md](docs/RUNBOOK.md).

## Running the probes

```bash
python -m uv run python scripts/00_probe_stj_sample.py   # downloads ~9 days of STJ decisions, keyword scan
python -m uv run python scripts/01_probe_datajud.py      # DataJud fields + municipality coverage
python -m uv run python scripts/02_probe_bridge.py       # STJ -> CNJ number -> DataJud linkage test
```

Those reproducibility artefacts now exist: `uv` environment + lockfile, the `doit` DAG in `dodo.py`, DuckDB
views rebuilt from Parquet by `scripts/19_refresh_duckdb_views.py`, 200+ unit tests, `docs/RUNBOOK.md`, the
download manifest `logs/raw_hashes.tsv` (sha256, bytes, date, licence, source, file), `CITATION.cff` and
`LICENSE`. The Zenodo release comes before submission.

## Safeguards (non-negotiable)

No automated decision; mandatory human review; configurable threshold; every alert stores its reasons; no inference of fraud; no exposure of people (salted hashes, salt outside the repository, aggregate reporting only, no nominal rankings); impact assessment for vulnerable litigants; LGPD compliance; documented limitations; contestation mechanism in the research prototype.

## License

Code: MIT ([LICENSE](LICENSE)). Text, documentation and data: see [LICENSING.md](LICENSING.md).
