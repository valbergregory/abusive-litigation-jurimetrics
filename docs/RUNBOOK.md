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

## Phase 1 — corpus and annotation (pending researcher approval)

| # | Planned script | Reads | Writes | Est. time |
|---|---|---|---|---|
| 10 | `10_ingest_stj_integras.py` | all daily ZIP+JSON since 2021-01-04 (11.2 GB) | `data/interim/stj_integras/*.parquet` (metadata + text), DuckDB table `documents` | 2–4 h download, 20 min parse |
| 11 | `11_ingest_stj_espelhos.py` | 10 órgãos × monthly JSON (0.5 GB) + initial ZIPs (0.5 GB) | `espelhos.parquet`, tables `citations`, `legislation` | 30 min |
| 12 | `12_ingest_stj_bridge.py` | acervo snapshot + atas since 2023-06-30 (4.2 GB; **bridge fields only**) | `bridge.parquet` (`numeroRegistro` ↔ `numeroUnico`) | 1–2 h |
| 13 | `13_check_text_coverage.py` | tables `documents` | `logs/13_text_coverage.json`, figure | 5 min |
| 20 | `20_lexicon_candidates.py` | `documents`, `espelhos`, `config/lexicon_v2.yaml` | `candidates.parquet` with context windows | 15 min |
| 21 | annotation UI / spreadsheet export | `candidates.parquet` | `data/annotations/gold_v1.parquet` (researcher-labelled) | manual |
| 22 | `22_validate_lexicon.py` | gold set | precision/recall/F1 per pattern → `logs/22_lexicon_validation.json` | 1 min |
| 30 | `30_fetch_datajud_trajectories.py` | bridge + DataJud (STJ + origin) | `trajectories.parquet`, table `movements` | hours, background |

Go/no-go review after step 22 (criteria in `docs/feasibility_report.md` §7).

## Export to the manuscript (every phase)

`uv run python scripts/90_export_overleaf.py` → `outputs/overleaf/tables/*.tex` (booktabs), `outputs/overleaf/figures/*.{pdf,png}`, `outputs/overleaf/numbers.tex` (one `\newcommand` per number cited in the article). Copy the folder to Overleaf; never type numbers by hand.
