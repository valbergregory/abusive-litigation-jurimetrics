"""Tests for the DataJud trajectory reader (step 30). No network: the API shape is fixed in a sample."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import polars as pl
import pytest

from alj.datajud import (
    CASE_FIELDS,
    CASE_SCHEMA,
    FORBIDDEN_FIELDS,
    MOVEMENT_SCHEMA,
    batched,
    case_row,
    frames,
    iter_sources,
    movement_rows,
    parse_iso,
    parse_public_key,
    terms_body,
    total_hits,
    unexpected_fields,
)

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "raw" / "datajud" / "sample_api_publica_stj.json"

# One document in the published shape (fields as measured by scripts/01_probe_datajud.py), with the movements
# deliberately out of chronological order and one of them without a timestamp.
DOC = {
    "id": "STJ_SUP_02721312420263000000",
    "numeroProcesso": "02721312420263000000",
    "tribunal": "STJ",
    "grau": "SUP",
    "dataAjuizamento": "20260702000000",
    "nivelSigilo": 0,
    "classe": {"codigo": 1030, "nome": "Reclamação"},
    "assuntos": [{"codigo": 7779, "nome": "Indenização por Dano Moral"}, {"codigo": 10431, "nome": "Dano Material"}],
    "orgaoJulgador": {"codigo": 76789, "nome": "PRESIDÊNCIA", "codigoMunicipioIBGE": 5300108},
    "sistema": {"codigo": -1, "nome": "Inválido"},
    "formato": {"codigo": 1, "nome": "Eletrônico"},
    "dataHoraUltimaAtualizacao": "2026-08-20T22:45:02.433000Z",
    "movimentos": [
        {"codigo": 123, "nome": "Conclusão", "dataHora": "2026-07-10T09:00:00.000Z"},
        {
            "codigo": 581,
            "nome": "Documento",
            "dataHora": "2026-07-02T14:55:29.000Z",
            "complementosTabelados": [{"codigo": 4, "descricao": "tipo_de_documento", "valor": 107, "nome": "Certidão"}],
            "orgaoJulgador": {"codigo": "33544", "nome": "SECRETARIA JUDICIÁRIA - SJD"},
        },
        {"codigo": 999, "nome": "Movimento sem data"},
    ],
}


def test_parse_public_key_reads_the_wiki_page():
    page = "<h2>Chave</h2><p>Authorization: <code>APIKey Y2hhdmUtZmFsc2EtZGUtdGVzdGU9PQ==</code></p>"
    assert parse_public_key(page) == "Y2hhdmUtZmFsc2EtZGUtdGVzdGU9PQ=="


def test_parse_public_key_fails_loudly_when_the_page_changes():
    with pytest.raises(ValueError):
        parse_public_key("<p>a página mudou e não traz mais a chave</p>")


def test_parse_iso():
    assert parse_iso("2026-07-02T14:55:29.000Z") == dt.datetime(2026, 7, 2, 14, 55, 29)
    assert parse_iso("2026-07-02 14:55:29") == dt.datetime(2026, 7, 2, 14, 55, 29)
    assert parse_iso(None) is None
    assert parse_iso("02/07/2026") is None
    assert parse_iso("2026-02-30T00:00:00Z") is None  # impossible date, not an exception


def test_batched_covers_every_item_once():
    items = [str(n) for n in range(250)]
    chunks = list(batched(items, 100))
    assert [len(c) for c in chunks] == [100, 100, 50]
    assert [x for c in chunks for x in c] == items
    with pytest.raises(ValueError):
        list(batched(items, 0))


def test_terms_body_asks_only_for_the_allow_listed_fields():
    body = terms_body(["1", "2"], size=500)
    assert body["query"]["terms"]["numeroProcesso"] == ["1", "2"]
    assert body["size"] == 500
    assert body["_source"] == list(CASE_FIELDS)


def test_total_hits_handles_both_shapes():
    assert total_hits({"hits": {"total": {"value": 7, "relation": "eq"}}}) == 7
    assert total_hits({"hits": {"total": 7}}) == 7
    assert total_hits({}) == 0


def test_iter_sources_keeps_the_elasticsearch_id_when_the_source_has_none():
    payload = {"hits": {"hits": [{"_id": "abc", "_source": {"numeroProcesso": "1"}}, {"_id": "d"}]}}
    assert [s["id"] for s in iter_sources(payload)] == ["abc"]


def test_case_row_projects_the_measured_fields():
    row = case_row(DOC, alias="api_publica_stj")
    assert set(row) == set(CASE_SCHEMA)
    assert row["numero_processo"] == "02721312420263000000"
    assert row["data_ajuizamento"] == dt.datetime(2026, 7, 2)
    assert row["classe_codigo"] == "1030" and row["classe_nome"] == "Reclamação"
    assert row["municipio_ibge"] == 5300108
    assert row["assuntos_codigos"] == "7779;10431"
    assert row["n_movimentos"] == 3
    # the window comes from the movements, so it is independent of the server's date parsing
    assert row["primeiro_movimento"] == dt.datetime(2026, 7, 2, 14, 55, 29)
    assert row["ultimo_movimento"] == dt.datetime(2026, 7, 10, 9, 0, 0)


def test_case_row_survives_an_empty_document():
    row = case_row({}, alias="api_publica_tjsp")
    assert row["numero_processo"] is None and row["n_movimentos"] == 0
    assert row["primeiro_movimento"] is None and row["ultimo_movimento"] is None


def test_movement_rows_are_ordered_by_timestamp_and_undated_ones_come_last():
    rows = movement_rows(DOC, alias="api_publica_stj")
    assert [r["ordem"] for r in rows] == [1, 2, 3]
    assert [r["codigo"] for r in rows] == [581, 123, 999]
    assert rows[2]["data_hora"] is None
    assert rows[0]["complementos"] == "4:107"
    assert rows[0]["orgao_codigo"] == "33544"
    assert set(rows[0]) == set(MOVEMENT_SCHEMA)


def test_unexpected_fields_reports_a_new_key_at_the_source():
    assert unexpected_fields(DOC) == []
    assert unexpected_fields({**DOC, "partes": [{"nome": "X"}]}) == ["partes"]
    # @timestamp is Elasticsearch bookkeeping that the probe sample carries: known, not ingested, not reported
    assert unexpected_fields({**DOC, "@timestamp": "2026-08-20T22:45:02.433000Z"}) == []


def test_frames_have_the_schemas_and_no_forbidden_column():
    cases, movements = frames([DOC, DOC], alias="api_publica_stj")
    assert cases.height == 2 and movements.height == 6
    assert cases.schema == pl.Schema(CASE_SCHEMA) and movements.schema == pl.Schema(MOVEMENT_SCHEMA)
    assert not (set(cases.columns) & FORBIDDEN_FIELDS)
    assert not (set(movements.columns) & FORBIDDEN_FIELDS)


def test_frames_of_nothing_keep_the_schema():
    cases, movements = frames([], alias="api_publica_stj")
    assert cases.height == 0 and movements.height == 0
    assert cases.schema == pl.Schema(CASE_SCHEMA) and movements.schema == pl.Schema(MOVEMENT_SCHEMA)


@pytest.mark.skipif(not SAMPLE.exists(), reason="probe sample absent (data/ is git-ignored)")
def test_the_real_probe_sample_projects_without_surprises():
    payload = json.loads(SAMPLE.read_text(encoding="utf-8"))
    sources = list(iter_sources(payload))
    assert sources, "the probe sample should carry at least one document"
    for source in sources:
        assert unexpected_fields(source) == [], "the API grew a field: check it before ingesting"
        assert not (set(source) & FORBIDDEN_FIELDS)
        assert case_row(source, alias="api_publica_stj")["numero_processo"]


def test_the_trajectory_views_are_registered_in_the_database_registry():
    # step 31 and the manuscript export read these by name; a missing entry would silently produce empty tables
    from alj.db import VIEW_SOURCES

    assert {"datajud_targets", "datajud_cases", "datajud_movimentos", "datajud_features"} <= set(VIEW_SOURCES)
    assert all(VIEW_SOURCES[v].endswith("*.parquet")
               for v in ("datajud_targets", "datajud_cases", "datajud_movimentos", "datajud_features"))
