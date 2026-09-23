"""Build the descriptive figures of the manuscript from the pipeline logs (policy §13).

Only measurements go into a figure: nothing here depends on a label, because no label exists yet. The four
figures are the ones the Data section needs:

  fig_strict_by_year        documents naming the phenomenon per year — the 2024–2025 break (Rec. 159 + Theme 1198)
  fig_candidates_by_tier    candidates per year split by tier, showing that the conduct/sanction tiers dominate
  fig_bridge_coverage       share of candidates resolvable to a CNJ number with the acervo snapshot alone
  fig_pattern_hits          the most frequent patterns, by documents, with the neighbouring tier marked apart

Every value is read from logs/*.json (the step that measured it); a missing log simply skips its figure.
Output: PDF (vector, for LaTeX) + PNG (for slides) in outputs/figures/, picked up by scripts/90_export_overleaf.py.

Usage:  uv run python scripts/81_build_figures.py
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "logs"
FIG = ROOT / "outputs" / "figures"
GREY = "#8c8c8c"
INK = "#1a1a1a"
ACCENT = "#b03a2e"


def read_log(name: str) -> dict | None:
    path = LOG / name
    if not path.exists():
        return None
    try:
        return json.load(open(path, encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def style(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(GREY)
    ax.spines["bottom"].set_color(GREY)
    ax.tick_params(colors=INK, labelsize=9)
    ax.grid(axis="y", color=GREY, alpha=0.25, linewidth=0.6)
    ax.set_axisbelow(True)


def save(fig, name: str) -> str:
    FIG.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(FIG / f"{name}.{ext}", bbox_inches="tight", dpi=200)
    plt.close(fig)
    return name


def fig_strict_by_year(cand: dict) -> str | None:
    rows = cand.get("by_year") or []
    if not rows:
        return None
    years = [r["year"] for r in rows]
    strict = [r["strict"] for r in rows]
    fig, ax = plt.subplots(figsize=(5.6, 3.2))
    bars = ax.bar(years, strict, color=[ACCENT if int(y) >= 2024 else GREY for y in years], width=0.62)
    for b, v in zip(bars, strict, strict=True):
        ax.annotate(f"{v:,}".replace(",", "."), (b.get_x() + b.get_width() / 2, v),
                    ha="center", va="bottom", fontsize=8, color=INK)
    ax.set_ylabel("documents naming the phenomenon", fontsize=9)
    ax.set_xlabel("year of publication", fontsize=9)
    style(ax)
    ax.set_ylim(0, max(strict) * 1.18)
    ax.text(0.02, 0.95, "strict tier only (litigância predatória/abusiva, assédio processual…)",
            transform=ax.transAxes, fontsize=7.5, color=GREY, va="top")
    return save(fig, "fig_strict_by_year")


def fig_candidates_by_tier(cand: dict) -> str | None:
    rows = cand.get("by_year") or []
    if not rows:
        return None
    years = [r["year"] for r in rows]
    conduct = [r["conduct"] for r in rows]
    sanction = [r["sanction"] for r in rows]
    strict = [r["strict"] for r in rows]
    fig, ax = plt.subplots(figsize=(5.6, 3.2))
    ax.bar(years, sanction, label="sanction tier", color="#4a6fa5", width=0.62)
    ax.bar(years, conduct, bottom=sanction, label="conduct tier (Annex A)", color="#9ab3d5", width=0.62)
    ax.bar(years, strict, bottom=[s + c for s, c in zip(sanction, conduct, strict=True)],
           label="strict tier", color=ACCENT, width=0.62)
    ax.set_ylabel("candidate documents", fontsize=9)
    ax.set_xlabel("year of publication", fontsize=9)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    style(ax)
    ax.text(0.02, 0.80, "a document may hit more than one tier", transform=ax.transAxes,
            fontsize=7.5, color=GREY, va="top")
    return save(fig, "fig_candidates_by_tier")


def fig_bridge_coverage(bridge: dict) -> str | None:
    rows = bridge.get("candidate_coverage_by_year") or bridge.get("document_coverage_by_year") or []
    if not rows:
        return None
    years = [r["year"] for r in rows]
    pct = [r["pct"] for r in rows]
    fig, ax = plt.subplots(figsize=(5.6, 3.0))
    ax.plot(years, pct, marker="o", color=ACCENT, linewidth=1.8, markersize=5)
    ax.axhline(70, color=GREY, linestyle="--", linewidth=1)
    ax.annotate("go/no-go threshold (70%)", (0.02, 71), xycoords=("axes fraction", "data"),
                fontsize=7.5, color=GREY, va="bottom")
    for x, y in zip(years, pct, strict=True):
        ax.annotate(f"{y:.1f}%", (x, y), textcoords="offset points", xytext=(0, 7),
                    ha="center", fontsize=8, color=INK)
    ax.set_ylabel("candidates resolvable to a CNJ number", fontsize=9)
    ax.set_xlabel("year of publication", fontsize=9)
    ax.set_ylim(0, 100)
    style(ax)
    ax.text(0.02, 0.95, "acervo snapshot only; the atas de distribuição cover 2023-06-30 onwards",
            transform=ax.transAxes, fontsize=7.5, color=GREY, va="top")
    return save(fig, "fig_bridge_coverage")


def fig_pattern_hits(cand: dict, top: int = 14) -> str | None:
    rows = [r for r in (cand.get("by_pattern") or []) if (r.get("documents") or 0) >= 5][:top]
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: r["documents"])
    labels = [r["pattern_id"].replace("_", " ") for r in rows]
    values = [r["documents"] for r in rows]
    colors = [GREY if r["tier"] == "neighbour" else ("#4a6fa5" if r["tier"] == "sanction"
              else (ACCENT if r["tier"] == "strict" else "#9ab3d5")) for r in rows]
    fig, ax = plt.subplots(figsize=(6.0, 4.4))
    ax.barh(labels, values, color=colors, height=0.68)
    ax.set_xlabel("documents", fontsize=9)
    style(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GREY, alpha=0.25, linewidth=0.6)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in (ACCENT, "#9ab3d5", "#4a6fa5", GREY)]
    ax.legend(handles, ["strict", "conduct", "sanction", "neighbour (not a candidate)"],
              frameon=False, fontsize=8, loc="lower right")
    return save(fig, "fig_pattern_hits")


def main() -> int:
    cand = read_log("20_lexicon_candidates.json")
    bridge = read_log("12_ingest_stj_bridge.json")
    built, skipped = [], []
    for name, fn, src in (
        ("fig_strict_by_year", fig_strict_by_year, cand),
        ("fig_candidates_by_tier", fig_candidates_by_tier, cand),
        ("fig_bridge_coverage", fig_bridge_coverage, bridge),
        ("fig_pattern_hits", fig_pattern_hits, cand),
    ):
        if src is None:
            skipped.append({"figure": name, "why": "log not found"})
            continue
        out = fn(src)
        (built if out else skipped).append(out or {"figure": name, "why": "no rows in the log"})
    summary = {"run_at": dt.datetime.now().isoformat(timespec="seconds"), "built": built, "skipped": skipped,
               "out_dir": "outputs/figures"}
    json.dump(summary, open(LOG / "81_build_figures.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
