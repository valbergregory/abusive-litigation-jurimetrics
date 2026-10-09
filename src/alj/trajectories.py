"""Trajectory covariates from the DataJud movements (step 31).

What a case *does* — how long it takes, how many movements it accumulates, whether it is extinguished without a
decision on the merits, whether documents were ordered to be amended — is the second half of design B. This
module turns the movement list collected by step 30 into one row per case.

Two rules shape the design:

* **movement groups are a measurement instrument** (CLAUDE.md §12), so they live in ``config/movement_groups.yaml``
  with a version, and the codes are the CNJ *Tabelas Processuais Unificadas* codes **as observed in the collected
  data** (``scripts/31_trajectory_features.py --vocabulary`` lists them with counts). Nothing is guessed from a
  code table that this corpus might not use;
* **a trajectory is never a label** (§2). ``grupo`` says whether the case's decisions carried lexicon signals, not
  whether the litigation was abusive; the comparison group is "not signalled" (§3).

The feature table is built in SQL (:func:`feature_sql`) because the movement table has tens of millions of rows;
the function is pure, so the logic is unit-tested against a small in-memory fixture instead of the real corpus.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class MovementGroup:
    """One group of procedural movements: a column in the feature table."""

    id: str
    label: str           # pt-BR, for the researcher's documents
    label_en: str = ""   # English, for the manuscript's tables and figures (falls back to ``label``)
    codes: tuple[int, ...] = ()
    name_contains: tuple[str, ...] = ()

    def predicate(self) -> str:
        """SQL predicate over the ``movimentos`` columns ``codigo`` and ``nome``."""
        parts = []
        if self.codes:
            parts.append("m.codigo IN (" + ", ".join(str(c) for c in self.codes) + ")")
        for needle in self.name_contains:
            escaped = needle.replace("'", "''")
            parts.append(f"m.nome ILIKE '%{escaped}%'")
        if not parts:
            raise ValueError(f"movement group {self.id!r} has neither codes nor name_contains")
        return "(" + " OR ".join(parts) + ")"


@dataclass(frozen=True)
class MovementGroups:
    version: str
    groups: tuple[MovementGroup, ...]

    def by_id(self, group_id: str) -> MovementGroup:
        for group in self.groups:
            if group.id == group_id:
                return group
        raise KeyError(group_id)


_ID = re.compile(r"^[a-z][a-z0-9_]{2,39}$")


def load_movement_groups(path: str | Path) -> MovementGroups:
    """Read and validate ``config/movement_groups.yaml``."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    version = str(raw.get("version") or "").strip()
    if not version:
        raise ValueError("movement_groups.yaml needs a version (the instrument is versioned, policy §5.3)")
    groups: list[MovementGroup] = []
    seen: set[str] = set()
    for item in raw.get("groups") or []:
        group_id = str(item.get("id") or "").strip()
        if not _ID.match(group_id):
            raise ValueError(f"invalid movement group id: {group_id!r}")
        if group_id in seen:
            raise ValueError(f"duplicate movement group id: {group_id!r}")
        seen.add(group_id)
        group = MovementGroup(
            id=group_id,
            label=str(item.get("label") or group_id),
            label_en=str(item.get("label_en") or ""),
            codes=tuple(int(c) for c in (item.get("codes") or [])),
            name_contains=tuple(str(n) for n in (item.get("name_contains") or [])),
        )
        group.predicate()  # fails now, not in the middle of a long query
        groups.append(group)
    if not groups:
        raise ValueError("movement_groups.yaml defines no group")
    return MovementGroups(version=version, groups=tuple(groups))


def feature_sql(
    groups: MovementGroups,
    *,
    cases: str = "datajud_cases",
    movimentos: str = "datajud_movimentos",
    targets: str = "datajud_targets",
) -> str:
    """SQL producing one row per case (``numero_processo``, ``alias``) with the trajectory covariates.

    Movements are de-duplicated by ``(codigo, data_hora, orgao_codigo)`` before being counted, because the same
    case is sometimes published as several DataJud documents of the same ``grau`` whose movement lists overlap.

    Dates come from the movements, never from the server's parsing of ``dataAjuizamento`` (CLAUDE.md §8): the
    window of a case is ``primeiro_movimento`` → ``ultimo_movimento``, and ``dias_desde_ajuizamento`` is only
    computed when the client-side parse of ``dataAjuizamento`` produced a plausible date (not after the last
    movement and not before 1990).
    """
    group_columns = []
    for group in groups.groups:
        predicate = group.predicate()
        group_columns.append(
            f"""count(*) FILTER (WHERE {predicate}) AS n_{group.id},
                min(m.data_hora) FILTER (WHERE {predicate}) AS primeiro_{group.id}"""
        )
    group_select = ",\n                ".join(group_columns)
    return f"""
        WITH c AS (
            SELECT numero_processo, alias,
                   count(*) AS n_documentos,
                   string_agg(DISTINCT grau, ';' ORDER BY grau) AS graus,
                   min(data_ajuizamento) AS data_ajuizamento,
                   max(nivel_sigilo) AS nivel_sigilo,
                   min(classe_codigo) AS classe_codigo,
                   min(classe_nome) AS classe_nome,
                   min(assuntos_codigos) AS assuntos_codigos,
                   max(municipio_ibge) AS municipio_ibge,
                   count(DISTINCT orgao_codigo) AS n_orgaos_caso
            FROM {cases} GROUP BY 1, 2),
        dedup AS (
            -- A case can appear in DataJud as several documents of the *same* grau (measured 2026-10-09: 5 % of
            -- the collected cases, e.g. three TJAL G2 documents of one case with overlapping movement lists).
            -- Counting the rows would multiply those movements, so a movement is identified by what it is:
            -- code, timestamp and judging body.
            SELECT numero_processo, alias, codigo, data_hora, orgao_codigo, any_value(nome) AS nome
            FROM {movimentos} GROUP BY 1, 2, 3, 4, 5),
        mv AS (
            SELECT m.numero_processo, m.alias,
                   count(*) AS n_movimentos,
                   count(DISTINCT m.codigo) AS n_codigos_distintos,
                   count(DISTINCT m.orgao_codigo) AS n_orgaos_movimento,
                   min(m.data_hora) AS primeiro_movimento,
                   max(m.data_hora) AS ultimo_movimento,
                   {group_select}
            FROM dedup m GROUP BY 1, 2),
        t AS (SELECT DISTINCT numero_processo, alias, grupo, pub_year, strict_hit, n_documentos AS n_docs_stj
              FROM {targets})
        SELECT t.numero_processo, t.alias, t.grupo, t.pub_year, t.strict_hit, t.n_docs_stj,
               c.n_documentos, c.graus, c.n_orgaos_caso, c.nivel_sigilo,
               c.classe_codigo, c.classe_nome, c.assuntos_codigos, c.municipio_ibge,
               c.data_ajuizamento, mv.primeiro_movimento, mv.ultimo_movimento,
               coalesce(mv.n_movimentos, 0) AS n_movimentos,
               coalesce(mv.n_codigos_distintos, 0) AS n_codigos_distintos,
               coalesce(mv.n_orgaos_movimento, 0) AS n_orgaos_movimento,
               date_diff('day', mv.primeiro_movimento, mv.ultimo_movimento) AS dias_entre_movimentos,
               CASE WHEN c.data_ajuizamento IS NOT NULL
                         AND c.data_ajuizamento <= mv.ultimo_movimento
                         AND year(c.data_ajuizamento) >= 1990
                    THEN date_diff('day', c.data_ajuizamento, mv.ultimo_movimento) END AS dias_desde_ajuizamento,
               {",\n               ".join(
                   f"coalesce(mv.n_{g.id}, 0) AS n_{g.id}, mv.primeiro_{g.id} AS primeiro_{g.id}"
                   for g in groups.groups
               )},
               (c.numero_processo IS NULL) AS nao_encontrado_no_datajud
        FROM t
        LEFT JOIN c ON c.numero_processo = t.numero_processo AND c.alias = t.alias
        LEFT JOIN mv ON mv.numero_processo = t.numero_processo AND mv.alias = t.alias
    """
