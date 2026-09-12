# Relatório de viabilidade — fase 0

**Projeto:** *Detecting Patterns of Abusive Litigation: An Explainable and Human-Centered Jurimetric Framework*
**Data da sondagem:** 04–05/09/2026. **Autor da sondagem:** Claude Code, sob direção de Valber.
**Escopo:** só viabilidade. Nada foi modelado, rotulado ou inferido. Todos os números abaixo vêm de arquivos baixados e consultas executadas nesta sessão (scripts em `scripts/00–02`, hashes em `logs/raw_hashes.tsv`).

---

## 0. Decisão de linguagem: Python + SQL (DuckDB), sem R no núcleo

**Recomendação: fazer o projeto só em Python + SQL.** Motivos verificados, não opinativos:

1. **Toda a cadeia de dados é nativa em Python.** CKAN/JSON/ZIP do STJ, Elasticsearch do DataJud, texto com `<br>`, embeddings em GPU (RTX 4060, 8 GB), grafos, PU learning, anomalia, SHAP. Nenhuma dessas etapas tem vantagem em R.
2. **A parte estatística que o projeto exige existe em Python sem perda:** calibração (`scikit-learn`, `netcal`), regressão regularizada, GLMM (`statsmodels.MixedLM`), séries temporais (`statsmodels`), econometria espacial (`pysal/spreg`, `esda`), testes de robustez. Onde R seria melhor (`lme4` com efeitos cruzados complexos, `spdep` LISA), o ganho é marginal para o desenho previsto e pode ir a um apêndice opcional a partir de Parquet.
3. **Custo real de duas linguagens para um pesquisador só:** dois gerenciadores de ambiente (`renv` + `uv`), `reticulate` ou Parquet como cola, dois conjuntos de testes, dois logs, dois caminhos de reprodução para o revisor. Isso é onde projetos solo quebram.
4. **Ambiente atual favorece Python:** Quarto 1.9.38 instalado (renderiza Python via Jupyter, que falta instalar); `uv` não instalado, mas disponível no PyPI; `duckdb`, `polars`, `scikit-learn`, `sentence-transformers`, `networkx`, `igraph`, `pyarrow` todos disponíveis. R 4.4.3 tem `tidyverse`, `tidymodels`, `targets`, `renv`, mas não tem `arrow`, `sf`, `spdep`, `quanteda`, `tidytext`, `probably`.
5. **Consistência com a decisão de 04/09** (portfólio jurídico: artigo 5 = Python-only).

**O que muda em relação ao briefing original:** `renv` e `targets` saem; entram `uv` (ambiente e lockfile) e um DAG em Python (`doit` ou `snakemake`; recomendo `doit` por rodar limpo no Windows). "Background Jobs no RStudio" vira `Start-Job`/`Start-Process` no PowerShell ou `run_in_background` no Claude Code. SQL fica **DuckDB** (arquivo único, Parquet nativo, extensões `fts` e `vss` para texto e vetores). PostgreSQL + pgvector só se o painel de pesquisa precisar de multiusuário, o que hoje não é o caso.

---

## 1. Campos realmente disponíveis (confirmados por download)

### 1.1 STJ — Portal de Dados Abertos (CKAN, `dadosabertos.web.stj.jus.br`)

| Dataset | Cobertura | Volume | Campos confirmados |
|---|---|---|---|
| **Íntegras de decisões terminativas e acórdãos do DJ** | diário desde 04/01/2021 (1.244 ZIPs diários + 3 mensais) | 11,2 GB de ZIPs; 1.800–4.600 documentos/dia; texto mediano 11 KB | `SeqDocumento`, `dataPublicacao`, `tipoDocumento` (DECISÃO/ACÓRDÃO), `numeroRegistro`, `processo` (sigla + nº STJ), `dataRecebimento`, `dataDistribuição`, `NM_MINISTRO`, `recurso`, `teor`, `descricaoMonocratica`, `assuntos` (códigos CNJ). Texto UTF-8 com `<br>`. **Contém nomes de partes.** |
| **Espelhos de acórdãos** (10 órgãos: CE, S1–S3, T1–T6) | mensal desde 05/2022 + carga inicial | 511 MB JSON + 461 MB ZIP; **≈180 mil acórdãos** (estimativa por bytes/registro) | `id`, `numeroProcesso`, `numeroRegistro`, `siglaClasse`, `nomeOrgaoJulgador`, `ministroRelator`, `ementa`, `decisao`, **`jurisprudenciaCitada`** (texto parseável: `<<REsp 1816742>>`), **`referenciasLegislativas`** (lista), `acordaosSimilares`, `notas`, `termosAuxiliares`, `tema`, `teseJuridica`, `dataDecisao`, `dataPublicacao` |
| **Acervo em tramitação** | foto diária (02/09/2026) | 333.650 processos pendentes | **`numeroUnico` (CNJ) ↔ `numeroRegistro`**, `siglaClasse`, `codigoClasseCNJ`, `codigoAssuntoCNJ`, `codigoOrgaoJulgador`, `nomeMinistroRelator`, `segredoJustica`, `sobrestado` |
| **Atas de distribuição** | diário desde 30/06/2023 (1.005 arquivos) | 4,16 GB | **`numeroUnico` ↔ `numeroRegistro`**, classe (STJ e CNJ), `codigoAssuntoCNJ`, órgão, relator, forma de distribuição e **`partes[]` (tipo, nome, CNPJ) com `advogados[]` (código OAB, nome)** |
| **Precedentes qualificados** | íntegro | 2.400 temas/controvérsias + processos | `numeroPrecedente`, datas de afetação/julgamento/publicação, `situacao`, `questaoSubmetidaAJulgamento`, `teseFirmada`, assuntos. **Tema 1198** presente: afetado 09/05/2023, julgado 13/03/2025, acórdão publicado 11/06/2026; tese: *"Constatados indícios de litigância abusiva, o juiz pode exigir, de modo fundamentado (...) a emenda da petição inicial a fim de demonstrar o interesse de agir e a autenticidade da postulação"*. |

**Alerta de qualidade (íntegras):** a cobertura de texto cai em 2026. Dias sondados: 2021–2025 com 97–99% dos metadados acompanhados do TXT; 11/03/2026: 17 de 4.648; 25/08/2026: 228 de 1.845; 26/08/2026: 412 de 2.285. Acórdãos praticamente sem texto em 2026. Hipóteses: atraso de carga ou mudança de rotina. **Precisa ser verificado** antes de qualquer análise de 2026 (checar se os `SeqDocumento` faltantes aparecem em ZIPs posteriores).

### 1.2 CNJ — API Pública do DataJud

- Autenticação com a chave pública publicada na wiki (funcionou; a chave pode rodar, por isso o script lê a wiki a cada execução). 64 endpoints (`api_publica_stj`, `api_publica_tjsp`, …).
- **Campos por processo:** `numeroProcesso` (CNJ, 20 dígitos), `tribunal`, `grau` (G1/G2/JE/TR/SUP), `dataAjuizamento` (string de 14 dígitos), `nivelSigilo`, `orgaoJulgador{codigo, nome, codigoMunicipioIBGE}`, `classe{codigo,nome}`, `assuntos[]`, `sistema`, `formato`, `movimentos[]{codigo, nome, dataHora, complementosTabelados[], orgaoJulgador}`, `dataHoraUltimaAtualizacao`. **Não há partes nem advogados**, como esperado.
- **Alerta de qualidade 1 (datas):** agregações e filtros de servidor sobre `dataAjuizamento` são inconfiáveis. Para milhões de documentos o Elasticsearch interpreta a string como epoch e devolve anos como 2571–2612 (STJ: 1,0 milhão de 3,6 milhões; TJMG/TJBA/TJGO/TJAL/TJCE/TJPR: 100%). O campo bruto está correto (`20221022085739`). **Solução:** filtrar por `movimentos.dataHora` (ISO) e converter `dataAjuizamento` no cliente.
- **Alerta de qualidade 2 (município):** `codigoMunicipioIBGE` disponível na maioria dos TJs (TJMG 832 municípios, TJPR 167, TJRS 165, TJCE 132, TJPE 132, TJRJ 82), mas **ausente em 92% do TJAL** e em quase todo o estoque antigo do TJSP (documentos recentes do TJSP já trazem). O nome do órgão contém a comarca, o que permite recuperação parcial.
- Paginação: `size` ≤ 10.000 por página; usar `search_after`. Sem limite documentado de requisições, mas sem SLA.

### 1.3 CNJ — atos normativos e institucionais (baixados e convertidos para texto)

- **Recomendação CNJ 159/2024** (PDF, 6 p.): art. 1º define litigância abusiva (gênero) e predatória (espécie); **Anexo A** lista **20 condutas** observáveis (itens 4, 6, 7, 10, 11, 13, 16 são operacionalizáveis com metadados e texto); Anexo B (17 medidas judiciais) e Anexo C (8 medidas para tribunais, inclusive "sistemas de inteligência de dados" e "alertas aos magistrados").
- **Resolução CNJ 615/2025** (alterada pela Res. 674/2026): governança de IA no Judiciário; fundamenta as salvaguardas (supervisão humana, transparência, registro, não discriminação).
- **Rede de Informações sobre Litigância Abusiva:** o "Banco de Decisões | Notas Técnicas" é um painel Qlik (`paineisanalytics.cnj.jus.br`), sem API pública; há painéis Power BI por tribunal (TJSP/NUMOPEDE, TJPA, TJMS, TRF2). Úteis como contexto e fonte de validação qualitativa, **não como base tabular**.
- **Berna** (notícia de 09/03/2026): 30 milhões de processos, 2,5 milhões sinalizados, 353 mil grupos. Contexto institucional; nenhum acesso presumido.
- **Tabelas Processuais Unificadas (SGT):** `assuntos.csv` (5.601 linhas), `classes.csv` (849), `movimentos.csv` (964) baixadas.

---

## 2. Amostra obtida

- 9 dias de íntegras (2021-06-15, 2022-06-15, 2023-06-14, 2024-06-12, 2024-11-13, 2025-06-11, 2026-03-11, 2026-08-25, 2026-08-26): ≈ 12.600 textos e ≈ 20.000 metadados.
- 1 mês de espelhos da 3ª Turma (arquivo 20260630: 4.162 acórdãos).
- Acervo em tramitação completo (333.650) e 1 ata de distribuição.
- 2 documentos de amostra por endpoint DataJud (STJ, TJSP) e agregações em 11 tribunais.

---

## 3. Estimativa do volume de decisões explicitamente sinalizadas

Varredura por expressões regulares em 6 dias com texto completo (≈ 12.600 documentos):

| Expressão | Ocorrências/dia (faixa) | Leitura |
|---|---|---|
| "litigância predatória", "advocacia predatória", "litigância abusiva" | 0–4 | quase nulas em 2021; aparecem a partir de 2024 |
| "abuso do direito de ação/litigar" | 1–5 | inclui reiteração de HC (criminal), não só massificação |
| "captação indevida/de clientes" | 0–2 | **falso positivo frequente**: "custo de captação de recursos" |
| "procuração irregular/falsa/sem poderes" | 0–2 | mistura direito material (negócio jurídico) |
| "fracionamento de demandas/pedidos" | 0–1 | |
| "litigância de má-fé" | 26–77 | conceito vizinho, não equivalente |
| "demandas repetitivas" | 7–11 | **ruído puro** (IRDR); descartar |

Nos espelhos (3ª Turma, 1 mês de 2026): 14 acórdãos com termo estrito em 4.162 (**0,34%**), vários com o termo já no cabeçalho da ementa ("LITIGÂNCIA PREDATÓRIA. IRREGULARIDADE DE REPRESENTAÇÃO…"). "Litigância de má-fé": 50.

**Extrapolação (ordem de grandeza, não contagem):**
- Íntegras 2021–2025 (≈ 1.250 dias): **≈ 1.000–3.000 decisões** com termo estrito ou "abuso do direito de ação", concentradas em 2024–2025 (efeito Tema 1198 e Rec. 159).
- Espelhos 2022–2026 (≈ 180 mil acórdãos): **≈ 300–700 acórdãos** com termo estrito.
- **Precisão do gatilho lexical é baixa.** Nas leituras feitas: um "advocacia predatória" era preliminar *afastada* e mera alegação; um "captação" era finanças. Estimativa prudente: **30–50% dos candidatos sobrevivem à revisão jurídica** como "ocorrência fundamentada". Logo, a classe "judicialmente sinalizado" deve ficar entre **algumas centenas e ~1.500 documentos**, com gradação de intensidade.

Isso é **suficiente** para modelos tabulares/textuais supervisionados e PU learning no nível documento e para grafos de padrões. É **insuficiente** para GNNs treinadas do zero e para inferência sobre atores.

---

## 4. Ligação com metadados (DataJud)

**A ponte existe e foi testada ponta a ponta (5/5):**

`íntegras.numeroRegistro` → `acervo/atas.numeroUnico` → `DataJud STJ.numeroProcesso` → `DataJud <tribunal de origem>.numeroProcesso` (mesmo número CNJ).

Exemplos resolvidos: REsp 2284584 → TJSP G2 (Apelação, plano de saúde, 28 movimentos); RHC 243517 → TJPA G2 (HC criminal, município 1501402, 29 movimentos); EREsp 2115732 → TRF5 G2 (280 movimentos); REsp 2276248 → TRF1 G1 + G2.

**Limite da ponte:** o acervo é uma foto (só pendentes): cobre 88–93% das decisões publicadas em ago/2026, 17% de mar/2026, 3,5% de jun/2025 e 1,1% de jun/2024. Para o histórico, as **atas de distribuição** cobrem tudo o que foi distribuído desde 30/06/2023. Processos distribuídos antes disso e já baixados **não têm ponte pública** (só via consulta processual, fora do escopo). Consequência: o núcleo ligável é **decisões cujo processo foi distribuído no STJ a partir de 30/06/2023**, exatamente o período em que o fenômeno aparece nos textos.

---

## 5. Três desenhos possíveis

### Desenho A — conservador: corpus de sinalização judicial no STJ (documento como unidade)
- **Dados:** íntegras + espelhos (2021–2025/26), SGT.
- **Rótulo:** candidatos por léxico → revisão jurídica manual → taxonomia (fundamento por item do Anexo A da Rec. 159; intensidade: menção / indício reconhecido / medida imposta / sanção).
- **Comparação:** decisões da mesma classe, assunto, órgão e trimestre sem sinalização (não chamadas de "legítimas").
- **Modelos:** regras transparentes (Anexo A), regressão logística regularizada, GBM sobre TF-IDF/embeddings + metadados; Isolation Forest e LOF como contraste; PU learning; SHAP e explicações locais.
- **Grafos:** só de padrões: decisão–assunto–dispositivo legal–precedente citado (espelhos), similaridade textual entre decisões.
- **Validação:** divisão temporal e por grupo documental (decisões "carimbo" de mesmo gabinete).
- **Responde:** RQ1, RQ2, RQ5; RQ6 só por órgão/período. Não responde bem RQ4 nem transferência entre tribunais.
- **Risco jurídico:** baixo. **Novidade científica:** moderada.

### Desenho B — intermediário: sinalização judicial + trajetória processual (recomendado)
- Tudo do A **+** ponte para o DataJud (STJ e tribunal de origem) para casos distribuídos a partir de 30/06/2023 e para a amostra de comparação pareada.
- **Atributos novos:** sequência e ritmo de movimentos, duração por fase, classe/assunto/órgão/comarca de origem, redistribuições, formato, densidade de casos similares na mesma unidade e período; normalização por população/renda (IBGE) por município quando disponível.
- **Grafos de padrões processuais:** processo–assunto–órgão–comarca–período–padrão textual–sequência de movimentos; arestas por similaridade de trajetória e de texto; detecção de comunidades; features de grafo alimentam os modelos tabulares (RQ3).
- **Validação:** temporal + fora do tribunal de origem (treinar em TJSP/TJRJ, testar em TJMG/TJRS…), fairness por território e classe (RQ6), custo ponderado de falsos positivos por perfil de litigante (RQ4).
- **Risco jurídico:** baixo a médio (só metadados públicos e texto público, sem pessoas nas features).
- **Custo extra:** ingestão das 1.005 atas (4 GB) e ~milhares de consultas DataJud paginadas.

### Desenho C — avançado: camada de atores com identificadores hasheados (só exploratório)
- Tudo do B **+** camada bipartida processo–advogado(OAB)–parte(CNPJ) extraída das atas de distribuição (público oficial, desde 30/06/2023), com **hash salgado** (salt fora do repositório), agregação mínima (k ≥ 5), sem nomes em qualquer saída, sem ranking.
- **Uso:** apenas testar se features de concentração (Anexo A, itens 6 e 13) acrescentam poder explicativo aos grafos de padrões, reportando efeito agregado. GNN só se houver ganho justificado sobre o B e volume suficiente, o que a estimativa do §3 sugere que **não** haverá.
- **Risco jurídico:** alto (LGPD, finalidade, Res. 615, proibições do próprio protocolo). Exige protocolo ético documentado antes de qualquer execução.

---

## 6. Riscos jurídicos e de validade

**Jurídicos**
1. Textos das íntegras trazem nomes de partes; espelhos e atas trazem advogados. Mesmo públicos, o tratamento exige finalidade, minimização e pseudonimização (LGPD arts. 6, 7 §§3–4, 12, 23). Nunca publicar identificadores; salt fora do Git.
2. Rec. 159 é recomendação; a Res. 615 rege IA no Judiciário. O sistema é apoio à triagem, não decisão. O artigo deve dizer isso explicitamente e o protótipo deve registrar razões, limiar e contestação.
3. Risco reputacional de rotular decisões de ministros/gabinetes como "sinalizadoras"; reportar por órgão e período, não por relator.

**Validade**
4. **Rótulo ≠ verdade.** Sinalização judicial mede o que o STJ escreveu, não o fenômeno. Casos não sinalizados não são legítimos. PU learning e sensibilidade a ruído de rótulo são obrigatórios.
5. **Viés de seleção:** só chega ao STJ o que foi recorrido; predomínio de consumidor/bancário e criminal (HC). A predatória de 1º grau em massa aparece filtrada.
6. **Precisão lexical baixa** (§3); a revisão manual é o rótulo, não a regex.
7. **Deriva temporal:** Tema 1198 (afetado 2023, julgado 2025, publicado 2026) e Rec. 159 mudam a linguagem das decisões. Divisão temporal e testes pré/pós são indispensáveis.
8. **Vazamento por decisões-modelo:** gabinetes repetem parágrafos; agrupar por similaridade antes de dividir.
9. **Qualidade dos dados:** cobertura de texto 2026 (§1.1), datas do DataJud (§1.2), município ausente em TJAL/TJSP antigo, `assuntos` múltiplos e inconsistentes.
10. **Ponte incompleta antes de 30/06/2023.**

---

## 7. Critérios de go/no-go (fase 1: corpus anotado)

| Critério | Go | Reformular | No-go |
|---|---|---|---|
| Candidatos lexicais revisados manualmente | ≥ 1.000 | 500–1.000 | < 500 |
| Casos confirmados com fundamentação (intensidade ≥ "indício reconhecido") | **≥ 300** | 150–300 → só Desenho A | < 150 → estudo descritivo |
| Precisão do gatilho lexical após revisão | ≥ 30% | 15–30% (refinar léxico) | < 15% |
| Consistência da anotação (re-anotação cega de 10%, κ) | ≥ 0,75 | 0,6–0,75 | < 0,6 |
| Ponte íntegras→DataJud para confirmados distribuídos ≥ 30/06/2023 | ≥ 70% | 40–70% → B parcial | < 40% → A |
| Cobertura de texto 2026 explicada/recuperada | sim | usar só até 2025 | — |
| Baseline explicável (regras + logística) supera regras puras em PR-AUC com calibração aceitável | sim | — | não → revisar taxonomia |
| Nenhum atributo pessoal nas features dos modelos principais | obrigatório | — | — |

Se o Desenho C não passar no protocolo ético ou não acrescentar ganho sobre o B, o estudo fica em **grafos de padrões processuais e textuais**, como previsto no briefing.

---

## 8. Diretriz transversal recebida de outra sessão (05/09) e divergências a decidir

Outra sessão do Claude Code (política de IA e reprodutibilidade do portfólio) copiou para esta pasta `docs/AI_POLICY_AND_REPRODUCIBILITY.md` e `docs/latex_snippets/` e pediu a incorporação de cinco itens. Incorporados ao README sem conflito: RUNBOOK numerado; exportação para `outputs/overleaf/` com `numbers.tex`; detectores como instrumento de medida validado contra gold set; só modelos locais; relato agregado sem nomes; lockfiles, manifesto de downloads, CITATION.cff, LICENSE, Zenodo. Python-only já era a decisão desta sessão.

**Divergências que só Valber resolve** (prevalece o que ele decidir; nada foi alterado no CLAUDE.md por pedido de outra sessão):

| Tema | Briefing desta sessão | Diretriz da outra sessão |
|---|---|---|
| Formato do artigo | Quarto (renderizado a partir do pipeline) | esqueleto LaTeX em `article/` + escrita no Overleaf |
| Papel do Claude na redação | "assistente de redação" | nunca escreve prosa do artigo; só código, testes, SQL, docs, runbook |
| Painel de pesquisa | protótipo de painel só para pesquisa (entrega 10) | não mencionado |

Recomendação: adotar a diretriz da outra sessão nos dois primeiros pontos (LaTeX/Overleaf e prosa exclusivamente humana), porque ela decorre das políticas editoriais verificadas e da Portaria CNPq 2.664/2026; o Quarto pode continuar como caderno de análise reproduzível que alimenta `outputs/overleaf/`. Pendente de confirmação.

## 9. Próximos passos propostos (fase 1)

1. Instalar `uv`, criar ambiente e lockfile; instalar Jupyter para o Quarto.
2. Ingestão completa das íntegras (11 GB) e espelhos (1 GB) em DuckDB/Parquet com trilha de hashes; verificar a cobertura de texto de 2026.
3. Léxico refinado (versão 2, com exclusões: "demandas repetitivas", "custo de captação") e extração de candidatos com contexto.
4. Protocolo de anotação (taxonomia por Anexo A + intensidade) e revisão manual de ≥ 1.000 candidatos.
5. Ingestão das atas (só campos de ponte na primeira passagem; partes/advogados ficam fora até o protocolo ético do Desenho C).
6. Reavaliar go/no-go com os números reais.

---

## 10. Atualização de 12/09/2026 — passo 10 executado (ingestão completa das íntegras, sem download)

Executado sem intervenção do pesquisador porque não dependia de decisão nem de download: os 11,4 GB de ZIP+JSON já
estavam no disco (espelho baixado em 07–08/09 pelo projeto irmão `STJ-Moral-Damages-Jurimetrics`, com SHA-256), e o
script `scripts/10_ingest_stj_integras.py` só lê esse espelho (`--source`), grava Parquet por chave em
`data/interim/stj_integras/{meta,text}/` (6,0 GB, zstd), cria as views `documents`/`document_text` em `data/alj.duckdb`
e registra cada arquivo-fonte em `logs/raw_hashes.tsv`. Nome do relator só como hash salgado; nenhum nome de parte.

**Números medidos (`logs/10_ingest_stj_integras.json`):** 1.287 chaves (1.281 diárias + 4 mensais de 2022 + 2 dias de
2026 sem ZIP no CKAN); **3.482.383 documentos** (2.635.456 decisões, 846.927 acórdãos) e **2.975.817 textos**.

| Ano | Chaves | Metadados | Com texto | Cobertura |
|---|---|---|---|---|
| 2021 | 243 | 533.230 | 525.240 | 98,5 % |
| 2022 | 169 | 560.137 | 518.840 | 92,6 % |
| 2023 | 231 | 559.212 | 519.340 | 92,9 % |
| 2024 | 238 | 640.938 | 632.348 | 98,7 % |
| 2025 | 242 | 705.287 | 661.293 | 93,8 % |
| 2026 | 164 | 483.579 | 134.335 | **27,8 %** |

- 147 chaves com cobertura < 50 % (102 em 2026; 18 em 2022; 16 em 2023; 11 em 2025) — é propriedade da fonte (os ZIP do
  espelho batem byte a byte com o tamanho publicado no CKAN), não do download. Exemplo: 02/08/2023 tem 4.284 metadados e 71 textos.
- `textos20260126.zip` está corrompido na origem (cabeçalhos locais presentes, diretório central ilegível; 3,9 MB, publicado
  em 11/02/2026); tratado como zero textos. 11/06 e 15/06/2026 não têm ZIP no CKAN.
- Critério de go/no-go "cobertura de texto 2026 explicada/recuperada": **não recuperada** → aplicar a alternativa prevista
  (“usar só até 2025”), salvo se o STJ republicar os recursos de 2026.

Continua pendente do pesquisador: desenho A/B/B+C, revisão de `docs/annotation_protocol.md` e autorização dos passos 11
(espelhos), 12 (atas, só campos de ponte) e 20+ (léxico v2 e candidatos).
