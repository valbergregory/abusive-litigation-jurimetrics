# Confirmed data dictionary (phase 0, 2026-09-05)

Only fields actually observed in downloaded files or API responses. Source dictionaries are kept verbatim in `data/raw/stj/*.csv`.

## STJ — íntegras de decisões terminativas e acórdãos (`metadados<AAAAMMDD>.json` + `textos<AAAAMMDD>.zip`)

| Field | Type | Notes |
|---|---|---|
| `SeqDocumento` | int | id of the decision; equals the TXT file name inside the ZIP |
| `dataPublicacao` | date (ISO) | publication in DJe |
| `tipoDocumento` | text | `DECISÃO` or `ACÓRDÃO` |
| `numeroRegistro` | text (12 digits) | STJ registry number; **linkage key** to acervo/atas |
| `processo` | text | class acronym + STJ sequential number, e.g. `AREsp 3272747` (padded spaces) |
| `dataRecebimento`, `dataDistribuição` | date | STJ dates |
| `NM_MINISTRO` | text | rapporteur (dictionary calls it `ministro`) |
| `recurso` | text/null | internal appeal (`AgRg`, `EDcl`, `AgInt`, …); null = main case |
| `teor` | text | outcome (`Negando`, `Não Conhecendo`, `Concedendo`, `Outros`, …) |
| `descricaoMonocratica` | text | templated conclusion with `#{placeholders}` (monocratic only) |
| `assuntos` | text | CNJ subject codes, dotted hierarchy, `, `-separated |
| TXT body | UTF-8 text | paragraphs separated by `<br>`; contains party names; median 11 KB |

Coverage observed: text present for 97–99 % of metadata rows in 2021–2025; 0.4–22 % in 2026 (to be investigated).

## STJ — espelhos de acórdãos (monthly `<AAAAMMDD>.json` + one initial backlog `<AAAAMMDD>.zip`, one dataset per órgão)

**Medido em 23/09/2026:** o ZIP inicial de cada conjunto **não** duplica a série mensal — traz o acervo histórico
(Corte Especial: 14.223 registros de 1989 a 2022-06, 92 em comum). Com os dez ZIPs, o corpus vai de 165.850 para
877.353 espelhos. Campos idênticos aos dos JSON mensais; os membros do ZIP são JSON com a mesma estrutura.
Valores ausentes chegam como a **string** `"None"`; `dataPublicacao` = `"DJE  DATA:dd/mm/aaaa"`; `dataDecisao` =
`aaaammdd`; `referenciasLegislativas` e `acordaosSimilares` são *reprs* de lista Python dentro do JSON;
`jurisprudenciaCitada` traz cada citação entre `<<…>>`, precedida do tribunal.

`id`, `numeroProcesso`, `numeroRegistro`, `siglaClasse`, `descricaoClasse`, `nomeOrgaoJulgador`, `ministroRelator`, `dataPublicacao` (text, e.g. `DJE DATA:19/06/2024`), `ementa`, `tipoDeDecisao`, `dataDecisao`, `decisao`, `jurisprudenciaCitada` (text; precedents wrapped as `<<REsp 1816742>>`), `notas`, `informacoesComplementares`, `termosAuxiliares`, `teseJuridica`, `tema`, `referenciasLegislativas` (list of text blocks `LEG:FED LEI:010406 ANO:2002 … ART:00966`), `acordaosSimilares` (list), `numeroDocumento`, `classePadronizada` (both null in sample).

## STJ — acervo em tramitação (`processos_tramitando_<AAAAMMDD>.json.gz`, snapshot)

`numeroUnico` (CNJ 20 digits), `Data`, `numeroRegistro`, `siglaClasse`, `numeroNaClasse`, `codigoClasseCNJ`, `processo`, `nomeMinistroRelator`, `dataRecebimento`, `codigoOrgaoJulgador` (`CE`, `S1–S3`, `T1–T6`, null), `codigoAssuntoCNJ`, `assuntoCompleto`, `listaAssuntos`, `segredoJustica`, `pedidoDeLiminar`, `sobrestado`, `localProcesso`. 333,650 rows on 2026-09-02.

## STJ — atas de distribuição (`ata<AAAAMMDD>.json`, daily since 2023-06-30)

`numeroUnico`, `numeroRegistro`, `dataHoraDistribuicao` (ISO), `descFormaDistribuicao` (Distribuição/Redistribuição), `codigoClasse`, `siglaClasse`, `nomeClasse`, `codigoClasseCNJ`, `numeroNaClasse`, `codigoDestino`, `descDestino`, `codigoOrgaoJulgador`, `nomeMinistroRelator`, `codigoAssuntoCNJ`, **`partes[]`** = {`descTipoParte`, `nomeParte`, `numeroCNPJ`, **`advogados[]`** = {`codigoOAB`, `nomeAdvogado`}}.
Personal data: ingest only the bridge fields until the design-C protocol exists.

## STJ — precedentes qualificados (`Temas.csv`, `Processos.csv`)

Temas: `sequencialPrecedente`, `tipoPrecedente`, `numeroPrecedente`, `dataPrimeiraAfetacao`, `dataJulgamento`, `dataPublicacaoAcordao`, `situacao`, `informacoesComplementares`, `questaoSubmetidaAJulgamento`, `teseFirmada`, `anotacoesNUGEPNAC`, `delimitacaoJulgado`, `entendimentoAnterior`, `referenciaLegislativa`, `referenciaSumular`, `sumulaOriginada`, `audienciaPublica`, `orgaoJulgador`, `Assuntos`, `numeroRepercussaoGeralSTF`. Processos: `sequencialPrecedente`, `Processo`, `numeroRegistro`, `ministroRelator`, `leadingCase`, `dataAfetacao`, ….

## CNJ — DataJud public API (`POST https://api-publica.datajud.cnj.jus.br/api_publica_<trib>/_search`)

| Field | Type | Notes |
|---|---|---|
| `id` | text | `<TRIB>_<GRAU>_<numeroProcesso>` |
| `tribunal`, `grau` | text | grau ∈ G1, G2, JE, TR, SUP |
| `numeroProcesso` | text (20 digits) | CNJ number, **linkage key** across tribunals |
| `dataAjuizamento` | text `yyyyMMddHHmmss` | **do not** aggregate/range on the server; parse client-side |
| `nivelSigilo` | int | 0 = public |
| `orgaoJulgador.{codigo,nome,codigoMunicipioIBGE}` | | município null in TJAL (92 %) and old TJSP stock |
| `classe.{codigo,nome}`, `assuntos[].{codigo,nome}` | | SGT codes |
| `sistema`, `formato` | | e.g. SAJ / Eletrônico |
| `movimentos[].{codigo,nome,dataHora,complementosTabelados[],orgaoJulgador}` | | ISO `dataHora`; use for time filters |
| `dataHoraUltimaAtualizacao`, `@timestamp` | ISO | |

Not present: parties, lawyers, documents, judge names beyond órgão.

**What step 30 stores (confirmed 2026-10-09, `src/alj/datajud.py`).** The request asks for the allow-list above
only, so nothing else reaches disk; `@timestamp` is known Elasticsearch bookkeeping and is deliberately dropped.

| Parquet | Grain | Columns |
|---|---|---|
| `datajud_targets` | case × court | `numero_processo`, `alias`, `grupo` (`candidato` / `comparacao_nao_sinalizado`), `pub_year`, `strict_hit`, `n_documentos` (STJ decisions behind the row) |
| `datajud_cases` | case × grau | `alias`, `numero_processo`, `tribunal`, `grau`, `es_id`, `data_ajuizamento`, `nivel_sigilo`, `classe_{codigo,nome}`, `orgao_{codigo,nome}`, `municipio_ibge`, `sistema_nome`, `formato_nome`, `assuntos_{codigos,nomes}`, `n_movimentos`, `primeiro_movimento`, `ultimo_movimento`, `atualizado_em` |
| `datajud_movimentos` | movement | `alias`, `numero_processo`, `grau`, `es_id`, `ordem` (chronological, assigned here), `codigo`, `nome`, `data_hora`, `orgao_codigo`, `complementos` (`codigo:valor`, `;`-joined) |
| `datajud_features` | case × court | the step-31 covariates: durations from the movements, counts per movement group of `config/movement_groups.yaml`, `nao_encontrado_no_datajud` |

A case's time window is `primeiro_movimento` → `ultimo_movimento`; `dias_desde_ajuizamento` is only computed when
the client-side parse of `dataAjuizamento` is plausible (≥ 1990 and not after the last movement), because the
server returns years such as 2571 for large result sets (§1.2 of the feasibility report).

The movement codes are the CNJ **TPU** codes already mirrored in `data/raw/cnj/sgt/movimentos.csv` (964 rows,
**UTF-8** — not cp1252, checked byte by byte on 2026-10-09 — `;`-separated; `cod_pai`/`cod_filhos` carry the
hierarchy). Two parents organise most of the outcome vocabulary: **218 "Sem Resolução de Mérito"**
(77 children, among them 454 indeferimento da petição inicial, 456 extinção, 458 abandono, 463 desistência) and
**385 "Com Resolução do Mérito"** (192 children, among them 219/220/221 procedência/improcedência and 471
prescrição). `config/movement_groups.yaml` stores the expanded code lists so the instrument does not depend on a
git-ignored file at run time.

## CNJ — SGT tables (`data/raw/cnj/sgt/*.csv`, `;`-separated)

`assuntos.csv` (5,601 rows), `classes.csv` (849), `movimentos.csv` (964): `situacao`, `dat_alteracao`, `codigo`, `descricao`, (`sigla`, `natureza` for classes), `cod_pai`, `cod_filhos`, `cod_filhos_ativos`, `nivel`. **UTF-8**, `;`-separated.

Searching the whole movement table for *litigância de má-fé*, *abuso processual*, *ato atentatório*, *temerári…*,
*protelatóri…* and *multa* returns **two** movements, both electoral and about an absent polling officer. The
procedural-abuse sanction therefore has **no movement code**: it exists in the decision text and in the judgment
metadata, never in the trajectory. Recorded here because it bounds what design B can measure.
