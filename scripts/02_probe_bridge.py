"""Feasibility probe of the record-linkage chain

    STJ 'integras' (numeroRegistro)
      -> STJ 'acervo em tramitacao' / 'atas de distribuicao' (numeroUnico, CNJ 20-digit number)
      -> DataJud STJ endpoint (numeroProcesso)
      -> DataJud endpoint of the tribunal of origin (same numeroProcesso).

Requires data/raw/stj/acervo_*.json.gz and at least one metadados*.json
(see scripts/00_probe_stj_sample.py). Output: logs/02_probe_bridge.json
"""

import glob
import gzip
import importlib.util
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw", "stj")
LOG = os.path.join(ROOT, "logs")

_spec = importlib.util.spec_from_file_location("dj", os.path.join(ROOT, "scripts", "01_probe_datajud.py"))
dj = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dj)

# segment J.TR of the CNJ number -> DataJud alias (extend as needed; full list on the wiki)
SEG = {
    "8.26": "tjsp",
    "8.13": "tjmg",
    "8.19": "tjrj",
    "8.21": "tjrs",
    "8.05": "tjba",
    "8.16": "tjpr",
    "8.17": "tjpe",
    "8.06": "tjce",
    "8.09": "tjgo",
    "8.02": "tjal",
    "8.12": "tjms",
    "8.07": "tjdft",
    "8.14": "tjpa",
    "8.24": "tjsc",
    "4.01": "trf1",
    "4.02": "trf2",
    "4.03": "trf3",
    "4.04": "trf4",
    "4.05": "trf5",
    "4.06": "trf6",
}


def alias_for(numero_unico: str):
    j, tr = numero_unico[13], numero_unico[14:16]
    a = SEG.get(f"{j}.{tr}")
    return "api_publica_" + a if a else None


if __name__ == "__main__":
    gz = sorted(glob.glob(os.path.join(RAW, "acervo_*.json.gz")))[-1]
    acervo = json.loads(gzip.open(gz, "rb").read())
    reg2uni = {str(r["numeroRegistro"]): r["numeroUnico"] for r in acervo}
    out = {"acervo_file": os.path.basename(gz), "acervo_records": len(acervo), "days": {}, "datajud_tests": []}

    metafiles = sorted(glob.glob(os.path.join(RAW, "metadados*.json")))
    for mf in metafiles:
        m = json.load(open(mf, encoding="utf-8"))
        regs = {str(r["numeroRegistro"]) for r in m}
        hit = regs & set(reg2uni)
        out["days"][os.path.basename(mf)] = {
            "registros": len(regs),
            "in_acervo": len(hit),
            "share": round(len(hit) / max(len(regs), 1), 3),
        }

    key = dj.get_key()
    m = json.load(open(metafiles[-1], encoding="utf-8"))
    for r in [r for r in m if str(r["numeroRegistro"]) in reg2uni][:5]:
        uni = reg2uni[str(r["numeroRegistro"])]
        rec = {"processo": r["processo"], "numeroUnico": uni}
        s = dj.search(key, "api_publica_stj", {"size": 3, "query": {"match": {"numeroProcesso": uni}}})["hits"]["hits"]
        rec["stj_hits"] = [(h["_source"]["classe"]["nome"], len(h["_source"].get("movimentos", []))) for h in s]
        a = alias_for(uni)
        if a:
            o = dj.search(key, a, {"size": 3, "query": {"match": {"numeroProcesso": uni}}})["hits"]["hits"]
            rec["origem"] = a
            rec["origem_hits"] = [
                (
                    h["_source"]["grau"],
                    h["_source"]["classe"]["nome"],
                    h["_source"]["orgaoJulgador"].get("codigoMunicipioIBGE"),
                    len(h["_source"].get("movimentos", [])),
                )
                for h in o
            ]
        out["datajud_tests"].append(rec)
        print(rec)

    print(out["days"])
    with open(os.path.join(LOG, "02_probe_bridge.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
