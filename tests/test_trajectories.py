"""Tests for the trajectory covariates (step 31). The SQL runs against a small in-memory fixture."""

from __future__ import annotations

import datetime as dt

import duckdb
import pytest

from alj.trajectories import MovementGroup, feature_sql, load_movement_groups

CONFIG = """
version: 0.1.0-test
groups:
  - id: extincao
    label: Extinção sem resolução do mérito
    codes: [196, 456]
  - id: emenda
    label: Determinação de emenda da inicial
    name_contains: ["emenda", "d'água"]
"""


def write(tmp_path, text: str):
    path = tmp_path / "movement_groups.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_movement_groups(tmp_path):
    groups = load_movement_groups(write(tmp_path, CONFIG))
    assert groups.version == "0.1.0-test"
    assert [g.id for g in groups.groups] == ["extincao", "emenda"]
    assert groups.by_id("extincao").codes == (196, 456)
    with pytest.raises(KeyError):
        groups.by_id("nao_existe")


def test_load_movement_groups_requires_a_version(tmp_path):
    with pytest.raises(ValueError, match="version"):
        load_movement_groups(write(tmp_path, "groups:\n  - id: a_b\n    codes: [1]\n"))


def test_load_movement_groups_rejects_bad_ids_and_duplicates(tmp_path):
    with pytest.raises(ValueError, match="invalid"):
        load_movement_groups(write(tmp_path, "version: 1\ngroups:\n  - id: 'A B'\n    codes: [1]\n"))
    with pytest.raises(ValueError, match="duplicate"):
        load_movement_groups(
            write(tmp_path, "version: 1\ngroups:\n  - id: aaa\n    codes: [1]\n  - id: aaa\n    codes: [2]\n")
        )


def test_load_movement_groups_rejects_an_empty_group_and_an_empty_file(tmp_path):
    with pytest.raises(ValueError, match="neither codes nor name_contains"):
        load_movement_groups(write(tmp_path, "version: 1\ngroups:\n  - id: vazio\n    label: x\n"))
    with pytest.raises(ValueError, match="no group"):
        load_movement_groups(write(tmp_path, "version: 1\ngroups: []\n"))


def test_predicate_covers_codes_names_and_quotes():
    assert MovementGroup("a", "a", codes=(1, 2)).predicate() == "(m.codigo IN (1, 2))"
    assert MovementGroup("b", "b", name_contains=("emenda",)).predicate() == "(m.nome ILIKE '%emenda%')"
    both = MovementGroup("c", "c", codes=(3,), name_contains=("d'água",)).predicate()
    assert both == "(m.codigo IN (3) OR m.nome ILIKE '%d''água%')"


@pytest.fixture
def fixture_db(tmp_path):
    """Three targets: one ordinary case, one with an impossible dataAjuizamento, one absent from DataJud."""
    con = duckdb.connect()
    con.execute(
        """CREATE TABLE dj_cases (numero_processo VARCHAR, alias VARCHAR, grau VARCHAR,
                                  data_ajuizamento TIMESTAMP, nivel_sigilo INTEGER, classe_codigo VARCHAR,
                                  classe_nome VARCHAR, assuntos_codigos VARCHAR, municipio_ibge INTEGER,
                                  orgao_codigo VARCHAR)"""
    )
    con.execute(
        """INSERT INTO dj_cases VALUES
           ('1', 'api_publica_tjsp', 'G1', TIMESTAMP '2024-01-10 00:00:00', 0, '1116', 'Procedimento Comum',
            '7779', 3550308, '100'),
           ('1', 'api_publica_tjsp', 'G2', TIMESTAMP '2024-01-10 00:00:00', 0, '1116', 'Procedimento Comum',
            '7779', 3550308, '200'),
           ('2', 'api_publica_tjsp', 'G1', TIMESTAMP '2571-03-01 00:00:00', 1, '1116', 'Procedimento Comum',
            '7779', 3550308, '100')"""
    )
    con.execute(
        """CREATE TABLE dj_moves (numero_processo VARCHAR, alias VARCHAR, codigo INTEGER, nome VARCHAR,
                                  data_hora TIMESTAMP, orgao_codigo VARCHAR)"""
    )
    con.execute(
        """INSERT INTO dj_moves VALUES
           ('1', 'api_publica_tjsp', 26, 'Distribuição', TIMESTAMP '2024-01-10 09:00:00', '100'),
           ('1', 'api_publica_tjsp', 999, 'Determinada a emenda da inicial', TIMESTAMP '2024-02-01 09:00:00', '100'),
           ('1', 'api_publica_tjsp', 196, 'Extinção da execução', TIMESTAMP '2024-03-11 09:00:00', '200'),
           ('2', 'api_publica_tjsp', 26, 'Distribuição', TIMESTAMP '2025-05-05 09:00:00', '100')"""
    )
    con.execute(
        """CREATE TABLE dj_targets (numero_processo VARCHAR, alias VARCHAR, grupo VARCHAR, pub_year VARCHAR,
                                    strict_hit BOOLEAN, n_documentos INTEGER)"""
    )
    con.execute(
        """INSERT INTO dj_targets VALUES
           ('1', 'api_publica_tjsp', 'candidato', '2024', true, 2),
           ('2', 'api_publica_tjsp', 'comparacao_nao_sinalizado', '2025', false, 1),
           ('3', 'api_publica_tjsp', 'candidato', '2024', false, 1)"""
    )
    groups = load_movement_groups(write(tmp_path, CONFIG))
    con.execute(
        f"CREATE VIEW feat AS {feature_sql(groups, cases='dj_cases', movimentos='dj_moves', targets='dj_targets')}"
    )
    yield con
    con.close()


def test_features_aggregate_the_graus_and_the_movements(fixture_db):
    row = fixture_db.execute(
        """SELECT n_documentos, graus, n_orgaos_caso, n_movimentos, n_codigos_distintos, n_orgaos_movimento,
                  primeiro_movimento, ultimo_movimento, dias_entre_movimentos, dias_desde_ajuizamento,
                  n_extincao, primeiro_extincao, n_emenda, nao_encontrado_no_datajud
           FROM feat WHERE numero_processo = '1'"""
    ).fetchone()
    (docs, graus, orgaos_caso, moves, codes, orgaos_mv, first, last, span, since, n_ext, first_ext, n_em,
     missing) = row
    assert (docs, graus, orgaos_caso) == (2, "G1;G2", 2)
    assert (moves, codes, orgaos_mv) == (3, 3, 2)
    assert first == dt.datetime(2024, 1, 10, 9) and last == dt.datetime(2024, 3, 11, 9)
    assert span == 61 and since == 61  # ajuizamento 2024-01-10 00:00 -> last movement
    assert (n_ext, n_em) == (1, 1)
    assert first_ext == dt.datetime(2024, 3, 11, 9)
    assert missing is False


def test_an_impossible_ajuizamento_date_yields_null_instead_of_a_wrong_duration(fixture_db):
    # the server parses dataAjuizamento as epoch milliseconds for large result sets (feasibility §1.2): a case
    # "filed" in 2571 must not produce a negative or absurd duration
    row = fixture_db.execute(
        """SELECT dias_desde_ajuizamento, dias_entre_movimentos, n_movimentos, grupo
           FROM feat WHERE numero_processo = '2'"""
    ).fetchone()
    assert row[0] is None
    assert (row[1], row[2], row[3]) == (0, 1, "comparacao_nao_sinalizado")


def test_a_target_absent_from_datajud_is_kept_and_flagged(fixture_db):
    row = fixture_db.execute(
        """SELECT nao_encontrado_no_datajud, n_movimentos, n_extincao, data_ajuizamento
           FROM feat WHERE numero_processo = '3'"""
    ).fetchone()
    assert row[0] is True
    assert (row[1], row[2]) == (0, 0)  # counted as zero, never dropped: the denominator must stay honest
    assert row[3] is None


def test_every_target_produces_exactly_one_row(fixture_db):
    assert fixture_db.execute("SELECT count(*), count(DISTINCT numero_processo) FROM feat").fetchone() == (3, 3)


def test_overlapping_documents_of_the_same_case_do_not_multiply_the_movements(tmp_path):
    """Measured on the real collection: a case can be published as several documents of the same grau, whose
    movement lists overlap. The union must be counted once (otherwise the duration is right and the volume is
    inflated, which is the worst kind of wrong)."""
    con = duckdb.connect()
    con.execute(
        """CREATE TABLE dj_cases (numero_processo VARCHAR, alias VARCHAR, grau VARCHAR,
                                  data_ajuizamento TIMESTAMP, nivel_sigilo INTEGER, classe_codigo VARCHAR,
                                  classe_nome VARCHAR, assuntos_codigos VARCHAR, municipio_ibge INTEGER,
                                  orgao_codigo VARCHAR);
           INSERT INTO dj_cases VALUES
             ('9', 'api_publica_tjal', 'G2', TIMESTAMP '2023-09-01 00:00:00', 0, '1116', 'x', '7779', 2704302, '1'),
             ('9', 'api_publica_tjal', 'G2', TIMESTAMP '2023-09-01 00:00:00', 0, '1116', 'x', '7779', 2704302, '1')"""
    )
    con.execute(
        """CREATE TABLE dj_moves (numero_processo VARCHAR, alias VARCHAR, codigo INTEGER, nome VARCHAR,
                                  data_hora TIMESTAMP, orgao_codigo VARCHAR);
           INSERT INTO dj_moves VALUES
             ('9', 'api_publica_tjal', 26, 'Distribuição', TIMESTAMP '2023-09-06 09:06:46', '1'),
             ('9', 'api_publica_tjal', 26, 'Distribuição', TIMESTAMP '2023-09-06 09:06:46', '1'),
             ('9', 'api_publica_tjal', 196, 'Extinção da execução', TIMESTAMP '2024-01-10 09:00:00', '1'),
             ('9', 'api_publica_tjal', 196, 'Extinção da execução', TIMESTAMP '2024-01-10 09:00:00', '1'),
             ('9', 'api_publica_tjal', 456, 'Extinção', TIMESTAMP '2024-02-20 09:00:00', '2')"""
    )
    con.execute(
        """CREATE TABLE dj_targets (numero_processo VARCHAR, alias VARCHAR, grupo VARCHAR, pub_year VARCHAR,
                                    strict_hit BOOLEAN, n_documentos INTEGER);
           INSERT INTO dj_targets VALUES ('9', 'api_publica_tjal', 'candidato', '2024', true, 1)"""
    )
    groups = load_movement_groups(write(tmp_path, CONFIG))
    con.execute(
        f"CREATE VIEW feat AS {feature_sql(groups, cases='dj_cases', movimentos='dj_moves', targets='dj_targets')}"
    )
    row = con.execute(
        "SELECT n_movimentos, n_codigos_distintos, n_orgaos_movimento, n_extincao FROM feat"
    ).fetchone()
    assert row == (3, 3, 2, 2)  # five rows, three distinct movements; both extinction codes counted once each
    con.close()
