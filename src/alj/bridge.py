"""Record-linkage bridge: STJ ``numeroRegistro`` ↔ CNJ ``numeroUnico`` (20 digits) ↔ DataJud.

Two public sources carry the pair (feasibility report §4):

* **acervo em tramitação** — a *snapshot* of the pending caseload (one file, ~77 MB gzipped). Complete for what
  is pending today, thin for older decisions (88–93 % of the decisions published in Aug/2026, 3.5 % of Jun/2025);
* **atas de distribuição** — every case distributed since 2023-06-30, i.e. the historical bridge.

Privacy (CLAUDE.md §§4–5). Both sources ship ``partes`` with party names, CNPJ and lawyers' OAB numbers. This
module **never reads that key**: :func:`bridge_fields` builds the row from an explicit allow-list, so a new field
in the source cannot leak in, and ``nomeMinistroRelator`` is kept only as a salted hash, exactly as in step 10.
The design-C actor layer stays out until the researcher approves its ethics protocol.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import polars as pl

from .cnj import parse_cnj

#: the only keys read from the sources — everything else (notably ``partes``) is dropped by construction
ACERVO_FIELDS: tuple[str, ...] = (
    "numeroUnico",
    "numeroRegistro",
    "Data",
    "siglaClasse",
    "codigoClasseCNJ",
    "numeroNaClasse",
    "processo",
    "dataRecebimento",
    "codigoOrgaoJulgador",
    "codigoAssuntoCNJ",
    "listaAssuntos",
    "segredoJustica",
    "pedidoDeLiminar",
    "sobrestado",
    "localProcesso",
    "origem",
    "UF",
    "dataUltimaDecisao",
    "dataPublicacao",
    "dataUltimaDistribuicao",
)
ATA_FIELDS: tuple[str, ...] = (
    "numeroUnico",
    "numeroRegistro",
    "dataHoraDistribuicao",
    "descFormaDistribuicao",
    "codigoClasse",
    "siglaClasse",
    "codigoClasseCNJ",
    "numeroNaClasse",
    "codigoDestino",
    "descDestino",
    "codigoOrgaoJulgador",
    "codigoAssuntoCNJ",
)
#: never ingested, in any form, before the design-C ethics protocol is approved
FORBIDDEN_FIELDS: frozenset[str] = frozenset({"partes", "advogados", "nomeParte", "numeroCNPJ", "codigoOAB", "nomeAdvogado"})

BRIDGE_SCHEMA = {
    "numero_registro": pl.Utf8,
    "numero_unico": pl.Utf8,
    "cnj_digits": pl.Utf8,
    "cnj_formatted": pl.Utf8,
    "cnj_valid": pl.Boolean,
    "cnj_year": pl.Int32,
    "segment": pl.Utf8,
    "tribunal": pl.Utf8,
    "origin_unit": pl.Utf8,
    "datajud_alias": pl.Utf8,
    "sigla_classe": pl.Utf8,
    "codigo_classe_cnj": pl.Utf8,
    "codigo_assunto_cnj": pl.Utf8,
    "codigo_orgao_julgador": pl.Utf8,
    "uf": pl.Utf8,
    "data_distribuicao": pl.Utf8,
    "data_recebimento": pl.Utf8,
    "data_ultima_decisao": pl.Utf8,
    "relator_hash": pl.Utf8,
    "source": pl.Utf8,
    "source_file": pl.Utf8,
}


def hash_name(value: str | None, salt: bytes) -> str | None:
    if not value:
        return None
    return hashlib.sha256(salt + value.strip().upper().encode("utf-8")).hexdigest()[:32]


def iter_json_records(path: str | Path, chunk_size: int = 1 << 20) -> Iterator[dict]:
    """Stream the objects of a (possibly gzipped) JSON file without loading it whole.

    The STJ publishes these sets in several layouts — one object per line, pretty-printed, or the whole array on
    a single line — so the objects are decoded incrementally with :meth:`json.JSONDecoder.raw_decode` instead of
    assuming any of them. A file holding a single object works too. Malformed tails stop the iteration silently;
    the caller reports the row count, which is what the log compares against the source.
    """
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    decoder = json.JSONDecoder()
    buffer = ""
    with opener(path, "rt", encoding="utf-8") as fh:  # type: ignore[operator]
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            buffer += chunk
            index = 0
            while True:
                while index < len(buffer) and buffer[index] in " \t\r\n,[]":
                    index += 1
                if index >= len(buffer):
                    break
                try:
                    obj, index = decoder.raw_decode(buffer, index)
                except json.JSONDecodeError:
                    break  # incomplete record: wait for the next chunk
                if isinstance(obj, dict):
                    yield obj
                elif isinstance(obj, list):
                    yield from (r for r in obj if isinstance(r, dict))
            buffer = buffer[index:]


def bridge_fields(record: dict, *, source: str, source_file: str, salt: bytes) -> dict | None:
    """Project one source record onto :data:`BRIDGE_SCHEMA`. Returns ``None`` when the pair is unusable."""
    allowed = ACERVO_FIELDS if source == "acervo" else ATA_FIELDS
    row = {k: record.get(k) for k in allowed}
    numero_unico = str(row.get("numeroUnico") or "").strip()
    numero_registro = str(row.get("numeroRegistro") or "").strip()
    if not numero_unico or not numero_registro:
        return None
    try:
        cnj = parse_cnj(numero_unico)
    except ValueError:
        return None
    distribution = row.get("dataUltimaDistribuicao") or row.get("dataHoraDistribuicao")
    return {
        "numero_registro": numero_registro,
        "numero_unico": numero_unico,
        "cnj_digits": cnj.digits,
        "cnj_formatted": cnj.formatted,
        "cnj_valid": cnj.check_digits_valid(),
        "cnj_year": cnj.year,
        "segment": cnj.segment,
        "tribunal": f"{cnj.segment}.{cnj.tribunal}",
        "origin_unit": cnj.origin,
        "datajud_alias": cnj.datajud_alias,
        "sigla_classe": row.get("siglaClasse"),
        "codigo_classe_cnj": None if row.get("codigoClasseCNJ") is None else str(row["codigoClasseCNJ"]),
        "codigo_assunto_cnj": None if row.get("codigoAssuntoCNJ") is None else str(row["codigoAssuntoCNJ"]),
        "codigo_orgao_julgador": (row.get("codigoOrgaoJulgador") or "").strip() or None,
        "uf": row.get("UF"),
        "data_distribuicao": None if distribution is None else str(distribution),
        "data_recebimento": None if row.get("dataRecebimento") is None else str(row["dataRecebimento"]),
        "data_ultima_decisao": None if row.get("dataUltimaDecisao") is None else str(row["dataUltimaDecisao"]),
        "relator_hash": hash_name(record.get("nomeMinistroRelator"), salt),
        "source": source,
        "source_file": source_file,
    }


def read_bridge(path: str | Path, *, source: str, salt: bytes, limit: int | None = None) -> pl.DataFrame:
    """Read one acervo snapshot or one ata into a :data:`BRIDGE_SCHEMA` frame (bridge fields only)."""
    path = Path(path)
    rows: list[dict] = []
    for n, record in enumerate(iter_json_records(path)):
        if limit is not None and n >= limit:
            break
        row = bridge_fields(record, source=source, source_file=path.name, salt=salt)
        if row is not None:
            rows.append(row)
    frame = pl.DataFrame(rows, schema=BRIDGE_SCHEMA) if rows else pl.DataFrame(schema=BRIDGE_SCHEMA)
    assert not (set(frame.columns) & FORBIDDEN_FIELDS)
    return frame
