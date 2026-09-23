"""Tests for the lexicon engine and for config/lexicon_v2.yaml.

Every pattern carries one example sentence written from the wording of Annex A of Rec. CNJ 159/2024 (and from the
phase-0 readings). Three properties are checked for each: the pattern matches its own example, the single
combined regex pushed into DuckDB by step 20 also matches it (soundness of the pre-filter, otherwise the
pipeline would silently lose documents) and :func:`scan_text` reports the hit.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from alj.lexicon import (
    Lexicon,
    _to_non_capturing,
    combined_source,
    document_summary,
    hit_rows,
    hits_frame,
    load_lexicon,
    prefilter_regex,
    scan_text,
)

CONFIG = Path(__file__).resolve().parents[1] / "config" / "lexicon_v2.yaml"

EXAMPLES: dict[str, str] = {
    # strict
    "litigancia_predatoria": "Reconhecida a litigância predatória na espécie.",
    "litigancia_abusiva": "Trata-se de hipótese de litigância abusiva.",
    "advocacia_predatoria": "Há fortes indicativos de advocacia predatória no caso.",
    "litigiosidade_artificial": "Constata-se litigiosidade artificial fomentada pelo patrono.",
    "demanda_artificial": "Cuida-se de demandas artificiais, sem substrato fático.",
    "assedio_processual": "A conduta configura assédio processual contra a parte ré.",
    "judicializacao_predatoria": "Fenômeno de judicialização predatória em massa.",
    # conduct
    "gratuidade_sem_comprovacao": "Requerimento de justiça gratuita formulado sem comprovação de hipossuficiência.",
    "foro_distinto_domicilio": "Ação ajuizada em comarca distinta do domicílio da parte autora.",
    "documentos_desatualizados": "Foram juntados documentos com dados incompletos e ilegíveis.",
    "comprovante_residencia_terceiro": "Apresentou comprovante de residência em nome de terceiro.",
    "fracionamento": "Verifica-se fracionamento indevido de demandas.",
    "fracionamento_perifrase": "Foram propostas várias ações sobre o mesmo tema pela mesma autora.",
    "peticoes_padronizadas": "As petições iniciais são padronizadas e genéricas.",
    "causa_de_pedir_generica": "As causas de pedir são idênticas, sem particularização dos fatos.",
    "peticoes_padronizadas_2": None,  # placeholder removed below (kept out of the file on purpose)
    "pedidos_vagos": "Formulou pedidos vagos e hipotéticos que não guardam relação lógica com a causa de pedir.",
    "demanda_identica_sem_dependencia": "Ajuizou demanda idêntica sem menção ao processo anterior extinto.",
    "procuracao_irregular": "A procuração é genérica e sem poderes específicos para a causa.",
    "assinatura_nao_qualificada": "A assinatura eletrônica não qualificada foi lançada sem certificado ICP-Brasil.",
    "representacao_irregular": "Determinada a emenda por irregularidade na representação processual.",
    "ausencia_documentos_essenciais": "Reconhecida a ausência de documentos essenciais à propositura.",
    "concentracao_poucos_patronos": (
        "Chama atenção a concentração de grande volume de demandas sob o patrocínio de poucos profissionais."
    ),
    "captacao_indevida": "Há elementos de captação indevida de clientes pelo escritório.",
    "pressao_beneficio_extraprocessual": "A demanda serve de pressão para obter benefício extraprocessual.",
    "valor_causa_aleatorio": "Atribuiu valor da causa elevado e aleatório, sem conteúdo econômico correspondente.",
    "notificacao_extrajudicial_sem_prova": "Juntou notificação extrajudicial sem comprovação de recebimento.",
    "cessao_direito_demandar": "Foi juntado instrumento de cessão do direito de demandar.",
    "desistencia_apos_indeferimento": "Pediu desistência da ação após o indeferimento da tutela de urgência.",
    "ausencia_pretensao_resistida": "Reconhecida a ausência de pretensão resistida antes do ajuizamento.",
    # sanction
    "ma_fe_art_80": "Caracterizada a litigância de má-fé, com condenação em multa.",
    "multa_ma_fe_art_81": "Aplico a multa do art. 81 do CPC.",
    "ato_atentatorio_art_77": "A conduta constitui ato atentatório à dignidade da justiça.",
    "emenda_ou_indeferimento_inicial": "Manteve-se o indeferimento da petição inicial por falta de documento indispensável.",
    "extincao_sem_merito": "Processo extinto sem resolução do mérito por ausência de interesse.",
    "oficio_oab_ou_mp": "Determino a expedição de ofício à OAB para apuração.",
    "apuracao_indicios": "Há indícios de litigância predatória a serem apurados.",
    # normative
    "rec_cnj_159": "Nos termos da Recomendação CNJ nº 159/2024.",
    "res_cnj_615": "Aplica-se a Resolução CNJ nº 615/2025.",
    "tema_1198": "Conforme o Tema 1.198 desta Corte.",
    "numopede": "Encaminhe-se ao NUMOPEDE do tribunal de origem.",
    "rede_litigancia_abusiva": "Integra a Rede de Combate à Litigância Abusiva.",
    "art_286_ii": "Deveria ter pedido distribuição por dependência (art. 286, II, do CPC).",
    # neighbour
    "ma_fe_processual_mencao": "Não se cogita de litigância de má-fé.",
    "abuso_direito_acao": "Configura abuso do direito de ação.",
    "lide_temeraria": "Trata-se de lide temerária.",
    "recurso_protelatorio": "Recurso de caráter manifestamente protelatório.",
    "demandas_repetitivas": "Tema afetado ao rito das demandas repetitivas.",
}
EXAMPLES = {k: v for k, v in EXAMPLES.items() if v is not None}


@pytest.fixture(scope="module")
def lex() -> Lexicon:
    return load_lexicon(CONFIG)


def test_config_loads_and_is_versioned(lex: Lexicon):
    assert lex.version.startswith("2.")
    assert len(lex.patterns) >= 40
    assert lex.candidate_tiers == ("strict", "conduct", "sanction")
    assert lex.window == (320, 320)


def test_annex_a_references_are_valid(lex: Lexicon):
    for p in lex.patterns:
        assert all(1 <= i <= 20 for i in p.annex_a), p.id
        if p.tier == "conduct":
            assert p.annex_a, f"{p.id} is a conduct pattern with no Annex A item"


def test_every_pattern_has_an_example(lex: Lexicon):
    ids = {p.id for p in lex.patterns}
    assert ids == set(EXAMPLES), f"missing: {sorted(ids - set(EXAMPLES))}; extra: {sorted(set(EXAMPLES) - ids)}"


@pytest.mark.parametrize("pattern_id", sorted(EXAMPLES))
def test_pattern_matches_its_example(lex: Lexicon, pattern_id: str):
    assert lex.by_id(pattern_id).regex.search(EXAMPLES[pattern_id]), pattern_id


@pytest.mark.parametrize("pattern_id", sorted(EXAMPLES))
def test_prefilter_is_sound(lex: Lexicon, pattern_id: str):
    """No document that a candidate-tier pattern would hit may be dropped by the DuckDB pre-filter."""
    if lex.by_id(pattern_id).tier not in lex.candidate_tiers:
        pytest.skip("only candidate tiers go through the pre-filter")
    assert prefilter_regex(lex).search(EXAMPLES[pattern_id]), pattern_id


@pytest.mark.parametrize("pattern_id", sorted(EXAMPLES))
def test_scan_text_reports_the_hit(lex: Lexicon, pattern_id: str):
    hits = scan_text(EXAMPLES[pattern_id], lex)
    assert pattern_id in {h.pattern_id for h in hits}, [h.pattern_id for h in hits]


def test_combined_source_is_re2_safe(lex: Lexicon):
    src = combined_source(lex)
    assert "(?P<p_litigancia_predatoria>" in src
    # no backreference and no lookaround: RE2 rejects both
    assert "(?=" not in src and "(?!" not in src and "(?<" not in src
    assert not any(f"\\{d}" in src for d in "123456789")


def test_to_non_capturing_keeps_classes_and_escapes():
    assert _to_non_capturing(r"(a|b)") == r"(?:a|b)"
    assert _to_non_capturing(r"[(]") == r"[(]"
    assert _to_non_capturing(r"\(") == r"\("
    assert _to_non_capturing(r"(?:x)(?P<n>y)") == r"(?:x)(?P<n>y)"


def test_exclusion_drops_the_financial_false_friend(lex: Lexicon):
    text = "O laudo apurou o custo de captação de recursos e a captação indevida de clientes não foi objeto."
    hits = scan_text(text, lex)
    captacao = [h for h in hits if h.pattern_id == "captacao_indevida"]
    assert captacao and captacao[0].excluded_by == "captacao_financeira"
    assert not any(h.kept and h.pattern_id == "captacao_indevida" for h in hits)


def test_exclusion_does_not_fire_without_the_false_friend(lex: Lexicon):
    hits = scan_text("Houve captação indevida de clientes na porta do hospital.", lex)
    assert [h for h in hits if h.pattern_id == "captacao_indevida"][0].kept


def test_negation_marker_sets_the_hint(lex: Lexicon):
    hits = scan_text("Não há litigância predatória configurada nos autos.", lex)
    assert [h for h in hits if h.pattern_id == "litigancia_predatoria"][0].negated_hint


def test_document_summary_aggregates(lex: Lexicon):
    text = (
        "Reconhecida a litigância predatória: as petições iniciais são padronizadas e genéricas, "
        "e a procuração é genérica e sem poderes específicos, nos termos da Recomendação CNJ nº 159/2024"
    )
    hits = scan_text(text, lex)
    row = document_summary(42, "20250611", hits, lex)
    assert row["is_candidate"] and row["strict_hit"] and row["conduct_hit"] and row["normative_hit"]
    assert row["negated_all"] is False
    assert row["n_patterns"] >= 3 and row["lexicon_version"] == lex.version
    assert "7" in row["annex_a_items"].split(";")
    frame = hits_frame(hit_rows(42, "20250611", hits))
    assert frame.height == len(hits)
    assert frame["context"].str.contains("litigância predatória").any()


def test_summary_of_a_document_with_only_neighbour_hits_is_not_a_candidate(lex: Lexicon):
    hits = scan_text("Tema afetado ao rito das demandas repetitivas e recurso protelatório.", lex)
    row = document_summary(1, "k", hits, lex)
    assert row["is_candidate"] is False and row["neighbour_hit"] is True


def test_negated_all_flags_rejected_allegations(lex: Lexicon):
    hits = scan_text("Afastada a alegação de litigância predatória, pois inexistência de provas.", lex)
    row = document_summary(1, "k", hits, lex)
    assert row["is_candidate"] and row["negated_all"]


def test_max_hits_per_pattern_is_respected(lex: Lexicon):
    text = " ".join(["litigância predatória reconhecida"] * 10)
    hits = [h for h in scan_text(text, lex) if h.pattern_id == "litigancia_predatoria"]
    assert len(hits) == lex.max_hits_per_pattern


def test_loader_rejects_duplicates_and_unknown_tiers(tmp_path: Path):
    dup = tmp_path / "dup.yaml"
    dup.write_text(
        "version: 9\npatterns:\n  - {id: a, tier: strict, regex: 'x'}\n  - {id: a, tier: strict, regex: 'y'}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_lexicon(dup)

    bad = tmp_path / "bad.yaml"
    bad.write_text("version: 9\npatterns:\n  - {id: a, tier: whatever, regex: 'x'}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown tier"):
        load_lexicon(bad)

    orphan = tmp_path / "orphan.yaml"
    orphan.write_text(
        "version: 9\npatterns:\n  - {id: a, tier: strict, regex: 'x'}\n"
        "exclusions:\n  - {id: e, regex: 'y', applies_to: [zzz]}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown pattern"):
        load_lexicon(orphan)


def test_yaml_documents_every_source_norm():
    raw = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert any("159" in s for s in raw["source_norms"])
    assert any("1198" in s for s in raw["source_norms"])
