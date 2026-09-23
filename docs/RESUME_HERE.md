# RETOMAR AQUI — artigo 5 (litigância abusiva)

> **DECISÕES DO PESQUISADOR — 23/09/2026**
> 1. **Atas autorizadas** (4,2 GB) → baixadas por `scripts/12b_download_atas.py` e ingeridas pelo passo 12
>    (só campos de ponte; partes e advogados continuam fora até o protocolo ético do desenho C).
> 2. **Desenho B** (sinalização judicial + trajetória processual via DataJud).
> 3. **Protocolo de anotação confirmado** na v0.1 (escalas S3/S2/S1/S0/NA · A1–A20/T1198/MAFE · M0–M5 · D1–D5).
> 4. Anotação: passo a passo em `docs/COMO_ANOTAR.md`.
> 5. Conferência do léxico: passo a passo em `docs/COMO_CONFERIR_O_LEXICO.md`.
> 6. **Push feito** em 23/09 (6 commits, `b5afe2b..d8bab88`).

Atualizado em 22/09/2026, ao fim da sessão "faça tudo que puder sem minha permissão".
Leia este arquivo primeiro; o detalhe técnico está em `docs/feasibility_report.md` §11 e em `docs/RUNBOOK.md`.

## Em uma frase

O corpus e o instrumento de medição estão prontos e rodados de ponta a ponta; **falta você decidir o desenho,
revisar o protocolo e anotar** — nenhum rótulo, modelo ou resultado existe, por regra (CLAUDE.md §2).

## Suas decisões, em ordem de impacto

### D-1. Atas de distribuição: autoriza o download de ~4,2 GB? (decide o desenho)

A ponte `numeroRegistro` → número CNJ → DataJud, feita só com a foto do acervo, cobre **1,3 % a 2,2 %** dos
candidatos de 2021–2024, 7,2 % de 2025 e 31,7 % de 2026 (§11.4). O critério de go/no-go da §7 pede ≥ 70 %.
As atas cobrem tudo o que foi distribuído desde 30/06/2023 e resolveriam o histórico recente.

- **Sim** → `uv run python scripts/12_ingest_stj_bridge.py --atas DIR` (só campos de ponte; partes e advogados
  continuam fora até o protocolo ético do desenho C) e o **desenho B** fica viável de jul/2023 em diante.
- **Não** → o estudo converge para o **desenho A** (documento como unidade, sem trajetória processual), que
  responde RQ1, RQ2 e RQ5, mas não RQ3 nem RQ4.

### D-2. Desenho A, B ou B+C?

Recomendação inalterada: **B**, condicionado a D-1. O C (camada de advogados/partes com hash salgado) exige
protocolo ético seu e, pelo volume medido, tende a não acrescentar poder explicativo suficiente para justificar o
risco — a estimativa da §3 se confirmou (≈ 2.950 documentos com termo estrito em 2021–2026, não centenas de
milhares).

### D-3. Protocolo de anotação: confirma as escalas?

`docs/annotation_protocol.md` continua o **seu** rascunho v0.1 (S3/S2/S1/S0/NA; A1–A20 + T1198 + MAFE; M0–M5;
D1–D5). O apêndice A, que eu acrescentei, só registra como o código o operacionaliza — colunas da planilha,
estratos e métricas. Se você mudar uma escala, mude ali e eu ajusto `src/alj/annotation.py` e `src/alj/validation.py`.

### D-4. Anotar 1.349 documentos (é o gargalo do artigo)

`data/annotations/gold_v1_sample.csv` (abre no Excel, já com BOM; a pasta é git-ignored porque traz trechos de
decisões). Ordem sugerida no `README_annotation.md` da mesma pasta:

| estrato | n | o que esperar |
|---|---|---|
| `strict` | 600 | o fenômeno é nomeado — calibra a escala |
| `strict_negated` | 120 | alegações **afastadas** — devem virar S1/S0 |
| `conduct_multi` | 300 | ≥ 2 condutas do Anexo A sem o termo — onde o artigo agrega valor |
| `conduct_sanction` | 179 | uma conduta + medida aplicada |
| `control_unflagged` | 150 | nunca sinalizados: **o denominador da revocação** |

Depois: salve como `gold_v1.csv`, anote `gold_v1_reannotation.csv` cego (135 documentos, duas semanas depois) e
rode `uv run python scripts/22_validate_lexicon.py` — ele já calcula precisão/revocação/F1 crus **e** ponderados,
com e sem S2, κ e a tabela §7 preenchida.

### D-5. Léxico v2.2 — **já feito em 22/09, com a Jus IA**; confirma?

Você mandou usar a Jus IA. Usei-a na sua conta, com **uma** consulta de escopo bibliográfico (nenhum documento do
corpus foi enviado, nada dela virou rótulo — registro completo em `docs/ai_usage_log.md`). Ela apontou cinco
critérios que os tribunais usam e que **não estavam** no léxico; eu medi cada um neste corpus antes de aceitar:

| padrão novo (v2.1.0 → v2.2.0) | documentos no corpus |
|---|---|
| `autenticidade_postulacao` (fórmula literal do Tema 1198) | 314 |
| `firma_reconhecida` | 814 |
| `requerimento_administrativo_previo` | 2.919 |
| `desconhecimento_da_acao` (parte não conhece a ação ou o advogado) | 414 |
| `sumula_tjba_predatoria` (Súmulas 46 e 54 do TJBA, forma restrita) | 1 |
| `comunicado_cg_tjsp` (Comunicados CG 02/2017 e 424/2024, CGJ-TJSP/NUMOPEDE) | 309 |
| `numopede` ampliado para a grafia NUMPEDE (TJPB) | +43 |

E a medição **descartou** três sugestões dela: Diretriz Estratégica 7/CNJ (2 documentos), Enunciados EPM/CGJ-TJSP (0) e Ato TRT21-GP 228/2023 (0). São atos reais, mas ausentes deste corpus.

A varredura completa com a v2.2 foi relançada (≈49 min) e a planilha de anotação será regerada com a **mesma
semente**, para ficar comparável. Se você preferir anotar sobre a v2.0, é só dizer — mas o momento barato de
trocar o instrumento é agora, antes da anotação.

### D-5b. Mais alguma coisa do léxico a ajustar?

Os padrões campeões de volume são de linguagem processual comum (`extincao_sem_merito` 63 k documentos,
`representacao_irregular` 33 k). Isso é intencional (o Anexo A descreve condutas, não termos de arte), mas se você
quiser que a camada de conduta seja mais restritiva, é melhor ajustar `config/lexicon_v2.yaml` **antes** de anotar —
uma nova varredura completa custa 49 min e repovoa o estrato `control_flagged`, hoje vazio.

## O que eu fiz em 23/09 pela manhã (sem depender de você)

- **Espelhos completos**: sondei o ZIP inicial (`scripts/11b`), descobri que não era duplicata e reingeri tudo —
  **877.353 espelhos**, 2,0 M citações, 1,2 M referências legislativas, desde 1989.
- **Passo 24 (novo)**: as duas fontes concordam pouco — quando a íntegra nomeia o fenômeno, o espelho o nomeia
  em **29,4 %** dos casos compartilhados. Um estudo só sobre ementas perderia ~70 % dos casos sinalizados.
- **Passo 81 (novo)**: quatro figuras descritivas em `outputs/figures` (termo estrito por ano, candidatos por
  camada, cobertura da ponte contra o limiar de 70 %, padrões mais frequentes), já no export do Overleaf.
- §12 do relatório de viabilidade, RUNBOOK, dicionário de dados e `dodo.py` atualizados; 226 testes.

## O que eu fiz na sessão anterior (tudo local, nada pushado)

- **Léxico v2.0.0** versionado (47 padrões em 5 camadas, 4 exclusões, 2 negações) + motor com pré-filtro RE2
  (25 s → 0,8 s por dia de publicação) e triagem por padrão; 208 testes, um exemplo asseverado por padrão.
- **Passo 20**: 2.975.817 textos, 150.897 candidatos, 304.248 acertos com contexto, 48,9 min.
- **Passo 11**: 165.850 espelhos + 220.335 citações + 93.209 referências legislativas (551,6 MB, 10,9 min).
- **Passo 23**: mesmo léxico nos espelhos — 3.003 candidatos, 171 com termo estrito.
- **Passo 12**: ponte com 333.636 pares a partir da foto do acervo (sem download).
- **Passo 21**: planilha estratificada de 1.349 documentos + 135 para κ.
- **Passos 80/90**: 8 tabelas booktabs e 30 macros em `outputs/overleaf/` (nenhum número digitado à mão).
- Infra: `dodo.py` (DAG), `scripts/19_refresh_duckdb_views.py`, `src/alj/manifest.py` (manifesto unificado),
  `docs/feasibility_report.md` §11, RUNBOOK e README atualizados.

## Pendências técnicas minhas (não dependem de você)

1. `control_flagged` vazio até a próxima varredura completa (o passo 20 agora grava os quase-acertos).
2. Passo 30 (`30_fetch_datajud_trajectories.py`) não escrito — só faz sentido depois de D-1.
3. ~~Espelhos: ZIPs iniciais~~ **RESOLVIDO em 23/09** — não eram duplicata: traziam o acervo histórico desde
   1989. Corpus de espelhos foi de 165.850 para **877.353** registros (§12.1 do relatório).
4. Commit local de 22/09 **sem push** — o repositório é público e o push é decisão sua.
