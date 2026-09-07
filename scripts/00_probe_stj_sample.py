"""Feasibility probe: download a handful of daily STJ 'integras' files spread across years,
check metadata<->text coverage and scan for abusive-litigation keywords with context snippets.
Writes data/raw/stj/<files>, logs/00_probe_stj_sample.json (counts only) and data/interim/probe_snippets_<day>.json
(keyword contexts, git-ignored because they may quote party names). No modelling, no labelling."""

import collections
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw", "stj")
LOG = os.path.join(ROOT, "logs")
idx = json.load(open(os.path.join(RAW, "integras_resources_index.json"), encoding="utf-8"))
DAYS = sys.argv[1:] or ["20210615", "20220615", "20230614", "20240612", "20241113", "20250611", "20260311", "20260826"]
KW = {
    "litigancia_abusiva": r"litig[âa]ncia\s+abusiva",
    "litigancia_predatoria": r"litig[âa]ncia\s+predat[óo]ria",
    "advocacia_predatoria": r"advocacia\s+predat[óo]ria",
    "demandas_fabricadas": r"demandas?\s+fabricad",
    "captacao_indevida": r"capta[çc][ãa]o\s+(indevida|il[íi]cita|irregular|de\s+client)",
    "procuracao_irregular": r"procura[çc][ãa]o\s+(irregular|falsa|gen[ée]rica|sem\s+poderes|desatualizada)",
    "documentos_repetidos": r"(documentos?|peti[çc][õo]es)\s+(repetid|id[êe]ntic|padroniza)",
    "fracionamento": r"fracionamento\s+(indevido\s+)?(de\s+|d[ao]s?\s+)?(demandas?|pedidos?|a[çc][õo]es|pretens)",
    "ajuizamento_massificado": r"(ajuizamento|litig[âa]ncia|demandas?|a[çc][õo]es)\s+(em\s+massa|massificad|massiv|repetitiv)",
    "abuso_direito_acao": r"abuso\s+do\s+direito\s+de\s+(a[çc][ãa]o|demandar|litigar|acesso)",
    "comportamento_anomalo": r"comportamento\s+processual\s+an[ôo]malo",
    "rec_cnj_159": r"Recomenda[çc][ãa]o\s+(CNJ\s+)?n?[º°.]?\s*159",
    "res_cnj_615": r"Resolu[çc][ãa]o\s+(CNJ\s+)?n?[º°.]?\s*615",
    "ma_fe_processual": r"litig[âa]ncia\s+de\s+m[áa][- ]f[ée]",
    "predatori_any": r"predat[óo]ri",
}
CORE = [k for k in KW if k not in ("ma_fe_processual", "predatori_any", "rec_cnj_159", "res_cnj_615")]


def fetch(name, kind):
    r = next((r for r in idx if r["name"] == name and r["format"] == kind), None)
    if not r:
        return None
    fn = os.path.join(
        RAW,
        ("textos" if kind == "ZIP" else "metadados")
        + name.replace(".zip", "")
        + (".zip" if kind == "ZIP" else ".json"),
    )
    if not os.path.exists(fn):
        for i in range(3):
            try:
                urllib.request.urlretrieve(r["url"], fn)
                break
            except Exception as e:
                time.sleep(3)
                err = e
        else:
            raise err
    return fn


out = []
for d in DAYS:
    zf = fetch(d + ".zip", "ZIP")
    mf = fetch("metadados" + d, "JSON")
    if not zf or not mf:
        print("missing", d)
        continue
    meta = json.load(open(mf, encoding="utf-8"))
    z = zipfile.ZipFile(zf)
    seqs = {str(r["SeqDocumento"]) for r in meta}
    names = {os.path.splitext(n)[0] for n in z.namelist()}
    hits = collections.Counter()
    core_docs = set()
    snippets = []
    for n in z.namelist():
        t = re.sub(r"<br\s*/?>", " ", z.read(n).decode("utf-8", "replace"))
        for k, p in KW.items():
            m = re.search(p, t, re.I)
            if m:
                hits[k] += 1
                if k in CORE:
                    core_docs.add(n)
                    if len(snippets) < 40:
                        snippets.append({"doc": n, "kw": k, "ctx": t[max(0, m.start() - 160) : m.end() + 160]})
    # snippets may contain party names quoted from decisions: keep them out of the committed log
    os.makedirs(os.path.join(ROOT, "data", "interim"), exist_ok=True)
    json.dump(
        snippets,
        open(os.path.join(ROOT, "data", "interim", f"probe_snippets_{d}.json"), "w", encoding="utf-8"),
        ensure_ascii=False,
        indent=1,
    )
    rec = {
        "day": d,
        "meta_n": len(seqs),
        "zip_n": len(names),
        "zip_in_meta": len(seqs & names),
        "sha256_zip": hashlib.sha256(open(zf, "rb").read()).hexdigest()[:16],
        "hits": dict(hits),
        "core_docs": len(core_docs),
        "tipo": dict(collections.Counter(r["tipoDocumento"] for r in meta)),
        "n_snippets_local": len(snippets),
    }
    out.append(rec)
    print(d, "meta", len(seqs), "zip", len(names), "core_docs", len(core_docs), dict(hits))
json.dump(out, open(os.path.join(LOG, "00_probe_stj_sample.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
