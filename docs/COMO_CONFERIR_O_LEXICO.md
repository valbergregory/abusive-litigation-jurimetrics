# Como conferir o léxico v2.2 — passo a passo (item D-5)

Objetivo: você olhar o que o instrumento realmente captura e decidir se algum padrão entra, sai ou fica mais
estrito — **antes** de começar a anotar. Depois da anotação, mexer no léxico obriga a refazer tudo.

Tempo: **30 a 45 minutos** para uma conferência honesta. Não precisa olhar os 53 padrões; a §3 abaixo diz quais.

---

## 1. Ver o retrato geral (2 minutos)

```bash
uv run python scripts/26_inspect_pattern.py --all
```

Sai uma tabela com todos os padrões que têm ≥ 5 documentos: quantos documentos e acertos cada um tem, quanto por
cento das janelas parece negação ("afastada a alegação…") e quantos acertos foram derrubados por exclusão.

O topo hoje é:

| padrão | camada | documentos |
|---|---|---|
| `extincao_sem_merito` | sanção | 63.275 |
| `representacao_irregular` | conduta | 33.506 |
| `ma_fe_processual_mencao` | vizinha | 21.409 |
| `ma_fe_art_80` | sanção | 13.744 |
| `demandas_repetitivas` | vizinha | 12.974 |

Isso é esperado: a camada de conduta traduz o Anexo A em linguagem processual comum, e a camada vizinha existe
só para ser medida e subtraída — ela **não** cria candidato. Mas é exatamente aqui que você decide se quer um
instrumento mais estreito.

## 2. Ler o que um padrão realmente casou (o essencial)

```bash
uv run python scripts/26_inspect_pattern.py litigancia_predatoria --sample 10
```

Para cada acerto sorteado (semente fixa, então repete igual) ele mostra o `doc_id`, o trecho que casou e a
janela de contexto, marcando `[NEGADO]` quando parece rejeição e `[EXCLUÍDO: …]` quando um falso amigo derrubou.

Variações úteis:

```bash
uv run python scripts/26_inspect_pattern.py extincao_sem_merito --sample 10 --year 2025
uv run python scripts/26_inspect_pattern.py litigancia_predatoria --negated --sample 6   # só as rejeições
uv run python scripts/25_show_document.py 20210208-120488078 --marks                      # decisão inteira
```

A pergunta a fazer em cada trecho é uma só: **isso é o que o padrão deveria capturar?** Não é "isso é litigância
predatória?" — essa é a pergunta da anotação, não da conferência do instrumento.

## 3. Os sete padrões que eu pediria para você olhar

Cinco entraram ontem, vindos do levantamento na Jus IA e medidos no corpus antes de entrar; dois são os que mais
inflam o conjunto de candidatos.

| padrão | documentos | por que olhar |
|---|---|---|
| `autenticidade_postulacao` | 314 | é a fórmula literal do Tema 1198; confirme que casa com a exigência de emenda, não com outra coisa |
| `firma_reconhecida` | 2.469 | classifiquei como **sanção** (é a medida imposta); veja se concorda ou se é conduta |
| `requerimento_administrativo_previo` | 6.954 | interesse de agir; pode estar pegando previdenciário/securitário comum |
| `desconhecimento_da_acao` | 934 | "a parte desconhecia a ação ou o advogado" — indício forte na prática |
| `comunicado_cg_tjsp` | 337 | Comunicados CG da Corregedoria paulista (NUMOPEDE) |
| `extincao_sem_merito` | 63.275 | **o maior de todos**: decide se a camada de sanção fica ampla assim |
| `representacao_irregular` | 33.506 | idem, para a camada de conduta |

Sugestão de roteiro: `--sample 10` em cada um dos cinco primeiros (≈ 20 min) e `--sample 15 --year 2025` nos
dois últimos (≈ 15 min).

## 4. O que fazer com o que você achar

Me diga em uma linha por padrão. As decisões possíveis são quatro:

1. **manter** como está;
2. **restringir** — ex.: `extincao_sem_merito` só quando vier acompanhado de documento/emenda na mesma frase;
3. **mudar de camada** — ex.: `firma_reconhecida` de sanção para conduta;
4. **remover** — o padrão não mede nada útil.

Eu aplico em `config/lexicon_v2.yaml`, atualizo o exemplo asseverado em `tests/test_lexicon.py`, rodo a varredura
completa (≈ 46 min) e regero a planilha **com a mesma semente**, para as amostras continuarem comparáveis.

## 5. O que **não** precisa conferir

- **Cobertura de 2026** — já decidido: usar só até 2025 (texto de 2026 tem 27,8 % de cobertura).
- **Camada vizinha** (`ma_fe_processual_mencao`, `demandas_repetitivas`, `abuso_direito_acao`, `lide_temeraria`,
  `recurso_protelatorio`) — ela nunca cria candidato; serve para medir e separar o conceito vizinho.
- **Exclusões** — as quatro foram medidas: `irdr_machinery` derrubou 991 acertos e `captacao_financeira` 142,
  exatamente os falsos amigos que a fase 0 previu.

## 6. Se você preferir não conferir agora

É legítimo: o léxico é um **instrumento de medida**, não um rótulo, e o que ele erra aparece na precisão medida
contra o seu padrão-ouro. O risco de adiar é só um — se você mudar o léxico **depois** de anotar, a amostra muda
e parte da anotação se perde. Por isso o pedido de olhar agora.
