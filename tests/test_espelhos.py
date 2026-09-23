"""Tests for the espelhos readers (alj.espelhos) and the DuckDB view registry (alj.db).

The strings below are the real published shapes (taken from the phase-0 sample of the Terceira Turma): the
placeholder ``"None"``, the journal prefix in ``dataPublicacao``, the Python repr of a list in
``referenciasLegislativas`` and the ``<<…>>`` citation markers.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from alj.db import VIEW_SOURCES, connect_or_memory, create_views
from alj.espelhos import (
    CITATION_SCHEMA,
    ESPELHO_SCHEMA,
    LEGISLATION_SCHEMA,
    clean,
    espelho_row,
    parse_citations,
    parse_compact_date,
    parse_legislation,
    parse_publication,
    parse_repr_list,
    read_espelhos,
)

SALT = b"salt-for-tests"

RECORD = {
    "id": "1440321",
    "numeroDocumento": "None",
    "numeroProcesso": "2465818",
    "numeroRegistro": "202303066741",
    "siglaClasse": "AgInt nos EDcl no AREsp",
    "descricaoClasse": "AGRAVO INTERNO NOS EMBARGOS DE DECLARAÇÃO",
    "classePadronizada": "None",
    "nomeOrgaoJulgador": "TERCEIRA TURMA",
    "ministroRelator": "MARCO AURÉLIO BELLIZZE",
    "dataPublicacao": "DJE        DATA:19/06/2024",
    "ementa": "AGRAVO INTERNO. LITIGÂNCIA PREDATÓRIA. IRREGULARIDADE DE REPRESENTAÇÃO.",
    "tipoDeDecisao": "ACÓRDÃO",
    "dataDecisao": "20240617",
    "decisao": "Vistos e relatados estes autos, acordam os Ministros...",
    "jurisprudenciaCitada": "(SOCIEDADE LIMITADA - SÓCIO - REQUISITOS)\n    STJ - <<REsp 1816742>>-SP\n"
                            "(PLANO DE SAÚDE - ASTREINTES)\n    STF - <<ARE 123456>>",
    "notas": "None",
    "informacoesComplementares": "None",
    "termosAuxiliares": "None",
    "teseJuridica": "None",
    "tema": "None",
    "referenciasLegislativas": "['LEG:FED LEI:010406 ANO:2002\\n *****  CC-02\\n         ART:00966 PAR:00001', "
                              "'LEG:FED LEI:013105 ANO:2015\\n         ART:00523']",
    "acordaosSimilares": "[]",
}


def test_clean_normalises_the_published_placeholders():
    assert clean("None") is None and clean("") is None and clean("  -  ") is None
    assert clean(" ACÓRDÃO ") == "ACÓRDÃO"
    assert clean(None) is None
    assert clean(0) == "0"


def test_parse_publication_splits_journal_and_date():
    assert parse_publication("DJE        DATA:19/06/2024") == ("DJE", dt.date(2024, 6, 19))
    assert parse_publication("DJEN       DATA:28/05/2026") == ("DJEN", dt.date(2026, 5, 28))
    assert parse_publication("DJE  DATA:32/13/2024")[1] is None  # impossible date, never guessed
    assert parse_publication("None") == (None, None)


def test_parse_compact_date():
    assert parse_compact_date("20240617") == dt.date(2024, 6, 17)
    assert parse_compact_date("2024-06-17") is None
    assert parse_compact_date("20241332") is None
    assert parse_compact_date("None") is None


def test_parse_repr_list_handles_python_reprs():
    assert parse_repr_list("['a', 'b']") == ["a", "b"]
    assert parse_repr_list("[]") == []
    assert parse_repr_list("None") == []
    assert parse_repr_list("plain text") == ["plain text"]
    assert parse_repr_list("['unterminated") == ["['unterminated"]  # malformed: kept raw, not dropped


def test_parse_citations_extracts_court_reference_and_topic():
    rows = parse_citations(RECORD["jurisprudenciaCitada"])
    assert [r["reference"] for r in rows] == ["REsp 1816742", "ARE 123456"]
    assert [r["court"] for r in rows] == ["STJ", "STF"]
    assert rows[0]["uf"] == "SP" and rows[1]["uf"] is None
    assert "SOCIEDADE LIMITADA" in rows[0]["topic"]
    assert parse_citations("None") == []


def test_parse_legislation_splits_blocks_and_articles():
    rows = parse_legislation(RECORD["referenciasLegislativas"])
    assert len(rows) == 2
    assert rows[0]["sphere"] == "FED" and rows[0]["kind"] == "LEI"
    assert rows[0]["number"] == "10406" and rows[0]["year"] == "2002"
    assert rows[0]["articles"] == "ART:00966;PAR:00001"
    assert rows[1]["number"] == "13105" and rows[1]["articles"] == "ART:00523"


def test_parse_legislation_keeps_unparsed_entries_with_their_raw_text():
    rows = parse_legislation("['SUM:000007 STJ']")
    assert len(rows) == 1 and rows[0]["sphere"] is None
    assert rows[0]["raw"].startswith("SUM:000007")
    assert rows[0]["articles"] == "SUM:000007"


def test_espelho_row_matches_the_schema_and_hashes_the_rapporteur():
    row = espelho_row(RECORD, orgao_slug="terceira-turma", source_file="20240630.json", salt=SALT)
    assert row is not None and set(row) == set(ESPELHO_SCHEMA)
    assert row["relator_hash"] and "BELLIZZE" not in json.dumps(row, ensure_ascii=False, default=str)
    assert row["data_publicacao"] == dt.date(2024, 6, 19) and row["journal"] == "DJE"
    assert row["n_citations"] == 2 and row["n_legislation"] == 2 and row["n_similar"] == 0
    assert row["tema"] is None and row["classe_padronizada"] is None  # "None" strings normalised
    assert "LITIGÂNCIA PREDATÓRIA" in row["ementa"]


def test_espelho_row_without_identifier_is_dropped():
    assert espelho_row({"ementa": "x"}, orgao_slug="o", source_file="f", salt=SALT) is None


def test_read_espelhos_returns_three_aligned_frames(tmp_path: Path):
    src = tmp_path / "20240630.json"
    src.write_text(json.dumps([RECORD, RECORD], ensure_ascii=False), encoding="utf-8")
    esp, cit, leg = read_espelhos(src, orgao_slug="terceira-turma", salt=SALT)
    assert esp.height == 2 and cit.height == 4 and leg.height == 4
    assert list(esp.columns) == list(ESPELHO_SCHEMA)
    assert list(cit.columns) == list(CITATION_SCHEMA)
    assert list(leg.columns) == list(LEGISLATION_SCHEMA)
    assert set(cit["espelho_id"]) == {"1440321"}


def test_read_espelhos_limit(tmp_path: Path):
    src = tmp_path / "a.json"
    src.write_text(json.dumps([RECORD] * 4, ensure_ascii=False), encoding="utf-8")
    assert read_espelhos(src, orgao_slug="o", salt=SALT, limit=1)[0].height == 1


def test_view_registry_covers_every_pipeline_output():
    assert {"documents", "document_text", "candidates", "candidate_hits", "bridge",
            "espelhos", "espelho_citations", "espelho_legislation"} <= set(VIEW_SOURCES)
    assert all(p.endswith("*.parquet") for p in VIEW_SOURCES.values())


def test_create_views_reports_missing_data_instead_of_failing(tmp_path: Path):
    con, is_file = connect_or_memory(tmp_path / "x.duckdb")
    assert is_file
    counts = create_views(con, tmp_path)
    assert set(counts) == set(VIEW_SOURCES) and all(v is None for v in counts.values())
    con.close()


def test_create_views_builds_a_view_from_parquet(tmp_path: Path):
    import polars as pl

    target = tmp_path / "data" / "interim" / "bridge"
    target.mkdir(parents=True)
    pl.DataFrame({"numero_registro": ["1", "2"]}).write_parquet(target / "acervo.parquet")
    con, _ = connect_or_memory(tmp_path / "db.duckdb")
    counts = create_views(con, tmp_path, ["bridge"])
    assert counts == {"bridge": 2}
    assert con.execute("SELECT count(*) FROM bridge").fetchone()[0] == 2
    con.close()
