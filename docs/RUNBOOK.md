# RUNBOOK — how to reproduce this repository step by step

Every step says what it reads, what it writes and how long it took on the reference machine
(Windows 11, Python 3.13, RTX 4060 8 GB, 1.3 TB free on D:). Steps are numbered in execution order.
Long steps should run in the background (PowerShell `Start-Job { ... }` or the Claude Code
background Bash) so the terminal stays free.

## 0. Environment (once)

```bash
python -m pip install --user uv          # if `uv` is not on PATH
python -m uv sync                        # creates .venv from pyproject.toml + uv.lock
python -m uv run pytest -q               # unit tests (no network, no data)
```

Writes: `.venv/` (git-ignored), `uv.lock` (committed). ~2 min. Optional extras: `uv sync --extra nlp` (PyTorch + sentence-transformers, ~3 GB), `--extra stats`, `--extra graph`, `--extra dev`.

## Phase 0 — feasibility (done 2026-09-05)

| # | Command | Reads | Writes | Time |
|---|---|---|---|---|
| 00 | `uv run python scripts/00_probe_stj_sample.py [YYYYMMDD ...]` | STJ CKAN API; ~9 daily ZIP+JSON of *íntegras* | `data/raw/stj/*`, `logs/00_probe_stj_sample.json` (counts only), `data/interim/probe_snippets_*.json` (local only) | ~6 min |
| 01 | `uv run python scripts/01_probe_datajud.py [tjsp tjmg ...]` | DataJud wiki (public key), 2 endpoints + aggregations | `data/raw/datajud/sample_*.json`, `logs/01_probe_datajud.json` | ~2 min |
| 02 | `uv run python scripts/02_probe_bridge.py` | `data/raw/stj/acervo_*.json.gz` (77 MB download done manually in phase 0), `metadados*.json`, DataJud | `logs/02_probe_bridge.json` | ~1 min |

Manual downloads of phase 0 (dictionaries, espelhos sample, CNJ acts, SGT tables) are listed with SHA-256 in `logs/raw_hashes.tsv`.
Result: `docs/feasibility_report.md`.

## Phase 1 — corpus and annotation (steps 10–12 and 19–22 written and run; the **design choice A / B / B+C**, the review of the annotation protocol, the manual annotation and the 4.2 GB atas download still wait for the researcher)

| # | Planned script | Reads | Writes | Est. time |
|---|---|---|---|---|
| 10 | `uv run python scripts/10_ingest_stj_integras.py [--source DIR] [--keys FROM TO] [--limit N] [--force]` (**run 2026-09-12: 3,482,383 documents, 2,975,817 texts, 6.0 GB Parquet, ~10 min**) | local mirror of all daily/monthly ZIP+JSON since 2021-01-04 (11.4 GB, 1.287 keys; default = sibling repo `STJ-Moral-Damages-Jurimetrics/data/raw/stj_integras`, downloaded with SHA-256 on 2026-09-07/08 — nothing is downloaded by this script) | `data/interim/stj_integras/{meta,text}/<key>.parquet` (rapporteur salted-hashed, no party names), `data/alj.duckdb` (views `documents`, `document_text`; table `ingest_log`), `logs/raw_hashes.tsv`, `logs/10_ingest_stj_integras.json` (counts only) | ~1–2 h parse, resumable per key |
| 11 | `uv run python scripts/11_ingest_stj_espelhos.py [--orgaos …] [--workers 6] [--no-download] [--no-zips] [--limit-files N]` (**run 2026-09-22; ZIP backlog added 2026-09-23 → 877.353 espelhos, 2,0 M citations, 1,2 M legislative references, back to 1989**) | CKAN `package_show` of the 10 bodies at run time → 52 monthly JSON each (~85 MB per body) **plus the initial backlog ZIP** (~11–20 MB each, the historical acervo since 1989) | `data/raw/stj_espelhos/<orgao>/*.json`, `data/interim/espelhos/{espelhos,citations,legislation}/*.parquet`, views `espelhos`, `espelho_citations`, `espelho_legislation`, `logs/11_ingest_stj_espelhos.json` | download-bound: the portal serves ~80 kB/s per connection, so 6 workers ≈ 30–60 min; resumable (a file whose size matches the published size is never fetched again) |
| 11b | `uv run python scripts/11b_probe_espelho_zip.py [--orgao corte-especial]` (**run 2026-09-23**) | one dataset's initial ZIP (CKAN) | `logs/11b_probe_espelho_zip.json` — measured 14.223 records / 12.390 registrations, 1989–2022, only 92 shared with the monthly series, i.e. the ZIP is NOT a duplicate | ~2 min, downloads ~11 MB and deletes it |
| 12 | `uv run python scripts/12_ingest_stj_bridge.py [--acervo FILE] [--atas DIR] [--limit N]` (**written and run 2026-09-22 on the acervo snapshot + the single sample ata**) | `data/raw/stj/acervo_processos_tramitando_*.json.gz` (77 MB, already in the repo) and, with `--atas DIR`, a local mirror of the atas since 2023-06-30 (**bridge fields only**; the 4.2 GB download stays a separate authorised step) | `data/interim/bridge/*.parquet` (`numeroRegistro` ↔ `numeroUnico` + CNJ segment/tribunal/DataJud alias), view `bridge`, `logs/12_ingest_stj_bridge.json` (coverage by year) | ~2 min for the acervo |
| 13 | ~~`13_check_text_coverage.py`~~ folded into step 10: `by_year` / `low_coverage_keys` in `logs/10_ingest_stj_integras.json` (2026 = 27.8 %, see feasibility §10) | — | — | — |
| 19 | `uv run python scripts/19_refresh_duckdb_views.py [--only view …]` | all Parquet directories | rebuilds every view of `data/alj.duckdb` (the database is a derived artefact; run this after a step whose log says `views_created: false`, i.e. the file was locked by another step) | seconds |
| 20 | `uv run python scripts/20_lexicon_candidates.py [--keys FROM TO] [--sample N] [--force]` (**written and run 2026-09-22**) | `data/interim/stj_integras/text/*.parquet` + `config/lexicon_v2.yaml` (v2.0.0, 47 patterns; 36 in the candidate tiers) | `data/interim/candidates/{docs,hits}/<key>.parquet` (one row per candidate document; one row per hit with a ±320-char context window, the exclusion that fired and the negation hint), views `candidates`, `candidate_hits`, table `lexicon_run_log`, `logs/20_lexicon_candidates.json` | ~1.8 s per publication day (≈ 40 min for the 1.285 days), resumable per key |
| 21 | `uv run python scripts/21_export_annotation_sample.py [--seed N] [--size NAME=N] [--max-year 2025]` (**written and run 2026-09-22**) | the candidate Parquet + the íntegras metadata (reads Parquet directly, so it never locks the database) | `data/annotations/gold_v1_sample.csv` (stratified worksheet with empty label columns), `gold_v1_reannotation.csv` (10 %, hints stripped, for κ), `README_annotation.md`, `logs/21_export_annotation_sample.json` | ~1 min |
| 21b | **researcher's manual review** — fill `label1_status` (S3/S2/S1/S0/NA), `label2_grounds` (A1…A20/T1198/MAFE), `label3_measure` (M0…M5), `label4_domain` (D1…D5) and `justification`, per `docs/annotation_protocol.md` §§2–6; save as `data/annotations/gold_v1.csv` (git-ignored) | the worksheet | the gold set | days, by hand |
| 22 | `uv run python scripts/22_validate_lexicon.py [--gold FILE] [--self-test]` (**written 2026-09-22; `--self-test` passes, real run waits for the gold set**) | `data/annotations/gold_v1.csv` (+ the blind round, if any), `logs/21_…json` for the inverse-sampling weights | precision/recall/F1 raw **and** weighted back to the population, per-pattern precision (k ≥ 5), Cohen's κ and the §7 go/no-go verdicts → `logs/22_lexicon_validation.json` | 1 min |
| 23 | `uv run python scripts/23_lexicon_espelhos.py [--orgaos …]` (**written 2026-09-22**) | `data/interim/espelhos/espelhos/*.parquet` (ementa + decisão + notas) and the same lexicon | `data/interim/candidates_espelhos/{docs,hits}/*.parquet`, views `espelho_candidates`, `espelho_candidate_hits`, `logs/23_lexicon_espelhos.json` | ~2 min; needs step 11 |
| 24 | `uv run python scripts/24_crosscheck_integras_espelhos.py` (**written and run 2026-09-23**) | `candidates`, `espelho_candidates`, metadata | agreement between the two public sources on the same `numeroRegistro` → `logs/24_crosscheck_integras_espelhos.json` (**when the íntegra names the phenomenon the espelho names it in 29,4 % of the shared cases**) | ~2 min |
| 30 | `30_fetch_datajud_trajectories.py` (not written) | bridge + DataJud (STJ + origin) | `trajectories.parquet`, table `movements` | hours, background |

### Running the whole thing

`dodo.py` (added 2026-09-22) wires the steps as a `doit` DAG:

```bash
uv run doit list         # every task with its one-line description
uv run doit              # candidates -> annotation_sample -> outputs -> overleaf (no network, no manual step)
uv run doit espelhos     # the download task must be asked for by name
```

`doit` never starts network traffic on its own (`espelhos` is outside the default tasks) and `validate` skips
itself with a message while `data/annotations/gold_v1.csv` does not exist.

Go/no-go review after step 22 (criteria in `docs/feasibility_report.md` §7).

### Why step 20 flags ~4 % of the corpus

The *conduct* and *sanction* tiers describe Annex A conducts in ordinary procedural language ("ausência de
documentos essenciais", "extinto sem resolução do mérito"), so they match far more decisions than the strict terms
("litigância predatória"). That is by design: the strict terms alone would only find the phenomenon after the
vocabulary existed (2024+). The candidate set is therefore a **reading frame**, not a class; the gold set is drawn
from it by stratified sampling in step 21, and step 22 weights the estimates back to the population.

## Export to the manuscript (every phase)

```bash
uv run python scripts/80_build_outputs.py      # logs/*.json + the lexicon YAML -> outputs/tables/*.csv + outputs/numbers.json
uv run python scripts/81_build_figures.py      # logs/*.json -> outputs/figures/*.{pdf,png} (4 descriptive figures)
uv run python scripts/90_export_overleaf.py    # -> outputs/overleaf/{tables/*.tex, figures/, numbers.tex}
```

Step 80 (added 2026-09-22) reads only the JSON logs written by the steps that measured each value, suppresses
cells with fewer than 5 documents and writes no table for a log that does not exist yet. Step 90 (2026-09-12;
`src/alj/export_overleaf.py`) turns the CSVs into booktabs tables and the numbers into one `\newcommand` each.
Copy `outputs/overleaf/` to Overleaf; never type a number by hand (policy §13).

## Phase 1 status (2026-09-22)

Done: 10, 11 (JSON + ZIP backlog), 11b, 12 (acervo), 19, 20, 21, 23, 24, 80, 81, 90 — plus `22 --self-test`. Waiting on the researcher: the design
choice (A / B / B+C), the review of `docs/annotation_protocol.md`, the manual annotation (step 21b) and the
authorisation to download the 4.2 GB of atas (the historical half of the bridge).
