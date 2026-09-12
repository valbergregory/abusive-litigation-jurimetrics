"""Schema-drift and privacy tests for alj.stj_integras (tiny synthetic fixtures; no network, no real names)."""

import datetime as dt
import json
import zipfile

from alj.stj_integras import (
    file_sha256,
    hash_name,
    key_of,
    parse_assuntos_leaf,
    parse_date,
    read_metadata,
    read_texts,
)

SALT = b"test-salt"


def test_key_of():
    assert key_of("textos20230614.zip") == "20230614"
    assert key_of("metadados202202.json") == "202202"
    assert key_of("D:/x/metadados20210615.json") == "20210615"
    assert key_of("CHECKSUMS.sha256") is None


def test_parse_date_iso_and_epoch():
    assert parse_date("2021-06-15") == dt.date(2021, 6, 15)
    assert parse_date("1686711600000") == dt.date(2023, 6, 14)  # 2023-06-14 00:00 Brasília
    assert parse_date(1686711600000) == dt.date(2023, 6, 14)
    assert parse_date("None") is None and parse_date("") is None and parse_date(None) is None


def test_parse_assuntos_leaf_three_formats():
    assert parse_assuntos_leaf("00899.07681.09580.09596., 00899.07681.07") == "9596;7"
    assert parse_assuntos_leaf("10254;10225;10254;10225") == "10254;10225"
    assert parse_assuntos_leaf("6100, 9148, 6120") == "6100;9148;6120"
    assert parse_assuntos_leaf("4949") == "4949"
    assert parse_assuntos_leaf("None") is None


def test_hash_name_is_salted_and_accent_insensitive():
    a = hash_name("Luis Felipe Salomão", SALT)
    assert a == hash_name("LUIS FELIPE SALOMAO", SALT)
    assert a != hash_name("Luis Felipe Salomão", b"other")
    assert len(a) == 24 and hash_name("None", SALT) is None


def test_read_metadata_normalises_2021_and_2023_layouts(tmp_path):
    rows_2021 = [
        {"SeqDocumento": "128903817", "dataPublicacao": "2021-06-15", "tipoDocumento": "DECISAO", "numeroRegistro": "202100188478",
         "processo": "AREsp 1826238", "dataRecebimento": "2021-01-28", "dataDistribuicao": "2021-02-24", "NM_MINISTRO": "FULANO",
         "recurso": "RtPaut", "teor": "Negando", "descricaoMonocratica": "Indeferido o pedido de #{nome_da_parte}",
         "assuntos": "00899.07681.09580.09596., 00899.07681.07"},
    ]
    rows_2023 = [
        {"seqDocumento": "193464522", "dataPublicacao": "1686711600000", "tipoDocumento": "ACÓRDÃO", "numeroRegistro": "202202636851",
         "processo": "HC 765766     ", "dataRecebimento": "1661137200000", "dataDistribuição": "1661223600000", "ministro": "BELTRANO",
         "recurso": "AGRAVO REGIMENTAL", "teor": "Negando", "descricaoMonocratica": "None", "assuntos": "3372;3372;14689;3372"},
    ]
    p1 = tmp_path / "metadados20210615.json"
    p1.write_text(json.dumps(rows_2021), encoding="utf-8")
    p2 = tmp_path / "metadados20230614.json"
    p2.write_text(json.dumps(rows_2023), encoding="utf-8")
    a = read_metadata(p1, SALT)
    b = read_metadata(p2, SALT)
    assert a.columns == b.columns
    ra, rb = a.row(0, named=True), b.row(0, named=True)
    assert ra["seq_documento"] == 128903817 and ra["key"] == "20210615" and ra["classe"] == "AREsp"
    assert ra["assuntos_leaf"] == "9596;7" and ra["tipo_documento"] == "DECISAO"
    assert rb["seq_documento"] == 193464522 and rb["tipo_documento"] == "ACORDAO" and rb["classe"] == "HC"
    assert rb["data_publicacao"] == dt.date(2023, 6, 14) and rb["data_distribuicao"] == dt.date(2022, 8, 23)
    assert rb["descricao_monocratica"] is None and rb["assuntos_leaf"] == "3372;14689"
    # privacy: the name never appears in the frame
    for frame in (a, b):
        assert "ministro" not in frame.columns
        assert not any("FULANO" in str(v) or "BELTRANO" in str(v) for v in frame.row(0))


def test_read_texts_handles_folder_prefix_and_br(tmp_path):
    zp = tmp_path / "textos20230614.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("20230614/193464522.txt", "linha 1<br/>linha 2\r\n")
        z.writestr("193464523.txt", "só um")
        z.writestr("20230614/", "")
    df = read_texts(zp)
    assert df.height == 2 and df["key"].to_list() == ["20230614", "20230614"]
    r = df.filter(df["seq_documento"] == 193464522).row(0, named=True)
    assert r["text"] == "linha 1\nlinha 2\n" and r["nchar"] == len(r["text"]) and len(r["text_sha256"]) == 64
    assert file_sha256(zp) == file_sha256(zp)


def test_read_texts_bad_zip_returns_empty(tmp_path):
    zp = tmp_path / "textos20260126.zip"
    zp.write_bytes(b"PK\x03\x04" + b"\x00" * 64)  # local header only, no central directory
    df = read_texts(zp)
    assert df.height == 0 and "text" in df.columns
