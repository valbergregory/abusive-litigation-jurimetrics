"""Lexicon engine: the versioned measurement instrument of the project (CLAUDE.md §§2 and 12).

``config/lexicon_v2.yaml`` declares patterns (tiers *strict*, *conduct*, *sanction*, *normative*, *neighbour*),
context-window *exclusions* (false friends measured in phase 0, e.g. "custo de captação de recursos") and
*negations* (markers that the court **rejected** the allegation). This module only measures:

* :func:`scan_text` returns one :class:`Hit` per non-overlapping match, with its context window, whether an
  exclusion fired and whether a negation marker sits in the window;
* :func:`document_summary` aggregates the surviving hits of one document into the candidate row.

Nothing here produces a label. ``is_candidate`` means "worth the researcher's reading time", never "abusive":
labels come from ``docs/annotation_protocol.md`` and live in ``data/annotations/``.

Performance note. The corpus is ~3.0 M documents / 6 GB of text, so a Python pass per pattern is out of the
question. :func:`combined_source` builds ONE alternation with a named group per pattern, whose syntax is valid
both for Python ``re`` and for DuckDB's RE2 (no backreferences, no lookaround): step 20 pushes that single
regex into DuckDB to select the documents worth scanning, then calls :func:`scan_text` on the survivors only.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl
import yaml

TIERS = ("strict", "conduct", "sanction", "normative", "neighbour")

HIT_SCHEMA = {
    "seq_documento": pl.Int64,
    "key": pl.Utf8,
    "pattern_id": pl.Utf8,
    "tier": pl.Utf8,
    "annex_a": pl.Utf8,
    "start": pl.Int64,
    "match": pl.Utf8,
    "context": pl.Utf8,
    "negated_hint": pl.Boolean,
    "excluded_by": pl.Utf8,
}
CANDIDATE_SCHEMA = {
    "seq_documento": pl.Int64,
    "key": pl.Utf8,
    "n_hits": pl.Int64,
    "n_patterns": pl.Int64,
    "patterns": pl.Utf8,
    "tiers": pl.Utf8,
    "annex_a_items": pl.Utf8,
    "strict_hit": pl.Boolean,
    "conduct_hit": pl.Boolean,
    "sanction_hit": pl.Boolean,
    "normative_hit": pl.Boolean,
    "neighbour_hit": pl.Boolean,
    "negated_all": pl.Boolean,
    "n_excluded": pl.Int64,
    "is_candidate": pl.Boolean,
    "lexicon_version": pl.Utf8,
}


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


_BOUNDED = re.compile(r"\{0,\d+\}(\?)?")


def relax_bounded_repeats(source: str) -> str:
    """``[^.]{0,160}?`` → ``[^.]*?``: a strict superset of the pattern, and far cheaper to run.

    Bounded repeats are expanded by both engines: in RE2 they blow up the automaton (measured 25 s vs 0.8 s per
    publication day) and in Python ``re`` they backtrack. The relaxed form is used for the DuckDB pre-filter and
    for the per-pattern triage inside :func:`scan_text`; the hits themselves always come from the exact pattern,
    which is what the article documents. ``[^.]`` keeps the relaxation inside one sentence.
    """
    return _BOUNDED.sub(lambda m: "*?" if m.group(1) else "*", source)


@dataclass(frozen=True)
class Pattern:
    id: str
    tier: str
    regex: re.Pattern[str]
    annex_a: tuple[int, ...] = ()
    note: str = ""
    relaxed: re.Pattern[str] | None = None

    @property
    def source(self) -> str:
        return self.regex.pattern


@dataclass(frozen=True)
class Rule:
    """An exclusion or a negation marker (both are context-window tests)."""

    id: str
    regex: re.Pattern[str]
    applies_to: tuple[str, ...] = ()
    note: str = ""

    def covers(self, pattern_id: str) -> bool:
        return pattern_id in self.applies_to


@dataclass(frozen=True)
class Hit:
    pattern_id: str
    tier: str
    annex_a: tuple[int, ...]
    start: int
    match: str
    context: str
    negated_hint: bool = False
    excluded_by: str | None = None

    @property
    def kept(self) -> bool:
        return self.excluded_by is None


@dataclass(frozen=True)
class Lexicon:
    version: str
    patterns: tuple[Pattern, ...]
    exclusions: tuple[Rule, ...] = ()
    negations: tuple[Rule, ...] = ()
    options: dict = field(default_factory=dict)
    path: Path | None = None

    def by_id(self, pattern_id: str) -> Pattern:
        for p in self.patterns:
            if p.id == pattern_id:
                return p
        raise KeyError(pattern_id)

    def of_tier(self, *tiers: str) -> tuple[Pattern, ...]:
        return tuple(p for p in self.patterns if p.tier in tiers)

    @property
    def candidate_tiers(self) -> tuple[str, ...]:
        return tuple(self.options.get("candidate_tiers", ("strict", "conduct", "sanction")))

    @property
    def window(self) -> tuple[int, int]:
        return int(self.options.get("window_before", 320)), int(self.options.get("window_after", 320))

    @property
    def max_hits_per_pattern(self) -> int:
        return int(self.options.get("max_hits_per_pattern", 3))


def _compile(source: str) -> re.Pattern[str]:
    return re.compile(source, re.IGNORECASE | re.DOTALL)


def load_lexicon(path: str | Path) -> Lexicon:
    """Read and compile ``config/lexicon_v2.yaml``. Raises on duplicate ids or unknown tiers."""
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    patterns: list[Pattern] = []
    seen: set[str] = set()
    for item in raw.get("patterns", []):
        pid = item["id"]
        if pid in seen:
            raise ValueError(f"duplicate pattern id in {path.name}: {pid}")
        if item["tier"] not in TIERS:
            raise ValueError(f"unknown tier for {pid}: {item['tier']}")
        seen.add(pid)
        patterns.append(
            Pattern(
                id=pid,
                tier=item["tier"],
                regex=_compile(item["regex"]),
                annex_a=tuple(item.get("annex_a") or ()),
                note=item.get("note", ""),
                relaxed=_compile(relax_bounded_repeats(item["regex"])),
            )
        )
    if not patterns:
        raise ValueError(f"no patterns in {path}")

    def rules(section: str) -> tuple[Rule, ...]:
        out = []
        for item in raw.get(section, []) or []:
            applies = tuple(item.get("applies_to") or ())
            unknown = [a for a in applies if a not in seen]
            if unknown:
                raise ValueError(f"{section} {item['id']} applies_to unknown pattern(s): {unknown}")
            out.append(Rule(id=item["id"], regex=_compile(item["regex"]), applies_to=applies, note=item.get("note", "")))
        return tuple(out)

    return Lexicon(
        version=str(raw.get("version", "0")),
        patterns=tuple(patterns),
        exclusions=rules("exclusions"),
        negations=rules("negations"),
        options=raw.get("options", {}) or {},
        path=path,
    )


def _to_non_capturing(source: str) -> str:
    """Turn every capturing group of ``source`` into ``(?:…)`` so it can be nested in a named alternation."""
    out: list[str] = []
    in_class = False
    i = 0
    while i < len(source):
        c = source[i]
        if c == "\\" and i + 1 < len(source):
            out.append(source[i : i + 2])
            i += 2
            continue
        if in_class:
            in_class = c != "]"
            out.append(c)
        elif c == "[":
            in_class = True
            out.append(c)
        elif c == "(" and not source.startswith("(?", i):
            out.append("(?:")
        else:
            out.append(c)
        i += 1
    return "".join(out)


def combined_source(lex: Lexicon, tiers: tuple[str, ...] | None = None, *, relaxed: bool = False) -> str:
    """One alternation with a named group per pattern — valid for Python ``re`` and for DuckDB/RE2.

    Group names are ``p_<pattern_id>``; use :func:`prefilter_regex` for the Python side. With ``relaxed=True``
    the bounded repeats are widened (see :func:`relax_bounded_repeats`); that is the form step 20 pushes into
    DuckDB, because it is a superset and ~30× faster.
    """
    chosen = lex.of_tier(*(tiers or lex.candidate_tiers))
    if not chosen:
        raise ValueError("no pattern in the requested tiers")
    src = "|".join(f"(?P<p_{p.id}>{_to_non_capturing(p.source)})" for p in chosen)
    return relax_bounded_repeats(src) if relaxed else src


def prefilter_regex(lex: Lexicon, tiers: tuple[str, ...] | None = None, *, relaxed: bool = True) -> re.Pattern[str]:
    return _compile(combined_source(lex, tiers, relaxed=relaxed))


def _window(text: str, start: int, end: int, before: int, after: int) -> str:
    return re.sub(r"\s+", " ", text[max(0, start - before) : min(len(text), end + after)]).strip()


def scan_text(
    text: str,
    lex: Lexicon,
    *,
    tiers: tuple[str, ...] | None = None,
    only: tuple[str, ...] | None = None,
    triage: bool = True,
) -> list[Hit]:
    """All non-overlapping hits of every pattern (of ``tiers``, default: all) in one document's text.

    ``triage`` first tests the relaxed form of each pattern (a superset, cheap) and runs the exact pattern only
    when it can match — same result, ~10× faster on real decisions. ``only`` restricts the pattern ids scanned.
    """
    if not text:
        return []
    before, after = lex.window
    cap = lex.max_hits_per_pattern
    hits: list[Hit] = []
    chosen = lex.of_tier(*tiers) if tiers else lex.patterns
    if only is not None:
        chosen = tuple(p for p in chosen if p.id in set(only))
    for p in chosen:
        if triage and p.relaxed is not None and not p.relaxed.search(text):
            continue
        for n, m in enumerate(p.regex.finditer(text)):
            if n >= cap:
                break
            ctx = _window(text, m.start(), m.end(), before, after)
            excluded = next((r.id for r in lex.exclusions if r.covers(p.id) and r.regex.search(ctx)), None)
            negated = any(r.regex.search(ctx) for r in lex.negations)
            hits.append(
                Hit(
                    pattern_id=p.id,
                    tier=p.tier,
                    annex_a=p.annex_a,
                    start=m.start(),
                    match=re.sub(r"\s+", " ", m.group(0)).strip(),
                    context=ctx,
                    negated_hint=negated,
                    excluded_by=excluded,
                )
            )
    hits.sort(key=lambda h: (h.start, h.pattern_id))
    return hits


def document_summary(seq_documento: int, key: str, hits: list[Hit], lex: Lexicon) -> dict:
    """Aggregate one document's hits into the candidate row (see :data:`CANDIDATE_SCHEMA`)."""
    kept = [h for h in hits if h.kept]
    tiers = sorted({h.tier for h in kept})
    annex = sorted({i for h in kept for i in h.annex_a})
    in_candidate_tier = [h for h in kept if h.tier in lex.candidate_tiers]
    return {
        "seq_documento": seq_documento,
        "key": key,
        "n_hits": len(kept),
        "n_patterns": len({h.pattern_id for h in kept}),
        "patterns": ";".join(sorted({h.pattern_id for h in kept})),
        "tiers": ";".join(tiers),
        "annex_a_items": ";".join(str(i) for i in annex),
        "strict_hit": "strict" in tiers,
        "conduct_hit": "conduct" in tiers,
        "sanction_hit": "sanction" in tiers,
        "normative_hit": "normative" in tiers,
        "neighbour_hit": "neighbour" in tiers,
        "negated_all": bool(in_candidate_tier) and all(h.negated_hint for h in in_candidate_tier),
        "n_excluded": len(hits) - len(kept),
        "is_candidate": bool(in_candidate_tier),
        "lexicon_version": lex.version,
    }


def hits_frame(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=HIT_SCHEMA) if rows else pl.DataFrame(schema=HIT_SCHEMA)


def candidates_frame(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=CANDIDATE_SCHEMA) if rows else pl.DataFrame(schema=CANDIDATE_SCHEMA)


def hit_rows(seq_documento: int, key: str, hits: list[Hit]) -> list[dict]:
    return [
        {
            "seq_documento": seq_documento,
            "key": key,
            "pattern_id": h.pattern_id,
            "tier": h.tier,
            "annex_a": ";".join(str(i) for i in h.annex_a),
            "start": h.start,
            "match": h.match,
            "context": h.context,
            "negated_hint": h.negated_hint,
            "excluded_by": h.excluded_by,
        }
        for h in hits
    ]
