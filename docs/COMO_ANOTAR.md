# Como anotar — passo a passo (item D-4)

Objetivo: transformar `gold_v1_sample.csv` (1.443 documentos, já sorteado) no **padrão-ouro** do artigo. Sem ele
não existe precisão, revocação, κ nem a tabela go/no-go — é o gargalo real.

Regra que vale acima de tudo: **rótulo é seu**. O que está na planilha em `patterns`, `annex_a_items`, `tiers` e
`context_*` é palpite da máquina, pode estar errado, e medir esse erro é justamente o objetivo.

---

## 1. Abrir a planilha (2 minutos)

```
D:\Claude code - projetos\abusive-litigation-jurimetrics\data\annotations\gold_v1_sample.csv
```

Abra no Excel (duplo clique; o arquivo já tem BOM, então os acentos saem certos). **Salve imediatamente como
`gold_v1.xlsx`** na mesma pasta e trabalhe nele — o `.csv` fica intacto como original. A pasta é git-ignored:
nada dali vai para o GitHub.

Congele a primeira linha (Exibir → Congelar Painéis → Congelar Linha Superior) e ative o filtro
(Dados → Filtrar). Você vai filtrar por `stratum` o tempo todo.

## 2. Entender as colunas (5 minutos, uma vez)

| grupo | colunas | o que é |
|---|---|---|
| identificação | `doc_id`, `key`, `seq_documento`, `data_publicacao`, `classe`, `processo`, `numero_registro`, `assuntos_leaf`, `nchar` | qual decisão é |
| palpites da máquina | `stratum`, `patterns`, `annex_a_items`, `tiers`, `n_hits`, `negated_all`, `context_1..3` | por que ela chamou sua atenção |
| **você preenche** | `label1_status`, `label2_grounds`, `label3_measure`, `label4_domain`, `justification`, `minutes_spent`, `annotator`, `annotation_date`, `protocol_version` | o rótulo |

Os códigos são os do seu protocolo (`docs/annotation_protocol.md`):

- **`label1_status`** — `S3` o STJ reconhece indícios e fundamenta uma medida neles · `S2` o STJ mantém (ou não
  reexamina) reconhecimento da origem, tipicamente Súmula 7 · `S1` o termo aparece só como alegação da parte,
  preliminar afastada ou citação de precedente · `S0` falso positivo do léxico · `NA` texto ausente ou ilegível.
- **`label2_grounds`** — itens do Anexo A confirmados, separados por `;`: `A1`…`A20`, mais `T1198` (aplicou o
  Tema 1198) e `MAFE` (é só litigância de má-fé do art. 80, sem padrão de massificação).
- **`label3_measure`** — `M0` nenhuma · `M1` emenda/complementação de documentos · `M2` extinção sem mérito ·
  `M3` multa ou custas · `M4` ofício à OAB/MP · `M5` outra.
- **`label4_domain`** — `D1` consumo/bancário · `D2` cível outro · `D3` criminal · `D4` público/tributário ·
  `D5` trabalhista/outro.
- **`justification`** — uma frase com a passagem decisiva, citada **por parágrafo**, nunca por nome de parte.
- **`minutes_spent`**, **`annotator`** (suas iniciais), **`annotation_date`**, **`protocol_version`** (`v0.1`).

## 2b. Ferramentas de apoio (02/10) — nenhuma sugere rótulo

```bash
uv run python scripts/28_plan_batches.py --start 2026-10-05   # uma vez: plano de lotes de 25/dia útil
uv run python scripts/27_check_worksheet.py                   # ao fim de cada sessão: erros, avisos, progresso
```

- O **plano** (`data/annotations/plano_lotes.csv`) segue a ordem da seção 4 e, dentro de cada estrato, uma ordem
  pseudoaleatória fixa: se você parar no meio de um estrato, o que já foi feito é uma subamostra aleatória dele, e a
  validação parcial não fica enviesada para as decisões mais antigas (a planilha é ordenada por data).
- A **conferência** lê o próprio `gold_v1.xlsx` (não precisa salvar CSV para isso), aponta códigos fora do
  protocolo e combinações improváveis — S3 com M0, S3/S2 sem fundamento, S0 com fundamento, MAFE junto de itens A,
  NA com fundamento, justificativa vazia —, mostra quanto falta por estrato, as horas restantes, o próximo lote e
  a data a partir da qual a rodada cega pode começar. Aviso é para rever; nada é alterado na sua planilha.

## 3. Ler o documento inteiro, não o trecho

O protocolo (§6.1) exige ler a decisão, não a janela de contexto. Para abrir a decisão:

```bash
uv run python scripts/25_show_document.py 20210208-120488078
```

(substitua pelo `doc_id` da linha). Ele imprime o texto completo no terminal e grava
`data/annotations/_leitura/<doc_id>.txt`, que você pode abrir no Bloco de Notas. Nada sai da máquina.

## 4. A ordem de trabalho (importa)

Filtre por `stratum` e siga esta ordem — ela calibra sua escala antes dos casos difíceis:

| ordem | estrato | n | o que esperar |
|---|---|---|---|
| 1º | `strict` | 600 | o fenômeno é nomeado; é aqui que você fixa a fronteira entre S3, S2 e S1 |
| 2º | `strict_negated` | 115 | o tribunal **afastou** a alegação; quase tudo deve virar `S1` ou `S0` |
| 3º | `conduct_multi` | 300 | ≥ 2 condutas do Anexo A **sem** o termo — onde o artigo agrega valor |
| 4º | `conduct_sanction` | 180 | uma conduta + medida aplicada |
| 5º | `control_flagged` | 100 | quase-acertos derrubados por exclusão; medem o custo das exclusões |
| 6º | `control_unflagged` | 150 | nunca sinalizados: **é o denominador da revocação**, não pule |

**Meta mínima:** 1.000 documentos revisados e **≥ 300 confirmados** (S3 ou S2) — critério da §7 do relatório.
Se ficar entre 150 e 300, o estudo cai para o desenho A.

Ritmo realista: 2 a 4 minutos por documento depois que a escala estiver calibrada. 1.443 documentos ≈ 60–90
horas. Dá para dividir: **os 600 do `strict` já permitem a primeira medição**, e eu rodo a validação parcial.

## 5. Dúvidas e casos-limite

- Não decidiu? **Deixe `label1_status` em branco.** Em branco é contado como "não anotado" e fica fora das
  estimativas; chute não.
- Decisão trata de vários pedidos e só um é sinalizado? Rotule pelo que a decisão **fundamenta**.
- Reconhecimento veio da origem e o STJ não reexaminou (Súmula 7)? É `S2`, não `S3`.
- O termo aparece só na ementa copiada de precedente? `S1`.
- Texto truncado ou vazio? `NA` — não tente adivinhar pelo contexto.

## 6. Quando terminar (ou parar em um bloco)

1. Salve como **`data/annotations/gold_v1.csv`** (Excel: Salvar como → CSV UTF-8; o Excel em português grava com
   `;` — o passo 22 aceita `,` e `;`).
2. Me avise, ou rode você mesmo:

```bash
uv run python scripts/22_validate_lexicon.py
```

Ele devolve precisão, revocação e F1 — crus e ponderados pela fração amostral, com e sem `S2` — precisão por
padrão (k ≥ 5), frequência dos itens do Anexo A e a tabela go/no-go preenchida.

**Rodando com a planilha pela metade** (por exemplo, só o `strict`): linhas em branco contam como não anotadas,
e o fim da saída diz o que já é estimável — a precisão (dos estratos anotados) sim; revocação e F1 só depois de
haver `control_unflagged` anotado (até lá aparecem como nulas, nunca como 1,0). O go/no-go sai marcado como
provisório e o passo 80 não leva esses números ao Overleaf.

## 7. A segunda rodada (κ) — duas semanas depois

`data/annotations/gold_v1_reannotation.csv` tem **144** dos mesmos documentos, embaralhados e **sem as colunas
de palpite**. Anote-os às cegas, salve como `gold_v1_reannotation_done.csv` e o passo 22 calcula o κ de Cohen
(meta: ≥ 0,75). As duas semanas contam a partir da **última** anotação desses mesmos documentos na primeira
rodada — `scripts/27_check_worksheet.py` mostra a data (por isso preencha `annotation_date` sempre), e o passo 22
avisa se algum par foi refeito cedo demais. Sem isso o artigo não tem estatística de concordância — e foi exatamente a ausência disso que o
levantamento de literatura apontou como lacuna da produção brasileira.
