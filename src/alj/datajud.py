"""DataJud public API (CNJ): procedural trajectories for the bridged cases (design B).

The bridge gives, for each STJ decision, the CNJ unified number of the case (``numero_unico``) and the public
endpoint of the court it came from (``datajud_alias``). This module turns that into the *trajectory*: the case's
class, subject codes, judging body and the full list of ``movimentos`` (code, name, timestamp), which is what
RQ3 and RQ4 need — how a signalled case moves, not only how it is described.

Three rules of the repository are implemented here, not left to the caller:

* **the key is read at runtime** (CLAUDE.md §8): :func:`parse_public_key` extracts it from the CNJ wiki page, so
  a rotated key does not silently break the run and no key is committed;
* **dates are parsed client-side** (§8): ``dataAjuizamento`` is a 14-digit string that the server parses as epoch
  milliseconds for large result sets, yielding years such as 2571 — :func:`alj.cnj.parse_datajud_datetime` does it;
* **fields come from an allow-list** (§§4–5): :func:`case_row` and :func:`movement_rows` build their rows from
  explicit keys. The public API carries no party or lawyer field today; :func:`unexpected_fields` reports any new
  top-level key so that a change at the source is noticed instead of ingested.

The queries are ``terms`` queries on ``numeroProcesso``: one request resolves a batch of cases, and a batch whose
result would overflow ``size`` is split instead of paginated (:func:`terms_body`), which keeps the collection
deterministic and free of cursor state.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable, Iterator, Sequence
from typing import Any, TypeVar

import polars as pl

from .cnj import parse_datajud_datetime

WIKI_URL = "https://datajud-wiki.cnj.jus.br/api-publica/acesso/"
SEARCH_URL = "https://api-publica.datajud.cnj.jus.br/{alias}/_search"

_T = TypeVar("_T")
LICENCE = "Dados Abertos CNJ / DataJud (Res. CNJ 331/2020, alterada pela Res. 437/2021)"

#: the only keys read from each ``_source``; a new field at the source is reported, never ingested
CASE_FIELDS: tuple[str, ...] = (
    "id",
    "numeroProcesso",
    "tribunal",
    "grau",
    "dataAjuizamento",
    "nivelSigilo",
    "classe",
    "assuntos",
    "orgaoJulgador",
    "sistema",
    "formato",
    "dataHoraUltimaAtualizacao",
    "movimentos",
)
#: never ingested, in any form (CLAUDE.md §§4–5); the public API does not publish them, and this asserts it
FORBIDDEN_FIELDS: frozenset[str] = frozenset(
    {"partes", "poloAtivo", "poloPassivo", "advogados", "nomeParte", "numeroDocumento", "numeroCNPJ", "codigoOAB"}
)
#: known Elasticsearch bookkeeping, deliberately not ingested: ``@timestamp`` repeats
#: ``dataHoraUltimaAtualizacao`` and says when the index was written, not when the case moved
IGNORED_FIELDS: frozenset[str] = frozenset({"@timestamp"})

CASE_SCHEMA = {
    "alias": pl.Utf8,
    "numero_processo": pl.Utf8,
    "tribunal": pl.Utf8,
    "grau": pl.Utf8,
    "es_id": pl.Utf8,
    "data_ajuizamento": pl.Datetime("us"),
    "nivel_sigilo": pl.Int32,
    "classe_codigo": pl.Utf8,
    "classe_nome": pl.Utf8,
    "orgao_codigo": pl.Utf8,
    "orgao_nome": pl.Utf8,
    "municipio_ibge": pl.Int32,
    "sistema_nome": pl.Utf8,
    "formato_nome": pl.Utf8,
    "assuntos_codigos": pl.Utf8,
    "assuntos_nomes": pl.Utf8,
    "n_movimentos": pl.Int32,
    "primeiro_movimento": pl.Datetime("us"),
    "ultimo_movimento": pl.Datetime("us"),
    "atualizado_em": pl.Datetime("us"),
}
MOVEMENT_SCHEMA = {
    "alias": pl.Utf8,
    "numero_processo": pl.Utf8,
    "grau": pl.Utf8,
    "es_id": pl.Utf8,
    "ordem": pl.Int32,
    "codigo": pl.Int32,
    "nome": pl.Utf8,
    "data_hora": pl.Datetime("us"),
    "orgao_codigo": pl.Utf8,
    "complementos": pl.Utf8,
}
TARGET_SCHEMA = {
    "numero_processo": pl.Utf8,
    "alias": pl.Utf8,
    "grupo": pl.Utf8,  # 'candidato' | 'comparacao_nao_sinalizado' (CLAUDE.md §3: never 'legitimate')
    "pub_year": pl.Utf8,
    "strict_hit": pl.Boolean,
    "n_documentos": pl.Int32,
}

_KEY = re.compile(r"APIKey\s+([A-Za-z0-9+/=]{30,})")
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})")


def parse_public_key(page: str) -> str:
    """The public API key as published on the CNJ wiki page. Raises ``ValueError`` when the page changed."""
    text = html.unescape(re.sub("<[^>]+>", " ", page))
    match = _KEY.search(text)
    if not match:
        raise ValueError(f"public API key not found on the wiki page; check {WIKI_URL}")
    return match.group(1)


def parse_iso(value: str | None):
    """``2026-07-02T14:55:29.000Z`` → datetime (no timezone conversion: the API publishes UTC)."""
    if not value:
        return None
    match = _ISO.match(str(value))
    if not match:
        return None
    from datetime import datetime

    y, mo, d, h, mi, s = (int(x) for x in match.groups())
    try:
        return datetime(y, mo, d, h, mi, s)
    except ValueError:
        return None


def batched(items: Sequence[_T], size: int) -> Iterator[list[_T]]:
    """Successive lists of at most ``size`` items (used both for case numbers and for waves of requests)."""
    if size < 1:
        raise ValueError("size must be >= 1")
    for start in range(0, len(items), size):
        yield list(items[start : start + size])


def terms_body(numbers: Sequence[str], *, size: int = 1000) -> dict[str, Any]:
    """Elasticsearch body resolving a batch of case numbers in one request.

    ``size`` must exceed the number of documents the batch can return (a case has one document per ``grau``);
    the caller compares it against ``hits.total.value`` and splits the batch when it does not, which is why no
    cursor is needed.
    """
    return {
        "size": size,
        "query": {"terms": {"numeroProcesso": list(numbers)}},
        "_source": list(CASE_FIELDS),
    }


def total_hits(payload: dict) -> int:
    total = (payload.get("hits") or {}).get("total")
    if isinstance(total, dict):
        return int(total.get("value") or 0)
    return int(total or 0)


def iter_sources(payload: dict) -> Iterator[dict]:
    for hit in (payload.get("hits") or {}).get("hits") or []:
        source = hit.get("_source")
        if isinstance(source, dict):
            yield {**source, "id": source.get("id") or hit.get("_id")}


def unexpected_fields(source: dict) -> list[str]:
    """Top-level keys the source grew since :data:`CASE_FIELDS` was written (reported in the step's log)."""
    return sorted(set(source) - set(CASE_FIELDS) - IGNORED_FIELDS)


def _code(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value).strip() or None


def case_row(source: dict, *, alias: str) -> dict:
    """One :data:`CASE_SCHEMA` row from one ``_source`` (allow-listed keys only)."""
    movements = [m for m in (source.get("movimentos") or []) if isinstance(m, dict)]
    stamps = sorted(x for x in (parse_iso(m.get("dataHora")) for m in movements) if x is not None)
    classe = source.get("classe") or {}
    orgao = source.get("orgaoJulgador") or {}
    assuntos = [a for a in (source.get("assuntos") or []) if isinstance(a, dict)]
    municipio = orgao.get("codigoMunicipioIBGE")
    return {
        "alias": alias,
        "numero_processo": _code(source.get("numeroProcesso")),
        "tribunal": _code(source.get("tribunal")),
        "grau": _code(source.get("grau")),
        "es_id": _code(source.get("id")),
        "data_ajuizamento": parse_datajud_datetime(source.get("dataAjuizamento")),
        "nivel_sigilo": None if source.get("nivelSigilo") is None else int(source["nivelSigilo"]),
        "classe_codigo": _code(classe.get("codigo")),
        "classe_nome": classe.get("nome"),
        "orgao_codigo": _code(orgao.get("codigo")),
        "orgao_nome": orgao.get("nome"),
        "municipio_ibge": None if municipio in (None, "") else int(municipio),
        "sistema_nome": (source.get("sistema") or {}).get("nome"),
        "formato_nome": (source.get("formato") or {}).get("nome"),
        "assuntos_codigos": ";".join(x for x in (_code(a.get("codigo")) for a in assuntos) if x) or None,
        "assuntos_nomes": "|".join(a["nome"] for a in assuntos if a.get("nome")) or None,
        "n_movimentos": len(movements),
        "primeiro_movimento": stamps[0] if stamps else None,
        "ultimo_movimento": stamps[-1] if stamps else None,
        "atualizado_em": parse_iso(source.get("dataHoraUltimaAtualizacao")),
    }


def movement_rows(source: dict, *, alias: str) -> list[dict]:
    """The trajectory itself: one :data:`MOVEMENT_SCHEMA` row per movement, ordered by timestamp.

    ``ordem`` is assigned after sorting by ``dataHora``, because the API returns the array in insertion order,
    which is not always chronological. Movements without a timestamp keep the source order at the end.
    """
    movements = [m for m in (source.get("movimentos") or []) if isinstance(m, dict)]
    decorated = [(parse_iso(m.get("dataHora")), n, m) for n, m in enumerate(movements)]
    decorated.sort(key=lambda t: (t[0] is None, t[0], t[1]))
    rows = []
    for ordem, (stamp, _n, movement) in enumerate(decorated, 1):
        complements = [c for c in (movement.get("complementosTabelados") or []) if isinstance(c, dict)]
        code = movement.get("codigo")
        rows.append({
            "alias": alias,
            "numero_processo": _code(source.get("numeroProcesso")),
            "grau": _code(source.get("grau")),
            "es_id": _code(source.get("id")),
            "ordem": ordem,
            "codigo": None if code is None else int(code),
            "nome": movement.get("nome"),
            "data_hora": stamp,
            "orgao_codigo": _code((movement.get("orgaoJulgador") or {}).get("codigo")),
            "complementos": ";".join(
                f"{_code(c.get('codigo'))}:{_code(c.get('valor'))}" for c in complements
            ) or None,
        })
    return rows


def frames(sources: Iterable[dict], *, alias: str) -> tuple[pl.DataFrame, pl.DataFrame]:
    """``(cases, movimentos)`` frames for a batch of ``_source`` documents."""
    cases: list[dict] = []
    movements: list[dict] = []
    for source in sources:
        cases.append(case_row(source, alias=alias))
        movements.extend(movement_rows(source, alias=alias))
    case_frame = pl.DataFrame(cases, schema=CASE_SCHEMA) if cases else pl.DataFrame(schema=CASE_SCHEMA)
    move_frame = (
        pl.DataFrame(movements, schema=MOVEMENT_SCHEMA) if movements else pl.DataFrame(schema=MOVEMENT_SCHEMA)
    )
    assert not (set(case_frame.columns) & FORBIDDEN_FIELDS)
    assert not (set(move_frame.columns) & FORBIDDEN_FIELDS)
    return case_frame, move_frame
