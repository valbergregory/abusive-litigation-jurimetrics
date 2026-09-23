"""Readers for the STJ open-data sets *Espelhos de acórdãos* (one CKAN dataset per judging body).

An *espelho* is the structured record of a published acórdão: ementa, decision text, cited case law, legislative
references, the repetitive theme and the legal thesis. It complements the *íntegras* in three ways the article
needs: it is the only source with **citations** and **legislative references** as fields, it covers the collegiate
decisions from 2022-05 onwards, and its ementa headers often carry the phenomenon in the first line
("LITIGÂNCIA PREDATÓRIA. IRREGULARIDADE DE REPRESENTAÇÃO…", phase 0 §3).

Quirks of the published data, all handled here:

* absent values arrive as the **string** ``"None"``, not as JSON null;
* ``dataPublicacao`` is ``"DJE        DATA:19/06/2024"`` (the journal acronym plus the date);
* ``dataDecisao`` is ``"yyyyMMdd"``;
* ``referenciasLegislativas`` and ``acordaosSimilares`` are **Python reprs** of lists inside a JSON string;
* ``jurisprudenciaCitada`` is free text where each citation is wrapped in ``<<…>>`` and preceded by the court.

Privacy: ``ministroRelator`` is kept only as a salted hash, as in the íntegras (CLAUDE.md §4).
"""

from __future__ import annotations

import ast
import datetime as dt
import hashlib
import io
import json
import re
import zipfile
from collections.abc import Iterable, Iterator
from pathlib import Path

import polars as pl

from .bridge import iter_json_records

NONEISH = {"", "none", "null", "nan", "-"}

ESPELHO_SCHEMA = {
    "espelho_id": pl.Utf8,
    "orgao_slug": pl.Utf8,
    "numero_registro": pl.Utf8,
    "numero_processo": pl.Utf8,
    "numero_documento": pl.Utf8,
    "sigla_classe": pl.Utf8,
    "descricao_classe": pl.Utf8,
    "classe_padronizada": pl.Utf8,
    "orgao_julgador": pl.Utf8,
    "relator_hash": pl.Utf8,
    "tipo_decisao": pl.Utf8,
    "journal": pl.Utf8,
    "data_publicacao": pl.Date,
    "data_decisao": pl.Date,
    "tema": pl.Utf8,
    "tese_juridica": pl.Utf8,
    "ementa": pl.Utf8,
    "decisao": pl.Utf8,
    "notas": pl.Utf8,
    "informacoes_complementares": pl.Utf8,
    "termos_auxiliares": pl.Utf8,
    "n_citations": pl.Int32,
    "n_legislation": pl.Int32,
    "n_similar": pl.Int32,
    "source_file": pl.Utf8,
}
CITATION_SCHEMA = {
    "espelho_id": pl.Utf8,
    "orgao_slug": pl.Utf8,
    "numero_registro": pl.Utf8,
    "court": pl.Utf8,
    "reference": pl.Utf8,
    "uf": pl.Utf8,
    "topic": pl.Utf8,
}
LEGISLATION_SCHEMA = {
    "espelho_id": pl.Utf8,
    "orgao_slug": pl.Utf8,
    "numero_registro": pl.Utf8,
    "sphere": pl.Utf8,
    "kind": pl.Utf8,
    "number": pl.Utf8,
    "year": pl.Utf8,
    "articles": pl.Utf8,
    "raw": pl.Utf8,
}

_CITATION = re.compile(r"<<\s*(?P<ref>[^>]+?)\s*>>\s*(?:-\s*(?P<uf>[A-Z]{2})\b)?")
_COURT = re.compile(r"\b(STJ|STF|TST|TSE|STM|TRF\s*-?\s*\d|TJ[A-Z]{2}|TRT\s*-?\s*\d+)\b")
_TOPIC = re.compile(r"\(([^()]{8,300})\)")
_LEG_HEAD = re.compile(
    r"LEG:\s*(?P<sphere>\w+)\s+(?P<kind>[A-Z\-]+):\s*(?P<number>[\d.]+)(?:\s+ANO:\s*(?P<year>\d{4}))?", re.I
)
_LEG_ITEMS = re.compile(r"\b(?:ART|PAR|INC|LET|SUM|ALI):\s*[\w.]+", re.I)


def clean(value: object) -> str | None:
    """Normalise the published placeholders (``"None"``, ``""``, ``"-"``) to ``None`` and strip whitespace."""
    if value is None:
        return None
    text = str(value).strip()
    return None if text.lower() in NONEISH else text


def hash_name(value: str | None, salt: bytes) -> str | None:
    if not value:
        return None
    return hashlib.sha256(salt + value.strip().upper().encode("utf-8")).hexdigest()[:32]


def parse_publication(value: object) -> tuple[str | None, dt.date | None]:
    """``"DJE        DATA:19/06/2024"`` → ``("DJE", date(2024, 6, 19))``."""
    text = clean(value)
    if not text:
        return None, None
    journal = text.split()[0] if text.split() else None
    match = re.search(r"DATA:\s*(\d{2})/(\d{2})/(\d{4})", text)
    if not match:
        return journal, None
    day, month, year = (int(g) for g in match.groups())
    try:
        return journal, dt.date(year, month, day)
    except ValueError:
        return journal, None


def parse_compact_date(value: object) -> dt.date | None:
    """``"20240617"`` → ``date(2024, 6, 17)``; anything else → ``None``."""
    text = clean(value)
    if not text or not re.fullmatch(r"\d{8}", text):
        return None
    try:
        return dt.date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        return None


def parse_repr_list(value: object) -> list[str]:
    """The published fields hold a Python repr of a list inside the JSON string."""
    text = clean(value)
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return [text]
        if isinstance(parsed, (list, tuple)):
            return [str(x) for x in parsed if clean(x)]
        return [str(parsed)]
    return [text]


def parse_citations(value: object) -> list[dict[str, str | None]]:
    """Extract one row per ``<<…>>`` citation, with the court that introduces it and the topic in brackets."""
    text = clean(value)
    if not text:
        return []
    out: list[dict[str, str | None]] = []
    for match in _CITATION.finditer(text):
        before = text[: match.start()]
        courts = _COURT.findall(before)
        topics = _TOPIC.findall(before)
        out.append(
            {
                "court": re.sub(r"\s+", "", courts[-1]) if courts else None,
                "reference": re.sub(r"\s+", " ", match.group("ref")).strip(),
                "uf": match.group("uf"),
                "topic": re.sub(r"\s+", " ", topics[-1]).strip() if topics else None,
            }
        )
    return out


def parse_legislation(value: object) -> list[dict[str, str | None]]:
    """Split the ``LEG:FED LEI:010406 ANO:2002 … ART:00966 …`` blocks into structured rows."""
    rows: list[dict[str, str | None]] = []
    for entry in parse_repr_list(value):
        flat = re.sub(r"\s+", " ", entry).strip()
        heads = list(_LEG_HEAD.finditer(flat))
        if not heads:
            rows.append({"sphere": None, "kind": None, "number": None, "year": None,
                         "articles": ";".join(re.sub(r"\s+", "", i) for i in _LEG_ITEMS.findall(flat)) or None,
                         "raw": flat})
            continue
        for n, head in enumerate(heads):
            end = heads[n + 1].start() if n + 1 < len(heads) else len(flat)
            block = flat[head.end() : end]
            rows.append(
                {
                    "sphere": head.group("sphere").upper(),
                    "kind": head.group("kind").upper(),
                    "number": head.group("number").lstrip("0") or "0",
                    "year": head.group("year"),
                    "articles": ";".join(re.sub(r"\s+", "", i) for i in _LEG_ITEMS.findall(block)) or None,
                    "raw": flat[head.start() : end].strip(),
                }
            )
    return rows


def espelho_row(record: dict, *, orgao_slug: str, source_file: str, salt: bytes) -> dict | None:
    """Project one published record onto :data:`ESPELHO_SCHEMA` (returns ``None`` without an identifier)."""
    numero_registro = clean(record.get("numeroRegistro"))
    espelho_id = clean(record.get("id"))
    if not (numero_registro or espelho_id):
        return None
    journal, published = parse_publication(record.get("dataPublicacao"))
    citations = parse_citations(record.get("jurisprudenciaCitada"))
    legislation = parse_legislation(record.get("referenciasLegislativas"))
    return {
        "espelho_id": espelho_id or f"{orgao_slug}:{numero_registro}",
        "orgao_slug": orgao_slug,
        "numero_registro": numero_registro,
        "numero_processo": clean(record.get("numeroProcesso")),
        "numero_documento": clean(record.get("numeroDocumento")),
        "sigla_classe": clean(record.get("siglaClasse")),
        "descricao_classe": clean(record.get("descricaoClasse")),
        "classe_padronizada": clean(record.get("classePadronizada")),
        "orgao_julgador": clean(record.get("nomeOrgaoJulgador")),
        "relator_hash": hash_name(clean(record.get("ministroRelator")), salt),
        "tipo_decisao": clean(record.get("tipoDeDecisao")),
        "journal": journal,
        "data_publicacao": published,
        "data_decisao": parse_compact_date(record.get("dataDecisao")),
        "tema": clean(record.get("tema")),
        "tese_juridica": clean(record.get("teseJuridica")),
        "ementa": clean(record.get("ementa")),
        "decisao": clean(record.get("decisao")),
        "notas": clean(record.get("notas")),
        "informacoes_complementares": clean(record.get("informacoesComplementares")),
        "termos_auxiliares": clean(record.get("termosAuxiliares")),
        "n_citations": len(citations),
        "n_legislation": len(legislation),
        "n_similar": len(parse_repr_list(record.get("acordaosSimilares"))),
        "source_file": source_file,
    }


def _frames(
    records: Iterable[dict], *, orgao_slug: str, source_file: str, salt: bytes, limit: int | None = None
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    rows: list[dict] = []
    citations: list[dict] = []
    legislation: list[dict] = []
    for n, record in enumerate(records):
        if limit is not None and n >= limit:
            break
        row = espelho_row(record, orgao_slug=orgao_slug, source_file=source_file, salt=salt)
        if row is None:
            continue
        rows.append(row)
        head = {"espelho_id": row["espelho_id"], "orgao_slug": orgao_slug,
                "numero_registro": row["numero_registro"]}
        citations.extend({**head, **c} for c in parse_citations(record.get("jurisprudenciaCitada")))
        legislation.extend({**head, **legislation_row}
                           for legislation_row in parse_legislation(record.get("referenciasLegislativas")))
    return (
        pl.DataFrame(rows, schema=ESPELHO_SCHEMA) if rows else pl.DataFrame(schema=ESPELHO_SCHEMA),
        pl.DataFrame(citations, schema=CITATION_SCHEMA) if citations else pl.DataFrame(schema=CITATION_SCHEMA),
        pl.DataFrame(legislation, schema=LEGISLATION_SCHEMA) if legislation else pl.DataFrame(schema=LEGISLATION_SCHEMA),
    )


def read_espelhos(
    path: str | Path, *, orgao_slug: str, salt: bytes, limit: int | None = None
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Read one published JSON file into ``(espelhos, citations, legislation)`` frames."""
    path = Path(path)
    return _frames(iter_json_records(path), orgao_slug=orgao_slug, source_file=path.name, salt=salt, limit=limit)


def iter_zip_records(path: str | Path) -> Iterator[dict]:
    """Yield the records of every JSON member of a published ZIP, without extracting it to disk."""
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.lower().endswith(".json"):
                continue
            with zf.open(name) as fh:
                try:
                    data = json.load(io.TextIOWrapper(fh, encoding="utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
            yield from (r for r in (data if isinstance(data, list) else [data]) if isinstance(r, dict))


def read_espelhos_zip(
    path: str | Path, *, orgao_slug: str, salt: bytes, limit: int | None = None
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Read the initial backlog ZIP of a dataset — measured in 2026-09-23 to hold decisions back to 1989, with
    almost no overlap with the monthly series (probe: `scripts/11b_probe_espelho_zip.py`)."""
    path = Path(path)
    return _frames(iter_zip_records(path), orgao_slug=orgao_slug, source_file=path.name, salt=salt, limit=limit)
