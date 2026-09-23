"""Phase 1, step 24 — do the two public sources agree about the same case?

The íntegras carry the full text of every published decision; the espelhos carry the structured record of the
collegiate judgments (ementa, decision, citations). They are joined by ``numero_registro``. This step measures
their agreement on the *same* case, which the Data section needs for three reasons:

* the espelhos are the searchable public face of the court, so a phenomenon that the full text states and the
  espelho omits is invisible to anyone searching the ementas;
* it is an external check on the instrument: the lexicon is applied to two independently produced texts;
* it bounds what a study based only on espelhos (cheaper, smaller) could ever find.

Reported for the strict tier (the phenomenon is named) and for the candidate set as a whole, per year, with the
k >= 5 suppression rule. No label is involved: both sides are measurements of the same instrument.

Writes: logs/24_crosscheck_integras_espelhos.json (counts only).
Usage:  uv run python scripts/24_crosscheck_integras_espelhos.py
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from alj.db import connect_or_memory  # noqa: E402

DB = ROOT / "data" / "alj.duckdb"
LOG = ROOT / "logs"
META = (ROOT / "data" / "interim" / "stj_integras" / "meta" / "*.parquet").as_posix()
CAND = (ROOT / "data" / "interim" / "candidates" / "docs" / "*.parquet").as_posix()
ESP = (ROOT / "data" / "interim" / "espelhos" / "espelhos" / "*.parquet").as_posix()
ESP_CAND = (ROOT / "data" / "interim" / "candidates_espelhos" / "docs" / "*.parquet").as_posix()
K_MIN = 5


def main() -> int:
    for glob, what in ((CAND, "candidates (step 20)"), (ESP, "espelhos (step 11)"), (ESP_CAND, "espelho candidates (step 23)")):
        if not list(Path(glob).parent.glob("*.parquet")):
            print(f"missing {what} — run the corresponding step first", file=sys.stderr)
            return 2

    con, _ = connect_or_memory(DB, read_only=False)
    con.execute(f"CREATE OR REPLACE TEMP VIEW meta AS SELECT DISTINCT * FROM read_parquet('{META}')")
    con.execute(f"CREATE OR REPLACE TEMP VIEW cand AS SELECT * FROM read_parquet('{CAND}')")
    con.execute(f"CREATE OR REPLACE TEMP VIEW esp AS SELECT * FROM read_parquet('{ESP}')")
    con.execute(f"CREATE OR REPLACE TEMP VIEW espc AS SELECT * FROM read_parquet('{ESP_CAND}')")

    # one row per registration number, on each side
    con.execute(
        """CREATE OR REPLACE TEMP VIEW integras_reg AS
           SELECT m.numero_registro,
                  min(substr(m.key, 1, 4)) AS year,
                  max(CASE WHEN c.strict_hit THEN 1 ELSE 0 END) AS strict,
                  max(CASE WHEN c.is_candidate THEN 1 ELSE 0 END) AS candidate
           FROM meta m LEFT JOIN cand c USING (key, seq_documento)
           WHERE m.numero_registro IS NOT NULL
           GROUP BY 1"""
    )
    con.execute(
        """CREATE OR REPLACE TEMP VIEW espelhos_reg AS
           SELECT e.numero_registro,
                  max(CASE WHEN ec.strict_hit THEN 1 ELSE 0 END) AS strict,
                  max(CASE WHEN ec.is_candidate THEN 1 ELSE 0 END) AS candidate
           FROM esp e LEFT JOIN espc ec ON ec.key = e.orgao_slug || ':' || e.espelho_id
           WHERE e.numero_registro IS NOT NULL
           GROUP BY 1"""
    )

    def one(sql: str):
        return con.execute(sql).fetchone()

    totals = {
        "integras_registrations": one("SELECT count(*) FROM integras_reg")[0],
        "espelhos_registrations": one("SELECT count(*) FROM espelhos_reg")[0],
        "shared_registrations": one(
            "SELECT count(*) FROM integras_reg i JOIN espelhos_reg e USING (numero_registro)"
        )[0],
    }

    # agreement on the shared cases
    cm = con.execute(
        """SELECT sum(CASE WHEN i.strict = 1 AND e.strict = 1 THEN 1 ELSE 0 END) AS both_strict,
                  sum(CASE WHEN i.strict = 1 AND e.strict = 0 THEN 1 ELSE 0 END) AS integras_only,
                  sum(CASE WHEN i.strict = 0 AND e.strict = 1 THEN 1 ELSE 0 END) AS espelho_only,
                  sum(CASE WHEN i.candidate = 1 AND e.candidate = 1 THEN 1 ELSE 0 END) AS both_candidate,
                  sum(CASE WHEN i.candidate = 1 AND e.candidate = 0 THEN 1 ELSE 0 END) AS cand_integras_only,
                  sum(CASE WHEN i.candidate = 0 AND e.candidate = 1 THEN 1 ELSE 0 END) AS cand_espelho_only
           FROM integras_reg i JOIN espelhos_reg e USING (numero_registro)"""
    ).fetchone()
    agreement = dict(zip(["both_strict", "strict_integras_only", "strict_espelho_only", "both_candidate",
                          "candidate_integras_only", "candidate_espelho_only"], [int(x or 0) for x in cm], strict=True))
    strict_in_integras = agreement["both_strict"] + agreement["strict_integras_only"]
    agreement["strict_recall_of_espelhos_pct"] = (
        round(100.0 * agreement["both_strict"] / strict_in_integras, 1) if strict_in_integras else None
    )

    by_year = [
        dict(zip(["year", "integras_strict", "with_espelho", "espelho_also_strict", "pct"], row, strict=True))
        for row in con.execute(
            """SELECT i.year,
                      count(*) AS integras_strict,
                      sum(CASE WHEN e.numero_registro IS NOT NULL THEN 1 ELSE 0 END) AS with_espelho,
                      sum(CASE WHEN e.strict = 1 THEN 1 ELSE 0 END) AS espelho_also_strict,
                      round(100.0 * sum(CASE WHEN e.strict = 1 THEN 1 ELSE 0 END)
                            / nullif(sum(CASE WHEN e.numero_registro IS NOT NULL THEN 1 ELSE 0 END), 0), 1) AS pct
               FROM integras_reg i LEFT JOIN espelhos_reg e USING (numero_registro)
               WHERE i.strict = 1 GROUP BY 1 HAVING count(*) >= ? ORDER BY 1""",
            [K_MIN],
        ).fetchall()
    ]
    con.close()

    out = {
        "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "unit": "numero_registro (one STJ case), not document",
        "totals": totals,
        "agreement_on_shared_cases": agreement,
        "strict_by_year": by_year,
        "note": ("the espelhos only cover collegiate judgments from 2022-05 onwards, so a case decided "
                 "monocratically has no espelho by construction; read the coverage column before the agreement"),
        "k_min": K_MIN,
    }
    LOG.mkdir(exist_ok=True)
    json.dump(out, open(LOG / "24_crosscheck_integras_espelhos.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
