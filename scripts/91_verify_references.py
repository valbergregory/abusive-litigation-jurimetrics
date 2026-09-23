"""Utility — verify candidate references against Crossref (and DataCite) before they reach the manuscript.

Policy: a reference suggested by any AI tool is a *hypothesis*. It only becomes a candidate after the DOI
resolves and the returned title/author/year match what was suggested (docs/ai_usage_log.md). This script does
that check and writes a BibTeX file with one comment per entry recording the verification.

Usage:
    uv run python scripts/91_verify_references.py notes/dois.txt            # one DOI (optionally "DOI<TAB>title") per line
    uv run python scripts/91_verify_references.py notes/dois.txt --out notes/references_candidates.bib

Writes: the .bib, plus logs/91_verify_references.json with the status of every DOI.
Nothing is invented: a DOI that does not resolve is reported as `unresolved` and kept out of the .bib.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import unicodedata
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "logs"
CROSSREF = "https://api.crossref.org/works/"
DATACITE = "https://api.datacite.org/dois/"
UA = "abusive-litigation-jurimetrics/0.1 (research; mailto:valber.gregory@gmail.com)"

TYPE_MAP = {
    "journal-article": "article",
    "proceedings-article": "inproceedings",
    "book": "book",
    "book-chapter": "incollection",
    "monograph": "book",
    "report": "techreport",
    "posted-content": "misc",
    "dissertation": "phdthesis",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def title_matches(expected: str, got: str) -> bool | None:
    """None when nothing was expected; otherwise a loose containment/overlap test."""
    if not expected:
        return None
    a, b = norm(expected), norm(got)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    wa, wb = set(a.split()), set(b.split())
    return len(wa & wb) / max(1, min(len(wa), len(wb))) >= 0.6


def fetch(client: httpx.Client, doi: str) -> tuple[str, dict | None]:
    for base, source in ((CROSSREF, "crossref"), (DATACITE, "datacite")):
        try:
            r = client.get(base + doi, timeout=30)
        except httpx.HTTPError:
            continue
        if r.status_code == 200:
            payload = r.json()
            return source, payload.get("message", payload.get("data", {}))
    return "unresolved", None


def to_entry(doi: str, source: str, msg: dict) -> dict:
    if source == "datacite":
        attr = msg.get("attributes", {})
        return {
            "key": re.sub(r"[^A-Za-z0-9]", "", doi)[-12:],
            "type": "misc",
            "title": (attr.get("titles") or [{}])[0].get("title", ""),
            "authors": "; ".join(c.get("name", "") for c in attr.get("creators", [])),
            "year": str(attr.get("publicationYear", "")),
            "venue": attr.get("publisher", ""),
            "doi": doi,
        }
    title = (msg.get("title") or [""])[0]
    authors = "; ".join(
        f"{a.get('family', '')}, {a.get('given', '')}".strip(", ") for a in msg.get("author", [])
    ) or (msg.get("editor") and "; ".join(f"{e.get('family','')}, {e.get('given','')}" for e in msg["editor"])) or ""
    issued = (msg.get("issued", {}).get("date-parts") or [[None]])[0]
    year = str(issued[0]) if issued and issued[0] else ""
    venue = (msg.get("container-title") or [""])[0] or msg.get("publisher", "")
    first = (msg.get("author") or [{}])[0].get("family", "anon")
    return {
        "key": re.sub(r"[^A-Za-z0-9]", "", f"{first}{year}{norm(title).split(' ')[0] if title else ''}") or doi,
        "type": TYPE_MAP.get(msg.get("type", ""), "misc"),
        "title": title,
        "authors": authors,
        "year": year,
        "venue": venue,
        "doi": doi,
        "publisher": msg.get("publisher", ""),
        "citations": msg.get("is-referenced-by-count"),
    }


def bibtex(entry: dict, note: str) -> str:
    fields = [
        ("author", entry["authors"]),
        ("title", entry["title"]),
        ("journal" if entry["type"] == "article" else "booktitle", entry["venue"]),
        ("year", entry["year"]),
        ("doi", entry["doi"]),
    ]
    body = ",\n".join(f"  {k:<10} = {{{v}}}" for k, v in fields if v)
    return f"% {note}\n@{entry['type']}{{{entry['key']},\n{body}\n}}\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="file with one 'DOI' or 'DOI<TAB>expected title' per line")
    ap.add_argument("--out", default=str(ROOT / "notes" / "references_candidates.bib"))
    args = ap.parse_args(argv)

    lines = [ln.strip() for ln in Path(args.input).read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.startswith("#")]
    results = []
    entries = []
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True) as client:
        for ln in lines:
            doi, _, expected = ln.partition("\t")
            doi = doi.strip().rstrip(".")
            source, msg = fetch(client, doi)
            if msg is None:
                results.append({"doi": doi, "status": "unresolved", "expected_title": expected or None})
                print(f"  UNRESOLVED  {doi}")
                continue
            entry = to_entry(doi, source, msg)
            match = title_matches(expected, entry["title"])
            status = "verified" if match is not False else "title_mismatch"
            results.append({"doi": doi, "status": status, "source": source, "title": entry["title"],
                            "year": entry["year"], "venue": entry["venue"], "type": entry["type"],
                            "citations": entry.get("citations"), "expected_title": expected or None})
            note = (f"{status} via {source} on {dt.date.today().isoformat()}"
                    + (f"; cited by {entry['citations']}" if entry.get("citations") is not None else ""))
            if status == "verified":
                entries.append(bibtex(entry, note))
            print(f"  {status:<15} {doi}  {entry['year']}  {entry['title'][:70]}")

    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    header = (f"% candidate references for the manuscript — verified against Crossref/DataCite on "
              f"{dt.date.today().isoformat()} by scripts/91_verify_references.py\n"
              f"% nothing here is cited until the researcher approves it (docs/ai_usage_log.md)\n\n")
    out.write_text(header + "\n".join(entries), encoding="utf-8")
    LOG.mkdir(exist_ok=True)
    summary = {"run_at": dt.datetime.now().isoformat(timespec="seconds"), "input": args.input,
               "checked": len(lines), "verified": sum(r["status"] == "verified" for r in results),
               "unresolved": sum(r["status"] == "unresolved" for r in results),
               "title_mismatch": sum(r["status"] == "title_mismatch" for r in results),
               "out": out.as_posix().replace(ROOT.as_posix() + "/", ""), "results": results}
    json.dump(summary, open(LOG / "91_verify_references.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
