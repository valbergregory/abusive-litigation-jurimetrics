"""Reading aid for the annotation — print one decision in full, by ``doc_id``.

The protocol (§6.1) requires reading the whole decision, not the context window of the worksheet. This script
takes the ``doc_id`` of a row of ``data/annotations/gold_v1_sample.csv`` (``<key>-<seq_documento>``), prints the
metadata and the full text, and saves a copy under ``data/annotations/_leitura/`` so it can be opened in a text
editor. Nothing leaves the machine and nothing is written outside the git-ignored annotation folder.

With ``--marks`` the passages the lexicon matched are marked with «…» in the saved copy, to find them quickly —
they are hints, never labels (CLAUDE.md §2).

Usage:
    uv run python scripts/25_show_document.py 20250611-190666544
    uv run python scripts/25_show_document.py 20250611-190666544 --marks --no-print
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import duckdb

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alj.lexicon import load_lexicon, scan_text  # noqa: E402

META = (ROOT / "data" / "interim" / "stj_integras" / "meta" / "*.parquet").as_posix()
TEXT = (ROOT / "data" / "interim" / "stj_integras" / "text" / "*.parquet").as_posix()
OUT = ROOT / "data" / "annotations" / "_leitura"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("doc_id", help="<key>-<seq_documento>, as in the worksheet")
    ap.add_argument("--marks", action="store_true", help="mark the lexicon matches with «…» in the saved copy")
    ap.add_argument("--no-print", action="store_true", help="only save the file, do not print")
    args = ap.parse_args(argv)

    key, _, seq = args.doc_id.rpartition("-")
    if not key or not seq.isdigit():
        print(f"doc_id must be <key>-<seq_documento>, got {args.doc_id!r}", file=sys.stderr)
        return 2

    con = duckdb.connect()
    meta = con.execute(
        f"""SELECT data_publicacao, tipo_documento, classe, processo, numero_registro, assuntos_leaf, teor
            FROM read_parquet('{META}') WHERE key = ? AND seq_documento = ? LIMIT 1""",
        [key, int(seq)],
    ).fetchone()
    row = con.execute(
        f"SELECT text, nchar FROM read_parquet('{TEXT}') WHERE key = ? AND seq_documento = ? LIMIT 1",
        [key, int(seq)],
    ).fetchone()
    con.close()

    if meta is None:
        print(f"document {args.doc_id} not found in the metadata", file=sys.stderr)
        return 1
    if row is None or not row[0]:
        print(f"document {args.doc_id} has no text in the corpus (label it NA)", file=sys.stderr)
        return 1

    text, nchar = row
    header = (
        f"doc_id: {args.doc_id}\n"
        f"publicado: {meta[0]}   tipo: {meta[1]}   classe: {meta[2]}   processo: {meta[3]}\n"
        f"numeroRegistro: {meta[4]}   assuntos: {meta[5]}   caracteres: {nchar}\n"
        f"teor: {(meta[6] or '')[:200]}\n" + "-" * 100 + "\n"
    )

    body = text
    if args.marks:
        lex = load_lexicon(ROOT / "config" / "lexicon_v2.yaml")
        hits = [h for h in scan_text(text, lex) if h.kept]
        for h in sorted(hits, key=lambda h: -h.start):  # right to left, so the offsets stay valid
            end = h.start + len(re.sub(r"\s+", " ", h.match))
            body = body[: h.start] + "«" + body[h.start : end] + f"»[{h.pattern_id}]" + body[end:]

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{args.doc_id}.txt"
    path.write_text(header + body, encoding="utf-8")
    if not args.no_print:
        print(header + body)
    print(f"\n[salvo em {path}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
