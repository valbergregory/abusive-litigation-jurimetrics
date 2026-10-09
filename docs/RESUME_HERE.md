# RETOMAR AQUI — artigo 5 (litigância abusiva)

> **DECISÕES DO PESQUISADOR — 23/09/2026**
> 1. **Atas autorizadas** (4,2 GB) → baixadas por `scripts/12b_download_atas.py` e ingeridas pelo passo 12
>    (só campos de ponte; partes e advogados continuam fora até o protocolo ético do desenho C).
> 2. **Desenho B** (sinalização judicial + trajetória processual via DataJud).
> 3. **Protocolo de anotação confirmado** na v0.1 (escalas S3/S2/S1/S0/NA · A1–A20/T1198/MAFE · M0–M5 · D1–D5).
> 4. Anotação: passo a passo em `docs/COMO_ANOTAR.md`.
> 5. Conferência do léxico: passo a passo em `docs/COMO_CONFERIR_O_LEXICO.md`.
> 6. **Push feito** em 23/09 (6 commits, `b5afe2b..d8bab88`).

Atualizado em **09/10/2026** (fase 2: trajetórias processuais coletadas). Leia este arquivo primeiro; o
detalhe técnico está em `docs/feasibility_report.md` — §13 (ponte), **§14 (trajetórias)** — e em
`docs/RUNBOOK.md`.

> **Se o terminal disser que `uv` não é reconhecido** (conferido em 09/10/2026: o `uv` está em
> `%APPDATA%\Python\Python313\Scripts`, fora do PATH desta máquina), troque `uv run python` por
> `python -m uv run python`, ou chame `.\.venv\Scripts\python.exe` direto. O ambiente está íntegro:
> 272 testes passam, ruff limpo.

## Em uma frase

Desenho B decidido, atas ingeridas, protocolo v0.1 confirmado e, desde 09/10, **as trajetórias processuais do
DataJud coletadas** (135.941 processos, 16,75 M movimentos): **só falta a sua anotação** — 1.443 documentos de `gold_v1_sample.csv` e, ≥ 2 semanas depois, os 144 da rodada cega. Tudo o que

## Próximos passos (02/10) — ferramentas novas para anotar mais rápido

Nenhuma delas gera, sugere ou corrige rótulo; só leem o que você digitou.

1. **Plano de lotes** (uma vez, antes de começar):
   `uv run python scripts/28_plan_batches.py --start 2026-10-05` → `data/annotations/plano_lotes.csv`
   (25 documentos por dia útil, na ordem do `COMO_ANOTAR.md` §4; ≈ 58 dias úteis). Dentro de cada estrato a ordem
   é pseudoaleatória fixa, para que parar no meio de um estrato deixe uma subamostra aleatória (a planilha original
   é ordenada por data, e parar nela enviesaria a validação parcial). `--ordered-worksheet` grava também
   `gold_v1_sample_ordenado.csv` com as colunas `lote` e `ordem` — útil só se você ainda não começou.
2. **Conferência diária** (ao fim de cada sessão, lê direto o `gold_v1.xlsx`, sem precisar salvar CSV):
   `uv run python scripts/27_check_worksheet.py` → erros (código fora do protocolo, coluna faltando, `doc_id`
   repetido, data ilegível), avisos de combinação improvável (S3 com M0, S3/S2 sem fundamento, S0 com fundamento,
   MAFE com itens A, NA com fundamento, justificativa vazia), progresso por estrato, horas restantes a 2–4 min/doc
   e no seu ritmo medido, o **próximo lote** e a **data mínima da rodada cega** (≥ 14 dias após a última anotação
   dos 144 documentos dela). A lista linha a linha fica em `data/annotations/_verificacao.csv` (git-ignored).
3. **Validação parcial** — assim que o `strict` (600) estiver pronto, salve `gold_v1.csv` (vírgula **ou**
   ponto e vírgula, tanto faz) e rode `uv run python scripts/22_validate_lexicon.py`. Ele diz o que já é
   estimável: **precisão sim** (só dos estratos anotados), **revocação e F1 não** até haver `control_unflagged`
   anotado (antes saía um 1,0 falso; agora sai nulo). O go/no-go fica marcado como provisório, e o passo 80 não
4. **Rodada cega (κ)**: só abra `gold_v1_reannotation.csv` na data que o passo 27 indicar; salve como
   `gold_v1_reannotation_done.csv`. O passo 22 calcula o κ e avisa se algum par foi refeito com menos de 14 dias.
5. **Ao terminar**: `uv run python scripts/22_validate_lexicon.py`, depois `80_build_outputs.py`,

## Suas decisões, em ordem de impacto

### ✅ D-1 RESOLVIDA (23/09) — atas baixadas e ingeridas

1.010 recursos, 4,14 GB, 13,2 min, zero falhas; 1.000 dias (30/06/2023 a 09/09/2026), só campos de ponte.
A ponte foi de 333.636 para **2.543.847 pares** e a cobertura dos candidatos passou a **91,2 % (2024)** e
**92,8 % (2025)** — critério da §7 atendido. Detalhe em §13 do relatório.

<details><summary>pergunta original (mantida para registro)</summary>

### D-1. Atas de distribuição: autoriza o download de ~4,2 GB? (decide o desenho)

A ponte `numeroRegistro` → número CNJ → DataJud, feita só com a foto do acervo, cobre **1,3 % a 2,2 %** dos
candidatos de 2021–2024, 7,2 % de 2025 e 31,7 % de 2026 (§11.4). O critério de go/no-go da §7 pede ≥ 70 %.
As atas cobrem tudo o que foi distribuído desde 30/06/2023 e resolveriam o histórico recente.

- **Sim** → `uv run python scripts/12_ingest_stj_bridge.py --atas DIR` (só campos de ponte; partes e advogados
  continuam fora até o protocolo ético do desenho C) e o **desenho B** fica viável de jul/2023 em diante.
- **Não** → o estudo converge para o **desenho A** (documento como unidade, sem trajetória processual), que
  responde RQ1, RQ2 e RQ5, mas não RQ3 nem RQ4.

</details>

### ✅ D-2 RESOLVIDA — desenho **B**

Recomendação inalterada: **B**, condicionado a D-1. O C (camada de advogados/partes com hash salgado) exige
protocolo ético seu e, pelo volume medido, tende a não acrescentar poder explicativo suficiente para justificar o
risco — a estimativa da §3 se confirmou (≈ 2.950 documentos com termo estrito em 2021–2026, não centenas de
milhares).

### ✅ D-3 RESOLVIDA (23/09) — protocolo v0.1 confirmado

<details><summary>pergunta original (mantida para registro)</summary>

### D-3. Protocolo de anotação: confirma as escalas?

D1–D5). O apêndice A, que eu acrescentei, só registra como o código o operacionaliza — colunas da planilha,
estratos e métricas. Se você mudar uma escala, mude ali e eu ajusto `src/alj/annotation.py` e `src/alj/validation.py`.

</details>

### D-4. Anotar 1.443 documentos (é o gargalo do artigo) — ver "Próximos passos" acima

(A tabela abaixo é a da primeira amostra, de 1.349; a amostra regerada com o léxico v2.2 tem 1.443, com
`strict_negated` 115 e `control_flagged` 100 — números de `logs/21_export_annotation_sample.json`.)

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
uma nova varredura completa custa 49 min e refaz o estrato `control_flagged` (hoje com 100 sorteados de
6.250 disponíveis).

## O que eu fiz em 09/10 (fase 2 — as trajetórias, sem depender de você)

- **Passo 30 (novo)** — trajetórias do DataJud: **140.478 processos-alvo** (70.300 candidatos + 70.178 de
  comparação **nunca sinalizados**, sorteados com semente fixa nas mesmas células ano × tribunal), 34 tribunais,
  **135.941 encontrados (96,8 %)**, 213.075 documentos, **16.754.078 movimentos**, 60,8 min, **zero erros**.
- **Passo 31 (novo)** — uma linha por processo com as covariáveis de trajetória, a partir de
  `config/movement_groups.yaml` v0.1.0 (**segundo instrumento versionado**: 14 grupos de movimentos da TPU do
  CNJ). Todas as verificações de integridade em zero.
- **Três medições que mudaram decisões** (§14.3 do relatório): o custo da API é **por consulta** (lote de 500 é
  35× mais rápido que lote de 50); a TPU **não tem movimento** para litigância de má-fé — a sanção só existe no
  texto da decisão; e o mesmo processo aparece como vários documentos do mesmo grau (6.500 casos), o que inflaria
  o volume em 6,4 % se os movimentos não fossem deduplicados por `código + data/hora + órgão`.
- **TJDFT devolveu só 23,6 %** dos processos pedidos (os outros 33 tribunais, 90,1 %–99,9 %). Conferi: os números
  não estão no índice público. Por isso a §7 ganhou um critério novo — "trajetória efetivamente encontrada" —, e
  o passo 22 passou a medir **ponte e trajetória sobre os seus casos confirmados** (S3/S2), não sobre candidatos.
  `fig_trajectory_groups`, 39 macros em `numbers.tex`.

### O retrato descritivo (covariáveis, **não** rótulo e **não** efeito)

| medida | sinalizados | não sinalizados |
|---|---|---|
| processos | 70.300 | 70.178 |
| mediana de movimentos | 71 | 83 |
| mediana de dias (1º → último movimento) | 822 | 913 |
| % com extinção **sem** resolução de mérito | **35,0 %** | **20,5 %** |
| % com indeferimento da inicial | 3,5 % | 1,3 % |
| % com abandono/negligência | 0,7 % | 0,2 % |

Os grupos também diferem em tribunal, classe e ano: isso é descrição, não comparação pareada. O pareamento vem
depois do seu padrão-ouro, e é dele que sai qualquer afirmação.

## O que eu fiz em 02/10 (sem depender de você)

- **Passo 22 em etapas**: roda sobre a planilha parcial; pesos `disponíveis / anotados` por estrato; bloco
  `estimable` no log (precisão com escopo, revocação/F1 nulos sem `control_unflagged`); go/no-go `provisional`;
  lê CSV com `,` ou `;`; sem o Parquet de candidatos, deduz `flagged` do estrato (idêntico por construção).
- **Passos 27 (conferência) e 28 (lotes)**, novos; `src/alj/worksheet.py`; `openpyxl` para ler o `.xlsx`.
- **Passo 80** não exporta validação parcial (salvo `--allow-partial-gold`) e apaga prévias antigas.
- **Testes**: 247 (21 novos), incluindo o encadeamento 27 → 28 → 22 → 80 → 81 → 90 com padrão-ouro sintético,
  parcial (só `strict`) e completo.

## O que eu fiz em 23/09 pela manhã (sem depender de você)

- **Espelhos completos**: sondei o ZIP inicial (`scripts/11b`), descobri que não era duplicata e reingeri tudo —
  **877.353 espelhos**, 2,0 M citações, 1,2 M referências legislativas, desde 1989.
- **Passo 24 (novo)**: as duas fontes concordam pouco — quando a íntegra nomeia o fenômeno, o espelho o nomeia
  em **29,4 %** dos casos compartilhados. Um estudo só sobre ementas perderia ~70 % dos casos sinalizados.
- **Passo 81 (novo)**: quatro figuras descritivas em `outputs/figures` (termo estrito por ano, candidatos por
- §12 do relatório de viabilidade, RUNBOOK, dicionário de dados e `dodo.py` atualizados; 226 testes.

## O que eu fiz na sessão anterior (tudo local, nada pushado)

- **Léxico v2.0.0** versionado (47 padrões em 5 camadas, 4 exclusões, 2 negações) + motor com pré-filtro RE2
  (25 s → 0,8 s por dia de publicação) e triagem por padrão; 208 testes, um exemplo asseverado por padrão.
- **Passo 20**: 2.975.817 textos, 150.897 candidatos, 304.248 acertos com contexto, 48,9 min.
- **Passo 11**: 165.850 espelhos + 220.335 citações + 93.209 referências legislativas (551,6 MB, 10,9 min).
- **Passo 23**: mesmo léxico nos espelhos — 3.003 candidatos, 171 com termo estrito.
- **Passo 12**: ponte com 333.636 pares a partir da foto do acervo (sem download).
- **Passo 21**: planilha estratificada de 1.349 documentos + 135 para κ.
- Infra: `dodo.py` (DAG), `scripts/19_refresh_duckdb_views.py`, `src/alj/manifest.py` (manifesto unificado),
  `docs/feasibility_report.md` §11, RUNBOOK e README atualizados.

## Pendências técnicas minhas (não dependem de você)

1. ~~`control_flagged` vazio~~ **RESOLVIDO em 23/09**: o passo 20 grava os quase-acertos e o estrato tem 100
   documentos sorteados de 6.250 disponíveis.
2. ~~Passo 30 não escrito~~ **RESOLVIDO em 09/10**: passos 30 e 31 escritos e rodados (§14 do relatório).
   O que sobra da fase 2 é modelagem, e modelagem só depois do padrão-ouro, por regra.
3. ~~Espelhos: ZIPs iniciais~~ **RESOLVIDO em 23/09** — não eram duplicata: traziam o acervo histórico desde
   1989. Corpus de espelhos foi de 165.850 para **877.353** registros (§12.1 do relatório).
4. ~~Commit local de 22/09 sem push~~ **RESOLVIDO em 23/09** (push autorizado).
5. Confirmar edição/editora/ISBN dos livros brasileiros do mapa de literatura — espera sua aprovação da
   lista (`docs/literature_map.md` §6).
