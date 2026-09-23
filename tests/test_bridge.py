"""Tests for the record-linkage bridge (alj.bridge).

The privacy tests are the important ones: the sources ship party names, CNPJ and lawyers' OAB numbers, and none
of that may reach a Parquet file before the design-C ethics protocol exists (CLAUDE.md §§4–5).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from alj.bridge import (
    ACERVO_FIELDS,
    ATA_FIELDS,
    BRIDGE_SCHEMA,
    FORBIDDEN_FIELDS,
    bridge_fields,
    hash_name,
    iter_json_records,
    read_bridge,
)

SALT = b"salt-for-tests"

ACERVO_RECORD = {
    "numeroUnico": "00909208520083000000",
    "Data": "2026-09-02",
    "numeroRegistro": "200800909204",
    "siglaClasse": "ExeMS",
    "numeroNaClasse": 4149,
    "codigoClasseCNJ": 1023,
    "processo": "ExeMS 4149",
    "nomeMinistroRelator": "Presidente da Terceira Seção",
    "dataRecebimento": "2008-05-02",
    "codigoOrgaoJulgador": "S3 ",
    "codigoAssuntoCNJ": "10288",
    "assuntoCompleto": "DIREITO ADMINISTRATIVO : Servidor Público Civil",
    "segredoJustica": "NÃO",
    "UF": "DF",
    "dataUltimaDecisao": "2019-09-20",
    "dataUltimaDistribuicao": "2008-05-02",
    "partes": [
        {"descTipoParte": "EXEQUENTE", "nomeParte": "ASSOCIAÇÃO X", "numeroCNPJ": None,
         "advogados": [{"codigoOAB": "DF011997", "nomeAdvogado": "NOME DE ADVOGADO"}]},
    ],
}
ATA_RECORD = {
    "numeroUnico": "10025863420238260000",
    "numeroRegistro": "202301234567",
    "dataHoraDistribuicao": "2023-07-03T14:20:00",
    "descFormaDistribuicao": "SORTEIO",
    "siglaClasse": "AREsp",
    "codigoClasseCNJ": 1209,
    "codigoAssuntoCNJ": "10433",
    "codigoOrgaoJulgador": "T3",
    "partes": [{"nomeParte": "PARTE Y", "advogados": [{"codigoOAB": "SP123456"}]}],
}


def test_allow_lists_exclude_every_personal_field():
    assert not (set(ACERVO_FIELDS) & FORBIDDEN_FIELDS)
    assert not (set(ATA_FIELDS) & FORBIDDEN_FIELDS)
    assert not (set(BRIDGE_SCHEMA) & FORBIDDEN_FIELDS)


def test_acervo_record_projects_to_the_bridge_schema():
    row = bridge_fields(ACERVO_RECORD, source="acervo", source_file="acervo.json.gz", salt=SALT)
    assert row is not None
    assert set(row) == set(BRIDGE_SCHEMA)
    assert row["numero_registro"] == "200800909204"
    assert row["cnj_formatted"] == "0090920-85.2008.3.00.0000"
    assert row["cnj_year"] == 2008 and row["segment"] == "3" and row["tribunal"] == "3.00"
    assert row["codigo_orgao_julgador"] == "S3"  # trailing blank of the source is stripped
    assert row["data_distribuicao"] == "2008-05-02"
    assert row["source"] == "acervo"


def test_party_and_lawyer_data_never_reaches_the_row():
    row = bridge_fields(ACERVO_RECORD, source="acervo", source_file="f", salt=SALT)
    blob = json.dumps(row, ensure_ascii=False)
    assert "ASSOCIAÇÃO X" not in blob
    assert "DF011997" not in blob and "NOME DE ADVOGADO" not in blob


def test_rapporteur_is_only_a_salted_hash():
    row = bridge_fields(ACERVO_RECORD, source="acervo", source_file="f", salt=SALT)
    assert row["relator_hash"] and "Terceira" not in json.dumps(row, ensure_ascii=False)
    assert row["relator_hash"] == hash_name("presidente da terceira seção", SALT)  # case/space-insensitive
    assert hash_name("X", SALT) != hash_name("X", b"other-salt")
    assert hash_name(None, SALT) is None


def test_ata_record_uses_the_distribution_timestamp():
    row = bridge_fields(ATA_RECORD, source="ata", source_file="ata20230703.json", salt=SALT)
    assert row is not None
    assert row["data_distribuicao"] == "2023-07-03T14:20:00"
    assert row["tribunal"] == "8.26" and row["datajud_alias"] == "api_publica_tjsp"
    assert row["source"] == "ata"


def test_unusable_records_are_dropped_not_guessed():
    assert bridge_fields({"numeroUnico": "", "numeroRegistro": "1"}, source="acervo", source_file="f", salt=SALT) is None
    assert bridge_fields({"numeroUnico": "123", "numeroRegistro": "1"}, source="acervo", source_file="f", salt=SALT) is None
    assert bridge_fields({"numeroUnico": "00909208520083000000"}, source="acervo", source_file="f", salt=SALT) is None


def test_check_digit_validity_is_recorded_not_enforced():
    bad = {**ACERVO_RECORD, "numeroUnico": "00909209920083000000"}
    row = bridge_fields(bad, source="acervo", source_file="f", salt=SALT)
    assert row is not None and row["cnj_valid"] is False


def test_iter_json_records_reads_line_per_record_and_pretty_files(tmp_path: Path):
    line_file = tmp_path / "acervo.json.gz"
    with gzip.open(line_file, "wt", encoding="utf-8") as fh:
        fh.write("[\n")
        fh.write(json.dumps(ACERVO_RECORD, ensure_ascii=False) + ",\n")
        fh.write(json.dumps(ATA_RECORD, ensure_ascii=False) + "\n")
        fh.write("]\n")
    assert len(list(iter_json_records(line_file))) == 2

    pretty = tmp_path / "ata.json"
    pretty.write_text(json.dumps([ATA_RECORD, ATA_RECORD], indent=2, ensure_ascii=False), encoding="utf-8")
    assert len(list(iter_json_records(pretty))) == 2


def test_read_bridge_returns_a_typed_frame(tmp_path: Path):
    src = tmp_path / "acervo_processos_tramitando_20260902.json.gz"
    with gzip.open(src, "wt", encoding="utf-8") as fh:
        fh.write("[\n" + json.dumps(ACERVO_RECORD, ensure_ascii=False) + "\n]\n")
    frame = read_bridge(src, source="acervo", salt=SALT)
    assert frame.height == 1
    assert list(frame.columns) == list(BRIDGE_SCHEMA)
    assert frame["source_file"][0] == src.name


def test_read_bridge_respects_limit(tmp_path: Path):
    src = tmp_path / "a.json"
    src.write_text(json.dumps([ACERVO_RECORD] * 5), encoding="utf-8")
    assert read_bridge(src, source="acervo", salt=SALT, limit=2).height == 2


@pytest.mark.parametrize("source", ["acervo", "ata"])
def test_schema_is_stable_across_sources(source: str):
    record = ACERVO_RECORD if source == "acervo" else ATA_RECORD
    row = bridge_fields(record, source=source, source_file="f", salt=SALT)
    assert row is not None and set(row) == set(BRIDGE_SCHEMA)
