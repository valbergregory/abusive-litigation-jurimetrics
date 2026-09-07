"""Helpers for the CNJ unified case number (Resolução CNJ 65/2008).

Format NNNNNNN-DD.AAAA.J.TR.OOOO stored as 20 digits: sequential (7), check digits (2),
year (4), segment J (1), tribunal TR (2), origin unit OOOO (4).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_DIGITS = re.compile(r"\D")

# Segment codes of the Judiciary (art. 2º, Res. CNJ 65/2008)
SEGMENTS = {
    "1": "STF",
    "2": "CNJ",
    "3": "STJ",
    "4": "Justiça Federal",
    "5": "Justiça do Trabalho",
    "6": "Justiça Eleitoral",
    "7": "Justiça Militar da União",
    "8": "Justiça Estadual",
    "9": "Justiça Militar Estadual",
}

# J.TR -> DataJud public endpoint alias (state courts and federal regional courts; extend as needed)
DATAJUD_ALIAS = {
    "3.00": "api_publica_stj",
    "4.01": "api_publica_trf1",
    "4.02": "api_publica_trf2",
    "4.03": "api_publica_trf3",
    "4.04": "api_publica_trf4",
    "4.05": "api_publica_trf5",
    "4.06": "api_publica_trf6",
    "8.01": "api_publica_tjac",
    "8.02": "api_publica_tjal",
    "8.03": "api_publica_tjap",
    "8.04": "api_publica_tjam",
    "8.05": "api_publica_tjba",
    "8.06": "api_publica_tjce",
    "8.07": "api_publica_tjdft",
    "8.08": "api_publica_tjes",
    "8.09": "api_publica_tjgo",
    "8.10": "api_publica_tjma",
    "8.11": "api_publica_tjmt",
    "8.12": "api_publica_tjms",
    "8.13": "api_publica_tjmg",
    "8.14": "api_publica_tjpa",
    "8.15": "api_publica_tjpb",
    "8.16": "api_publica_tjpr",
    "8.17": "api_publica_tjpe",
    "8.18": "api_publica_tjpi",
    "8.19": "api_publica_tjrj",
    "8.20": "api_publica_tjrn",
    "8.21": "api_publica_tjrs",
    "8.22": "api_publica_tjro",
    "8.23": "api_publica_tjrr",
    "8.24": "api_publica_tjsc",
    "8.25": "api_publica_tjse",
    "8.26": "api_publica_tjsp",
    "8.27": "api_publica_tjto",
}


@dataclass(frozen=True)
class CNJNumber:
    sequential: str
    check: str
    year: int
    segment: str
    tribunal: str
    origin: str

    @property
    def digits(self) -> str:
        return f"{self.sequential}{self.check}{self.year:04d}{self.segment}{self.tribunal}{self.origin}"

    @property
    def formatted(self) -> str:
        return f"{self.sequential}-{self.check}.{self.year:04d}.{self.segment}.{self.tribunal}.{self.origin}"

    @property
    def segment_name(self) -> str:
        return SEGMENTS.get(self.segment, "desconhecido")

    @property
    def datajud_alias(self) -> str | None:
        return DATAJUD_ALIAS.get(f"{self.segment}.{self.tribunal}")

    def check_digits_valid(self) -> bool:
        """ISO 7064 MOD 97-10 as prescribed by Res. CNJ 65/2008, art. 1º, §§ 1º–2º."""
        base = f"{self.sequential}{self.year:04d}{self.segment}{self.tribunal}{self.origin}"
        return int(self.check) == 98 - (int(base + "00") % 97)


def parse_cnj(value: str) -> CNJNumber:
    d = _DIGITS.sub("", value or "")
    if len(d) != 20:
        raise ValueError(f"CNJ number must have 20 digits, got {len(d)}: {value!r}")
    return CNJNumber(
        sequential=d[:7], check=d[7:9], year=int(d[9:13]), segment=d[13], tribunal=d[14:16], origin=d[16:20]
    )


def parse_datajud_datetime(value: str | None):
    """`dataAjuizamento` arrives as 'yyyyMMddHHmmss' (14 digits). Returns datetime or None.
    Never let the server parse this field (see docs/feasibility_report.md §1.2)."""
    from datetime import datetime

    if not value:
        return None
    d = _DIGITS.sub("", str(value))
    if len(d) < 8:
        return None
    d = (d + "000000")[:14]
    try:
        return datetime.strptime(d, "%Y%m%d%H%M%S")
    except ValueError:
        return None
