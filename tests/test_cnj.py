from datetime import datetime

import pytest

from alj.cnj import parse_cnj, parse_datajud_datetime

# numbers observed in phase 0 (public case numbers returned by the STJ open-data portal / DataJud)
OBSERVED = [
    ("10615145420258260100", "8", "26", "api_publica_tjsp", 2025),
    ("08134596420268140000", "8", "14", "api_publica_tjpa", 2026),
    ("00000371120134058402", "4", "05", "api_publica_trf5", 2013),
    ("00445025320144013400", "4", "01", "api_publica_trf1", 2014),
]


@pytest.mark.parametrize("digits,segment,tribunal,alias,year", OBSERVED)
def test_parse_observed_numbers(digits, segment, tribunal, alias, year):
    n = parse_cnj(digits)
    assert n.segment == segment
    assert n.tribunal == tribunal
    assert n.year == year
    assert n.datajud_alias == alias
    assert n.digits == digits
    assert n.check_digits_valid()


def test_formatted_roundtrip():
    n = parse_cnj("1061514-54.2025.8.26.0100")
    assert n.formatted == "1061514-54.2025.8.26.0100"
    assert n.digits == "10615145420258260100"
    assert n.segment_name == "Justiça Estadual"


def test_rejects_wrong_length():
    with pytest.raises(ValueError):
        parse_cnj("12345")


def test_parse_datajud_datetime_14_digits():
    assert parse_datajud_datetime("20221022085739") == datetime(2022, 10, 22, 8, 57, 39)


def test_parse_datajud_datetime_short_and_empty():
    assert parse_datajud_datetime("20240325") == datetime(2024, 3, 25)
    assert parse_datajud_datetime(None) is None
    assert parse_datajud_datetime("") is None
    assert parse_datajud_datetime("99999999999999") is None
