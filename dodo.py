"""doit DAG for the pipeline (CLAUDE.md: "numbered scripts in scripts/ + doit DAG").

    uv run doit list          # the tasks and what they do
    uv run doit               # everything that is out of date and needs no authorisation
    uv run doit candidates    # one task and its dependencies

Design rules of this file:

* a task that **downloads** (11) or reads a 4.2 GB mirror (12 with --atas) is NOT in ``DOIT_CONFIG['default_tasks']``;
  it must be asked for by name, so that ``doit`` never starts network traffic on its own;
* a task that depends on the researcher's manual work (22, which needs the gold set) is skipped with a clear
  message instead of failing;
* the targets are the JSON logs, because they are the small, committed evidence that a step ran; the Parquet
  files themselves are git-ignored and are checked by ``uptodate`` on the directory contents.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
LOG = ROOT / "logs"
DATA = ROOT / "data"

DOIT_CONFIG = {
    "default_tasks": ["candidates", "annotation_sample", "outputs", "overleaf"],
    "verbosity": 2,
}


def _script(name: str) -> str:
    return f'"{PY}" "{ROOT / "scripts" / name}"'


def task_integras():
    """10 - ingest the integras corpus from the local mirror (no download)."""
    return {
        "actions": [_script("10_ingest_stj_integras.py")],
        "targets": [LOG / "10_ingest_stj_integras.json"],
        "uptodate": [(DATA / "interim" / "stj_integras" / "text").exists],
    }


def task_espelhos():
    """11 - download and ingest the espelhos (NETWORK: ask for this task by name)."""
    return {
        "actions": [_script("11_ingest_stj_espelhos.py")],
        "targets": [LOG / "11_ingest_stj_espelhos.json"],
        "uptodate": [False],  # resumable and idempotent; let the researcher decide when to re-run
    }


def task_bridge():
    """12 - numeroRegistro <-> numeroUnico bridge from the acervo snapshot (add --atas DIR for the history)."""
    return {
        "actions": [_script("12_ingest_stj_bridge.py")],
        "targets": [LOG / "12_ingest_stj_bridge.json"],
        "task_dep": ["integras"],
    }


def task_candidates():
    """20 - apply config/lexicon_v2.yaml to the corpus and write the candidate set."""
    return {
        "actions": [_script("20_lexicon_candidates.py")],
        "targets": [LOG / "20_lexicon_candidates.json"],
        "file_dep": [ROOT / "config" / "lexicon_v2.yaml", ROOT / "src" / "alj" / "lexicon.py"],
        "task_dep": ["integras"],
    }


def task_candidates_espelhos():
    """23 - apply the same lexicon to the espelhos (needs task `espelhos` first)."""
    return {
        "actions": [_script("23_lexicon_espelhos.py")],
        "targets": [LOG / "23_lexicon_espelhos.json"],
        "file_dep": [ROOT / "config" / "lexicon_v2.yaml"],
        "uptodate": [False],
    }


def task_annotation_sample():
    """21 - draw the stratified annotation worksheet for the researcher."""
    return {
        "actions": [_script("21_export_annotation_sample.py")],
        "targets": [LOG / "21_export_annotation_sample.json"],
        "task_dep": ["candidates"],
    }


def task_validate():
    """22 - validate the lexicon against the gold set (needs data/annotations/gold_v1.csv)."""

    def run() -> bool:
        gold = DATA / "annotations" / "gold_v1.csv"
        if not gold.exists():
            print(f"skipped: {gold.relative_to(ROOT)} does not exist yet (step 21b is manual)")
            return True
        import subprocess

        return subprocess.run([PY, str(ROOT / "scripts" / "22_validate_lexicon.py")], check=False).returncode == 0

    return {"actions": [run], "task_dep": ["annotation_sample"], "uptodate": [False]}


def task_views():
    """19 - rebuild the DuckDB views from the Parquet files."""
    return {"actions": [_script("19_refresh_duckdb_views.py")], "uptodate": [False]}


def task_outputs():
    """80 - assemble outputs/tables/*.csv and outputs/numbers.json from the logs."""
    return {
        "actions": [_script("80_build_outputs.py")],
        "targets": [LOG / "80_build_outputs.json"],
        "uptodate": [False],
    }


def task_overleaf():
    """90 - export outputs/ to outputs/overleaf/ (booktabs tables, numbers.tex)."""
    return {"actions": [_script("90_export_overleaf.py")], "task_dep": ["outputs"], "uptodate": [False]}


def task_tests():
    """Unit tests (no network, no data)."""
    return {"actions": [f'"{PY}" -m pytest -q'], "uptodate": [False]}
