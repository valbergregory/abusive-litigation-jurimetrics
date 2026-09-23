# CLAUDE.md — working rules for this repository

## Purpose
Research code for the article *Detecting Patterns of Abusive Litigation: An Explainable and Human-Centered Jurimetric Framework*. Single researcher (law, PhD economics, judiciary, information systems). Article in English; conversation with the researcher in Brazilian Portuguese; decision documents in `docs/` may be in Portuguese.

## Stack (decided 2026-09-05, see docs/feasibility_report.md §0)
- **Python only** (3.13) + **SQL via DuckDB**. No R in the core pipeline; an optional R appendix may read Parquet exports.
- Environment: `uv` (`pyproject.toml` + `uv.lock`). Never `pip install` into the global interpreter.
- Data: `polars`/`pyarrow` for ingestion, DuckDB for tables and audit trail (`fts`/`vss` extensions), Parquet for intermediates.
- ML/NLP: `scikit-learn`, `sentence-transformers` (GPU RTX 4060 8 GB), `networkx`/`igraph`; PyTorch Geometric **only** with documented justification and enough data.
- Pipeline: numbered scripts in `scripts/` + `doit` DAG; long jobs run in the background (PowerShell `Start-Job` or Claude Code background Bash), never blocking.
- Manuscript: Quarto with Jupyter kernel.

## Hard rules
1. **Never fabricate** data, labels, results, access, or relations. If a source is missing, say so and stop.
2. **Keyword hit ≠ label.** Labels come only from the manual legal review protocol in `docs/annotation_protocol.md` (phase 1).
3. Unsignalled cases are "not signalled", never "legitimate".
4. **No personal identifiers** in features, outputs, figures, tables, logs or commit messages. Names from texts/atas are dropped or salted-hashed (`.secrets/salt`, git-ignored). No nominal rankings, ever. Aggregate reporting with k ≥ 5.
5. Party/lawyer fields of the *atas de distribuição* are **not** ingested until the design-C ethics protocol is written and approved by the researcher.
6. No random splits: split by time, by document group (near-duplicate decisions) and by tribunal.
7. Every download gets a SHA-256 line in `logs/raw_hashes.tsv`; every script writes a JSON log to `logs/`.
8. DataJud: read the public key from the wiki at runtime; never hard-code it. Filter dates via `movimentos.dataHora`; parse `dataAjuizamento` client-side (server-side date ops are broken for millions of documents).
9. Git: commit only when the researcher asks; `data/` is git-ignored.
10. The system supports human triage. Any wording implying automated decision, accusation or fraud inference is wrong and must be rewritten.

## Portfolio-wide policy (researcher's directive of 2026-09-05, incorporated 2026-09-07 at the researcher's request to organise the repository)
Master copy: `docs/AI_POLICY_AND_REPRODUCIBILITY.md` (identical across the five jurimetrics repositories).
11. **Claude Code never writes manuscript prose.** It writes code, tests, SQL, configuration, documentation and the runbook. `article/` holds only the LaTeX skeleton (`main.tex` with `\input`, `% AUTHOR WRITES` markers, the two policy snippets, `references.bib`); the researcher writes in Overleaf.
12. Every automatic detector (regex lexicon, embeddings, classifier, local LLM) is a **measurement instrument**: versioned in `config/`, seeded, temperature 0, prompts under version control, validated against the researcher's gold set (precision/recall/F1) and described in Methods (policy §5.3). Only local models unless the researcher authorises a paid API in writing.
13. Numbers in the article come from `scripts/90_export_overleaf.py` → `outputs/overleaf/{tables,figures,numbers.tex}`. Never typed by hand.
14. `docs/RUNBOOK.md` is kept current: numbered steps, what each reads and writes, how long it takes.
15. Reproducibility artefacts: `uv.lock` + interpreter version, `pip freeze` copy in `logs/`, download manifest (URL, date, SHA-256, licence), `CITATION.cff`, `LICENSE`, Zenodo release before submission.

## Where things are
- Feasibility report: `docs/feasibility_report.md` (go/no-go criteria in §7).
- Confirmed fields: `docs/data_dictionary_confirmed.md`.
- Probes: `scripts/00_probe_stj_sample.py`, `01_probe_datajud.py`, `02_probe_bridge.py`; results in `logs/`.
- Normative texts (extracted): `data/raw/cnj/*.txt` (Rec. 159/2024 with annexes A–C, Res. 615/2025, Rede de Litigância Abusiva page, Berna news).
- Measurement instrument: `config/lexicon_v2.yaml` (47 patterns in five tiers: 7 strict, 22 conduct, 7 sanction, 6 normative, 5 neighbour; 4 exclusions, 2 negation markers) + `src/alj/lexicon.py`; every pattern has an example asserted in `tests/test_lexicon.py`.
- Phase-1 modules: `src/alj/{lexicon,annotation,validation,bridge,espelhos,db}.py`; scripts 11 (espelhos), 12 (bridge), 19 (refresh views), 20 (candidates), 21 (annotation sample), 22 (validation), 80 (outputs), 90 (Overleaf).
- Annotation: worksheet and strata in `docs/annotation_protocol.md` (appendix A); files in `data/annotations/` are git-ignored because they carry decision snippets.
- AI use log: `docs/ai_usage_log.md` — every tool, date, what went in, what came out and what was done with it (this is what the article's disclosure is built from).
