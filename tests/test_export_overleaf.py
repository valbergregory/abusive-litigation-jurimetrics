"""Overleaf exporter: booktabs conversion and \newcommand formatting (no filesystem side effects outside tmp_path)."""

from alj.export_overleaf import csv_to_booktabs, format_number, latex_escape, numbers_to_tex


def test_latex_escape_and_numbers():
    assert latex_escape("a_b & 5%") == r"a\_b \& 5\%"
    assert format_number(12345) == r"12\,345"
    assert format_number(0.1234, 2) == "0.12"
    tex = numbers_to_tex({"nDocs": {"value": 1500, "decimals": 0}, "shareHits": 0.5})
    assert r"\newcommand{\nDocs}{1\,500}" in tex and r"\newcommand{\shareHits}{0.50}" in tex


def test_csv_to_booktabs(tmp_path):
    p = tmp_path / "t.csv"
    p.write_text("court,docs,share_%\nTJSP,10,0.5\nTJRJ,12,0.6\n", encoding="utf-8")
    tex = csv_to_booktabs(p, label="tab:t")
    assert r"\begin{tabular}{lrr}" in tex and r"share\_\%" in tex and r"TJRJ & 12 & 0.6 \\" in tex
