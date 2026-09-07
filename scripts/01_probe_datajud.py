"""Feasibility probe of the DataJud public API (CNJ).

- Reads the current public API key from the wiki page (never hard-code it: CNJ may rotate it).
- Fetches 2 sample documents for STJ and TJSP and prints the field structure.
- Measures municipality (IBGE) coverage per tribunal using movimentos.dataHora as the time
  filter, because server-side date operations on `dataAjuizamento` (a 14-digit string,
  yyyyMMddHHmmss) are unreliable: for millions of documents Elasticsearch parses it as epoch
  milliseconds and yields years such as 2571. Parse that field client-side instead.

Outputs: data/raw/datajud/sample_<alias>.json and logs/01_probe_datajud.json
"""

import html
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw", "datajud")
LOG = os.path.join(ROOT, "logs")
WIKI = "https://datajud-wiki.cnj.jus.br/api-publica/acesso/"
BASE = "https://api-publica.datajud.cnj.jus.br/{alias}/_search"


def get_key() -> str:
    page = urllib.request.urlopen(WIKI, timeout=60).read().decode("utf-8", "replace")
    text = html.unescape(re.sub("<[^>]+>", " ", page))
    m = re.search(r"APIKey\s+([A-Za-z0-9+/=]{30,})", text)
    if not m:
        raise SystemExit("Public API key not found on the wiki page; check " + WIKI)
    return m.group(1)


def search(key: str, alias: str, body: dict) -> dict:
    req = urllib.request.Request(
        BASE.format(alias=alias),
        data=json.dumps(body).encode(),
        headers={"Authorization": "APIKey " + key, "Content-Type": "application/json"},
    )
    return json.load(urllib.request.urlopen(req, timeout=120))


def walk(o, p="", out=None):
    out = out if out is not None else []
    if isinstance(o, dict):
        for k, v in o.items():
            walk(v, p + "." + k, out)
    elif isinstance(o, list):
        out.append(f"{p} [list len {len(o)}]")
        if o:
            walk(o[0], p + "[]", out)
    else:
        out.append(f"{p} = {repr(o)[:70]}")
    return out


if __name__ == "__main__":
    key = get_key()
    log = {"fields": {}, "municipio": {}}
    for alias in ["api_publica_stj", "api_publica_tjsp"]:
        r = search(key, alias, {"size": 2, "query": {"match_all": {}}, "sort": [{"@timestamp": {"order": "desc"}}]})
        with open(os.path.join(RAW, f"sample_{alias}.json"), "w", encoding="utf-8") as fh:
            json.dump(r, fh, ensure_ascii=False, indent=1)
        log["fields"][alias] = walk(r["hits"]["hits"][0]["_source"])
        print(alias, "\n  " + "\n  ".join(log["fields"][alias][:12]))

    tribs = sys.argv[1:] or [
        "tjsp",
        "tjmg",
        "tjrj",
        "tjrs",
        "tjba",
        "tjpr",
        "tjpe",
        "tjce",
        "tjgo",
        "tjal",
        "tjms",
        "tjdft",
    ]
    for t in tribs:
        alias = "api_publica_" + t
        try:
            body = {
                "size": 0,
                "query": {"range": {"movimentos.dataHora": {"gte": "2024-01-01", "lt": "2024-04-01"}}},
                "aggs": {"mun": {"terms": {"field": "orgaoJulgador.codigoMunicipioIBGE", "size": 5000, "missing": -1}}},
            }
            b = search(key, alias, body)["aggregations"]["mun"]["buckets"]
            tot = sum(x["doc_count"] for x in b)
            miss = next((x["doc_count"] for x in b if x["key"] == -1), 0)
            log["municipio"][alias] = {
                "docs_2024Q1": tot,
                "missing": miss,
                "share_missing": round(miss / max(tot, 1), 3),
                "distinct_mun": len(b) - (1 if miss else 0),
            }
        except Exception as e:  # noqa: BLE001 - feasibility probe, report and continue
            log["municipio"][alias] = {"error": str(e)[:200]}
        print(alias, log["municipio"][alias])

    with open(os.path.join(LOG, "01_probe_datajud.json"), "w", encoding="utf-8") as fh:
        json.dump(log, fh, ensure_ascii=False, indent=1)
