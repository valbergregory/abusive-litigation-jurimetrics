"""Readers for the STJ open-data set *Íntegras de decisões terminativas e acórdãos* (CKAN).

Each publication day (or month, for 2022-02/03/04/07) ships two resources: ``metadados<key>.json`` (one row per
document) and ``textos<key>.zip`` (one ``<seq>.txt`` per document, optionally under a ``<day>/`` folder).
The metadata schema drifts across years; everything is normalised here so downstream code sees one layout:

* 2021 / 2024+ : ``SeqDocumento``, ``NM_MINISTRO``, ISO dates, ``dataDistribuição`` (accent, 2025+);
* 2022–2023    : ``seqDocumento``, ``ministro``, epoch-milliseconds dates;
* ``assuntos`` : dotted CNJ paths (``00287.03603.03608., ...``; 2021 and 2026), ``;``-separated leaves (2022–2023)
  or ``, ``-separated leaves (2024–2025). Only the leaf codes are kept, plus the raw string.

Privacy rule (CLAUDE.md §4): the rapporteur's name is never stored in clear — ``relator_hash`` is a salted SHA-256.
``descricaoMonocratica`` contains ``#{nome_da_parte}`` placeholders only (no real names) and is kept as published.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import unicodedata
import zipfile
from pathlib import Path

import polars as pl

KEY_RE = re.compile(r"(\d{6,8})")
BR_RE = re.compile(r"<br\s*/?>", re.I)
_LEAF_SPLIT = re.compile(r"[;,]")

META_SCHEMA = {
    "seq_documento": pl.Int64,
    "key": pl.Utf8,
    "data_publicacao": pl.Date,
    "tipo_documento": pl.Utf8,
    "numero_registro": pl.Utf8,
    "processo": pl.Utf8,
    "classe": pl.Utf8,
    "data_recebimento": pl.Date,
    "data_distribuicao": pl.Date,
    "relator_hash": pl.Utf8,
    "recurso": pl.Utf8,
    "teor": pl.Utf8,
    "descricao_monocratica": pl.Utf8,
    "assuntos_raw": pl.Utf8,
    "assuntos_leaf": pl.Utf8,
    "source_file": pl.Utf8,
}
TEXT_SCHEMA = {
    "seq_documento": pl.Int64,
    "key": pl.Utf8,
    "member": pl.Utf8,
    "nchar": pl.Int64,
    "text_sha256": pl.Utf8,
    "text": pl.Utf8,
}


def strip_accents(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def key_of(name: str) -> str | None:
    """``textos20230614.zip`` → ``20230614``; ``metadados202202.json`` → ``202202``."""
    m = KEY_RE.search(Path(name).name)
    return m.group(1) if m else None


def _norm_key(k: str) -> str:
    k = strip_accents(k).lower()
    return {"nm_ministro": "ministro"}.get(k, k)


def _clean(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return None if s in ("", "None", "null") else s


def parse_date(v) -> dt.date | None:
    """ISO ``YYYY-MM-DD[...]`` or epoch milliseconds (as int or digit string) → date (Brasília local)."""
    s = _clean(v)
    if s is None:
        return None
    if s.isdigit() and len(s) >= 11:
        ts = int(s) / 1000
        return (dt.datetime.fromtimestamp(ts, dt.UTC) - dt.timedelta(hours=3)).date()
    try:
        return dt.date.fromisoformat(s[:10])
    except ValueError:
        return None


def parse_assuntos_leaf(raw: str | None) -> str | None:
    """Leaf CNJ codes as ``'a;b;c'`` (unique, order kept), or None."""
    s = _clean(raw)
    if s is None:
        return None
    leaves: list[str] = []
    if "." in s:
        for path in s.split(","):
            segs = [x for x in path.strip().split(".") if x]
            if segs:
                leaves.append(segs[-1])
    else:
        leaves = [x.strip() for x in _LEAF_SPLIT.split(s)]
    out: list[str] = []
    for x in leaves:
        if x.isdigit():
            x = str(int(x))
            if x not in out:
                out.append(x)
    return ";".join(out) or None


def hash_name(name: str | None, salt: bytes) -> str | None:
    s = _clean(name)
    if s is None:
        return None
    return hashlib.sha256(salt + strip_accents(s).upper().encode()).hexdigest()[:24]


def read_metadata(path: str | Path, salt: bytes) -> pl.DataFrame:
    path = Path(path)
    rows = json.loads(path.read_text(encoding="utf-8"))
    key = key_of(path.name)
    recs = []
    for r in rows:
        r = {_norm_key(k): v for k, v in r.items()}
        processo = _clean(r.get("processo"))
        m = re.match(r"[A-Za-z]+", processo or "")
        seq = _clean(r.get("seqdocumento"))
        recs.append(
            {
                "seq_documento": int(seq) if seq and seq.isdigit() else None,
                "key": key,
                "data_publicacao": parse_date(r.get("datapublicacao")),
                "tipo_documento": strip_accents(_clean(r.get("tipodocumento")) or "").upper() or None,
                "numero_registro": _clean(r.get("numeroregistro")),
                "processo": processo,
                "classe": m.group(0) if m else None,
                "data_recebimento": parse_date(r.get("datarecebimento")),
                "data_distribuicao": parse_date(r.get("datadistribuicao")),
                "relator_hash": hash_name(r.get("ministro"), salt),
                "recurso": _clean(r.get("recurso")),
                "teor": _clean(r.get("teor")),
                "descricao_monocratica": _clean(r.get("descricaomonocratica")),
                "assuntos_raw": _clean(r.get("assuntos")),
                "assuntos_leaf": parse_assuntos_leaf(r.get("assuntos")),
                "source_file": path.name,
            }
        )
    return pl.DataFrame(recs, schema=META_SCHEMA, orient="row") if recs else pl.DataFrame(schema=META_SCHEMA)


def read_texts(zip_path: str | Path) -> pl.DataFrame:
    zip_path = Path(zip_path)
    key = key_of(zip_path.name)
    recs = []
    try:
        z = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        # e.g. textos20260126.zip (3.9 MB, published 2026-02-11): local headers present, central directory unreadable —
        # the source file itself is damaged (size matches CKAN). Reported by the caller as text_rows = 0.
        return pl.DataFrame(schema=TEXT_SCHEMA)
    with z:
        for info in z.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".txt"):
                continue
            m = re.search(r"(\d+)", Path(info.filename).name)
            if not m:
                continue
            raw = z.read(info)
            text = BR_RE.sub("\n", raw.decode("utf-8", "replace")).replace("\r", "")
            recs.append(
                {
                    "seq_documento": int(m.group(1)),
                    "key": key,
                    "member": info.filename,
                    "nchar": len(text),
                    "text_sha256": hashlib.sha256(raw).hexdigest(),
                    "text": text,
                }
            )
    df = pl.DataFrame(recs, schema=TEXT_SCHEMA, orient="row") if recs else pl.DataFrame(schema=TEXT_SCHEMA)
    return df.unique(subset=["seq_documento"], keep="first", maintain_order=True)


def file_sha256(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()
