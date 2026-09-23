# Registro de uso de IA neste repositório

Exigido pela política do portfólio (`docs/AI_POLICY_AND_REPRODUCIBILITY.md` §§2 e 5) e pelo `CLAUDE.md` §12.
Toda ferramenta de IA usada em qualquer etapa entra aqui, com data, finalidade, o que **entrou**, o que **saiu**
e o que foi feito com a saída. É deste arquivo que sai a declaração de IA do artigo (`article/ai_disclosure.tex`).

Regra que nenhum registro pode contrariar: **IA não produz rótulo**. Rótulo só vem da revisão manual do
pesquisador (`docs/annotation_protocol.md`; `CLAUDE.md` §2).

---

## 1. Claude Code (Anthropic) — desde 2026-09-05, contínuo

- **Finalidade:** escrever e testar código, SQL, configuração, documentação e runbook; nunca prosa do manuscrito
  (`CLAUDE.md` §11).
- **Entrada:** o repositório, os dados abertos baixados e as instruções do pesquisador.
- **Saída:** `scripts/`, `src/alj/`, `tests/`, `docs/`, `config/lexicon_v2.yaml`, `dodo.py`.
- **Verificação:** 224 testes automatizados, `ruff` limpo, todo número do manuscrito gerado por
  `scripts/80_build_outputs.py` + `scripts/90_export_overleaf.py`.

## 2. Jus IA (Jusbrasil) — 2026-09-22, uso pontual, na conta do pesquisador

- **Finalidade:** levantamento de **jurisprudência e critérios**, para descobrir o que os tribunais usam na
  prática e que a Recomendação CNJ 159/2024 não enuncia. Não foi usada para classificar, rotular ou analisar
  documento algum do corpus.
- **Perguntas feitas (duas, registradas na íntegra):**
  1. *"Quais critérios objetivos os tribunais brasileiros têm usado para reconhecer litigância predatória ou
     abusiva, e quais precedentes do STJ e dos Tribunais de Justiça firmaram esses critérios? Cite os julgados."*
  2. *"Além da Recomendação CNJ 159/2024 e da Resolução CNJ 615/2025, quais atos normativos, súmulas de tribunais
     estaduais e enunciados administrativos tratam de litigância predatória ou abusiva no Brasil? Liste com
     número, órgão e ano."*
- **O que entrou:** apenas essas duas perguntas. **Nenhuma decisão, trecho, metadado ou tabela do corpus foi
  enviada** ao serviço.
- **Primeira resposta (critérios e precedentes):** dez critérios, o Tema 1198/STJ, cinco acórdãos do STJ (REsp 2.271.437/SP,
  REsp 2.262.169/PI, AREsp 3.108.019/SC, REsp 2.238.236/SP, AREsp 2.632.271/PR), quatro julgados do TJSP e as
  Súmulas 46 e 54 do TJBA.
- **O que foi feito com a saída — e este é o ponto:** ela **não entrou no artigo como afirmação**. Cada item foi
  tratado como hipótese e conferido no nosso próprio corpus:
  - REsp 2.262.169/PI: localizado, com texto; o léxico v2.0 já o marcava (19 acertos, termo estrito +
    `procuracao_irregular` + `tema_1198` + `emenda_ou_indeferimento_inicial` + `extincao_sem_merito`);
  - REsp 2.271.437/SP, AREsp 3.108.019/SC e AREsp 2.632.271/PR: presentes no corpus **sem texto** — casos
    concretos do buraco de cobertura de 2026 (27,8 %, §10 do relatório), que passam a ilustrar essa limitação;
  - REsp 2.238.236/SP: não localizado pelo campo `processo` (conferir rótulo da classe antes de citar);
  - os cinco critérios ausentes do léxico foram **medidos neste corpus** (2024–2026) antes de virarem padrão:
    `autenticidade da postulação` 314 documentos, `firma reconhecida` 814, `prévio requerimento administrativo`
    2.919, `desconhecimento da ação/do advogado` 414, `Súmulas 46/54 do TJBA` 19.
- **Segunda resposta (atos normativos):** Diretriz Estratégica 7/CNJ (2023), Comunicados CG 02/2017 e 424/2024
  da CGJ-TJSP (NUMOPEDE), Enunciados EPM/CGJ-TJSP 4, 5, 9 e 15 (2024), Portaria CGJ-TJPB 02/2019 (NUMPEDE),
  Ato TRT21-GP 228/2023, Súmulas 46 e 54 do TJBA. O próprio serviço ressalvou que confirmou os números por
  acórdãos, sem devolver o texto integral autônomo dos comunicados e enunciados.
- **Cada item foi medido neste corpus antes de virar padrão — e a medição derrubou parte da lista:**

  | instrumento sugerido | documentos no corpus (2021–2026) | decisão |
  |---|---|---|
  | Comunicado CG (CGJ-TJSP / NUMOPEDE) | 309 | **aceito** (`comunicado_cg_tjsp`) |
  | NUMPEDE (grafia do TJPB) | 43 | **aceito** (ampliou `numopede`, que sozinho dava 890) |
  | Súmulas 46/54 do TJBA | 1 (forma restrita) / 19 (forma ampla, com ruído de outros TJs) | **aceito restrito**, por precisão |
  | Diretriz Estratégica 7/CNJ | 2 | **descartado** (irrelevante neste corpus) |
  | Enunciados EPM/CGJ-TJSP | 0 | **descartado** |
  | Ato TRT21-GP 228/2023 | 0 | **descartado** (matéria trabalhista, fora do corpus) |

- **Efeito no instrumento:** léxico **v2.2.0** (53 padrões), com sete padrões novos ou ampliados
  (`autenticidade_postulacao`, `firma_reconhecida`, `requerimento_administrativo_previo`,
  `desconhecimento_da_acao`, `sumula_tjba_predatoria`, `comunicado_cg_tjsp` e `numopede` ampliado), cada um com
  exemplo asseverado em `tests/test_lexicon.py`. A validação continua a mesma: precisão/revocação contra o
  padrão-ouro anotado pelo pesquisador.
- **Limites reconhecidos:** produto fechado, sem versão fixável, sem seed e sem temperatura controlável; suas
  citações não são fonte — são pista a conferir no inteiro teor (o próprio serviço adverte isso). Por isso ele
  **não** integra o método, não gera número do artigo e não aparece na seção de Métodos como instrumento; entra
  apenas nesta declaração, como ferramenta de pesquisa bibliográfica/jurisprudencial.

### Redação sugerida para a declaração do artigo (o autor decide se mantém)

> Para o levantamento de critérios jurisprudenciais e de atos normativos foi consultada uma ferramenta comercial
> de pesquisa jurídica assistida por IA (Jus IA, Jusbrasil), em 22/09/2026, em duas consultas de escopo
> bibliográfico. Nenhum documento do corpus foi submetido à ferramenta e nenhuma classificação por ela produzida
> foi utilizada. Cada julgado e cada ato indicados foram conferidos nas fontes primárias e medidos no próprio
> corpus; os que não se confirmaram foram descartados. Os critérios confirmados foram incorporados ao léxico
> (instrumento de medida versionado), cuja acurácia é reportada contra anotação humana.

---

## 3. O que **não** foi usado

- Nenhuma API paga de LLM (a política exige autorização escrita do pesquisador; não houve).
- Nenhum modelo — local ou remoto — produziu rótulo, medida ou número deste artigo até 2026-09-22.

## 4. GPT SciSpace (OpenAI/ChatGPT, na conta do pesquisador) — 2026-09-23

- **Finalidade:** levantamento de literatura (revisão bibliográfica), a pedido do pesquisador. Não classificou,
  não rotulou e não analisou documento algum do corpus.
- **O que entrou:** um prompt de seis blocos descrevendo o desenho do artigo (sem dado nenhum do corpus), com
  autores-âncora por bloco e regras anti-alucinação. Texto integral em
  `docs/prompts/scispace_revisao_literatura.md` (Prompt A) — reproduzível.
- **O que saiu:** mapa dos seis blocos, tabela de obras com DOI, tabela de livros e três lacunas.
- **Verificação (obrigatória, feita aqui):** `scripts/91_verify_references.py` consultou o Crossref/DataCite para
  cada DOI — **16 sugeridos, 16 resolvidos, 0 inventados, 0 com título divergente**
  (`logs/91_verify_references.json`). Só o que resolveu entrou em `notes/references_candidates.bib`, e nada
  entra em `article/references.bib` sem aprovação do pesquisador.
- **Limites honestos da ferramenta, registrados:**
  1. ela **se recusou** a contar recorrência de livros nas listas de referências, dizendo que não as recuperou
     completas e que não produziria contagens sem inspecioná-las — daí a tabela de livros brasileiros vazia;
  2. na rodada brasileira ela avisou que o recuperador de texto integral **contaminou contexto entre registros**
     (atribuiu trechos de um artigo sobre demandas predatórias a outros trabalhos) e, por isso, passou a usar
     apenas metadados/abstracts verificáveis. **Consequência: as citações internas que ela relata — quem cita
     quem — não são confiáveis;** os metadados dos artigos, esses foram confirmados por DOI no Crossref;
  3. ela declarou não ter recuperado registros completos de FGV, IPEA, Insper e ABJ, classificando isso como
     **lacuna de recuperação, não ausência da literatura** — esses relatórios exigem busca direta. A contagem de livros exige outra fonte (OpenAlex/Scopus) ou
  leitura direta das listas — está registrado em `docs/literature_map.md` §2.
- **Efeito no artigo:** nenhuma prosa de IA entra no manuscrito (CLAUDE.md §11). A resposta da rodada brasileira
  inclui quatro parágrafos propondo *como enunciar a lacuna*; esse texto foi deliberadamente **não copiado** para
  o repositório e está sinalizado em `docs/literature_map.md` §12 como material que o autor não deve reaproveitar,
  nem parafraseado. O que entra é insumo bibliográfico verificado e o registro das lacunas.
- **Resultado consolidado das duas rodadas:** 28 DOIs sugeridos, **27 resolvidos, 1 não resolvido**
  (`10.31501/ealr.v10i2.9637`, em quarentena), **0 inventados**. O mapa está em `docs/literature_map.md`, com a
  lista fechada de "não verificado — não citar" na §11.
