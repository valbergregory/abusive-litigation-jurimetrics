# Detecting Patterns of Abusive Litigation

*An Explainable and Human-Centered Jurimetric Framework* — research repository (Python + SQL).

**Status:** phase 0 (feasibility) completed on 2026-09-05. See [docs/feasibility_report.md](docs/feasibility_report.md) (in Portuguese, the decision document) before anything else. No model, label or result exists yet.

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
scripts/        numbered, reproducible steps (00–02 = feasibility probes; 10+ = phase 1, planned)
src/alj/        shared helpers (CNJ number parsing, DataJud date handling) with unit tests in tests/
config/         versioned measurement instruments (lexicons, model configs) — phase 1
article/        LaTeX skeleton for Overleaf (author writes all prose); tables/figures/numbers.tex are generated
outputs/        pipeline exports for the manuscript (outputs/overleaf/), git-ignored except README files
data/raw/       downloads (git-ignored; SHA-256 in logs/raw_hashes.tsv)
data/interim/   parquet / duckdb intermediates (git-ignored)
docs/           feasibility report, confirmed data dictionary, RUNBOOK, annotation protocol, AI policy
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

Phase 1 will add `uv` (environment + lockfile, interpreter version pinned, `pip freeze` copy in `logs/`), a `doit` DAG, DuckDB schema, unit tests, `docs/RUNBOOK.md` (numbered steps: what each reads, writes, how long it takes), a download manifest (URL, date, SHA-256, licence), `CITATION.cff`, `LICENSE` (MIT for code, CC-BY for text) and a Zenodo release before submission.

## Reproducibility and AI-use policy

The portfolio-wide policy lives in [docs/AI_POLICY_AND_REPRODUCIBILITY.md](docs/AI_POLICY_AND_REPRODUCIBILITY.md) (with LaTeX disclosure snippets in `docs/latex_snippets/`). Consequences for this repository:

- Every automatic detector of abusive-litigation language (regex dictionary, embeddings, classifier, local LLM) is a **measurement instrument**: versioned, seeded, temperature 0, prompts under version control, and validated against a gold set annotated by the researcher (precision, recall, F1) before any use.
- Only local models unless the researcher authorises a paid API in writing.
- Patterns are reported in aggregate (tribunal, class, subject, period). No lawyer, firm or party is ever labelled nominally.
- An export step will write `outputs/overleaf/` (booktabs tables, PDF/PNG figures, `numbers.tex` with one `\newcommand` per number cited) so that every figure in the manuscript traces back to code.
- Claude Code writes code, tests, SQL, configuration, documentation and runbooks. Whether it may also draft manuscript prose, and whether the manuscript is Quarto or an Overleaf LaTeX skeleton, is a pending decision of the researcher (see feasibility report §8).

## Safeguards (non-negotiable)

No automated decision; mandatory human review; configurable threshold; every alert stores its reasons; no inference of fraud; no exposure of people (salted hashes, salt outside the repository, aggregate reporting only, no nominal rankings); impact assessment for vulnerable litigants; LGPD compliance; documented limitations; contestation mechanism in the research prototype.

## License

Code: MIT ([LICENSE](LICENSE)). Text, documentation and data: see [LICENSING.md](LICENSING.md).
