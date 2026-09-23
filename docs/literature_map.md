# Mapa da literatura — artigo 5 (litigância abusiva)

Levantamento de 23/09/2026 com o GPT SciSpace (conversa "Literature Review Abusive Litigation", na conta do
pesquisador), prompt em `docs/prompts/scispace_revisao_literatura.md` (Prompt A). **Toda referência foi conferida
no Crossref** por `scripts/91_verify_references.py`: 16 DOIs sugeridos, **16 resolvidos, 0 inventados**
(`logs/91_verify_references.json`). O BibTeX verificado está em `notes/references_candidates.bib` e **não** sobe
para `article/references.bib` sem a aprovação do pesquisador.

## 1. O que voltou, por bloco

| bloco | obras verificadas |
|---|---|
| 1. Litigância abusiva, vexatória e frívola | Galanter revisitado — *Do the "Haves" Still Come Out Ahead?* (1999, `10.2307/3115150`); Fabiani/Silva? — *Why the "Haves" Come Out Ahead in Brazil?* (2016, `10.2139/SSRN.2716242`); Cunha & Barros — *Litigância abusiva, medidas de combate e a devida intersecção com a análise econômica do direito* (2025, `10.70982/rejef.v1i7.97`) |
| 2. Triagem e porta de entrada | *Twombly and Iqbal at the State Level* (J. Empirical Legal Studies, 2017, `10.1111/jels.12152`) |
| 3. NLP sobre decisões judiciais | Aletras et al. (ECtHR, 2016, `10.7717/peerj-cs.93`); Chalkidis et al. (ACL 2019, `10.18653/v1/P19-1424`); Medvedeva et al. (ICTAI 2019, `10.1109/ICTAI.2019.00275`); **Correia et al., anotação fina de entidades no STF** (IPM 2022, `10.1016/j.ipm.2021.102794`); **pipeline de anotação semântica de decisões brasileiras** (JURIX 2024, `10.3233/FAIA241248`) |
| 4. Rótulo fraco e anotação | Elkan & Noto (KDD 2008, `10.1145/1401890.1401920`); Bekker & Davis, *survey* de PU learning (2018, `10.48550/arXiv.1811.04820`); *Efficient Training for Positive Unlabeled Learning* (TPAMI 2019, `10.1109/TPAMI.2018.2860995`) |
| 5. Explicabilidade e custo do erro | Ribeiro et al., LIME (KDD 2016, `10.1145/2939672.2939778`); *SIDEs: Separating Idealization from Deceptive Explanations in xAI* (FAccT 2024, `10.1145/3630106.3658999`) |
| 6. Acesso à justiça e volume de litígio | *Access-to-Justice Reforms: A Brazilian Case Study of Bank Litigation* (German Law Journal, 2020, `10.1515/GJ-2020-0018`); *Por um acesso qualitativo à justiça — o perfil da litigância nos juizados* (2019, `10.12818/P.0304-2340.2019V75P443`) |

Dois achados úteis para o desenho: **Correia et al. (2022)** anotou 594 decisões do STF com 76 anotadores
selecionados por desempenho de concordância — é o precedente metodológico direto para o nosso protocolo; e
**Chalkidis et al. (2019)** reporta F1 ≈ 60 em rótulos raros e diz explicitamente que a predição neural não
oferece justificação confiável — exatamente o argumento para a nossa exigência de revisão humana.

## 2. Livros (o que você pediu)

O SciSpace **recusou-se a contar recorrência** de livros: disse que as listas de referências que recuperou não
vinham completas e que não produziria contagens "citado por N" sem inspecioná-las. Isso é o comportamento certo,
e vale registrar — a contagem de livros exige outra fonte (OpenAlex/Scopus) ou leitura das listas.

**(a) Internacionais e metodológicos**

| livro | edição | ISBN | status |
|---|---|---|---|
| Kritzer & Silbey (orgs.), *In Litigation: Do the "Haves" Still Come Out Ahead?* | Stanford University Press, 2003 | 978-0804747344 | **único efetivamente recuperado** da base |
| Cappelletti & Garth, *Access to Justice* | Sijthoff/Noordhoff, 1978 | varia por volume | sugerido, não recuperado |
| Kevin D. Ashley, *Artificial Intelligence and Legal Analytics* | Cambridge University Press, 2017 | 978-1107171503 | sugerido, não recuperado |
| Krippendorff, *Content Analysis: An Introduction to Its Methodology* | Sage, várias edições | varia | sugerido, não recuperado |
| Jurafsky & Martin, *Speech and Language Processing* | várias edições | varia | sugerido, não recuperado |

**(b) Literatura jurídica brasileira: tabela vazia.** Nenhuma monografia brasileira apareceu em duas ou mais das
obras recuperadas. A ferramenta anotou que os clássicos de processo civil, acesso à justiça, litigância de má-fé
e abuso processual "deveriam ser examinados em uma busca bibliográfica brasileira dedicada", mas que atribuir
edições e contagens sem inspecionar as listas violaria a regra de "só obras reais e verificáveis".

**Consequência prática:** os livros brasileiros precisam de uma busca separada — é o Prompt B do arquivo de
prompts, e/ou consulta direta a catálogos (BDJur/STJ, Biblioteca do TJAL, catálogos das editoras). Vale fazer
antes de escrever o referencial normativo.

## 3. Lacunas que posicionam o artigo

O levantamento apontou três, e as três sustentam a contribuição:

1. **Quase não há pesquisa empírica em larga escala em que a litigância abusiva/predatória seja anotada
   manualmente a partir de decisões, com estatística de concordância publicada.** É exatamente o que o protocolo
   de anotação + o κ do passo 22 produzem.
2. **A literatura brasileira que conecta a doutrina do CNJ/STJ sobre litigância predatória a uma medição
   validada por NLP é extremamente limitada.** Nosso léxico versionado + validação contra padrão-ouro ocupa essa
   lacuna.
3. **A literatura de PU learning estuda rótulos ausentes por mecanismos estatísticos**, não por um mecanismo
   institucional como "o tribunal sinalizou". A sinalização judicial é um rótulo de outra natureza — e a
   conclusão do próprio levantamento é que o artigo deve ser enquadrado como **validade de medida sob rótulos
   institucionais unilaterais**, dizendo que os modelos detectam *padrões associados à sinalização do STJ*, e não
   abuso objetivamente estabelecido.

Esse enquadramento é uma sugestão externa; a decisão é do pesquisador, mas ela é compatível com o que já está
escrito no `CLAUDE.md` §§2, 3 e 10.

## 4. Próximo passo

1. Prompt B (fatia brasileira) e Prompt C (livros) no mesmo chat — a base internacional já está coberta.
2. Eu verifico o retorno com `scripts/91_verify_references.py` e atualizo `notes/references_candidates.bib`.
3. Você aprova o que entra em `article/references.bib`.

---

# Fatia brasileira (Prompt B, 23/09/2026)

Mesma conversa, segunda rodada. 12 DOIs sugeridos, **11 verificados no Crossref/DataCite, 1 não resolvido**
(`10.31501/ealr.v10i2.9637`, Economic Analysis of Law Review — fica na lista "não verificado, não citar").
BibTeX em `notes/references_candidates_br.bib`.

## 5. Artigos brasileiros verificados

| obra | ano | DOI |
|---|---|---|
| *As demandas predatórias como fator de violação do princípio da razoável duração* | 2023 | `10.51891/rease.v9i9.11541` |
| *A atuação da OAB seccional Tocantins nas discussões* (demandas predatórias) | 2024 | `10.55892/jrg.v7i14.1173` |
| *Demandas predatórias: uma análise comparativa da compreensão e impacto* | 2025 | `10.55892/jrg.v8i18.2044` |
| *A exigência de políticas públicas para a contenção da litigância predatória* | 2024 | `10.69849/revistaft/ni10202411110704` |
| *Judicialização predatória: causas, consequências e impactos financeiros* | 2024 | `10.69849/revistaft/ni10202411151457` |
| *Dano processual nas ações de família: assédio processual e suas implicações* | 2024 | `10.55905/revconv.17n.8-167` |
| *Do vexatious litigant ao assédio processual: uma aplicação do direito comparado* | 2025 | `10.33448/rsd-v14i9.49620` |
| *Acesso à justiça e litigância habitual: meios consensuais adequados e incentivos* (dissertação, USP) | 2023 | `10.11606/d.2.2023.tde-28022024-080851` |
| *Análise bibliométrica dos artigos científicos de jurimetria publicados no Brasil* | 2020 | `10.20396/RDBCI.V18I0.8658889` |
| *Transforming Justice* (governança digital no Judiciário) | 2025 | `10.59490/dgo.2025.1049` |
| *Towards Responsible AI Governance in the Brazilian Judiciary* (AIES) | 2025 | `10.1609/aies.v8i3.36774` |

Observação de qualidade: boa parte sai de periódicos de fluxo contínuo e baixo fator de impacto. São úteis para
mostrar que o tema é discutido, **não** como evidência empírica — e o próprio levantamento diz isso.

## 6. Livros brasileiros

**(1) Efetivamente citados no material recuperado** — apenas dois, e nenhum com referência completa:

| autor | obra | onde apareceu |
|---|---|---|
| Alexandre Freitas Câmara | obra de processo civil (citada como "Câmara, 2014, p. 470") | em *As demandas predatórias como fator de violação do princípio da razoável duração* |
| Cassio Scarpinella Bueno | manual/curso de direito processual civil | citado em Cunha & Barros (2025), sem referência completa exposta |

A ferramenta recusou-se explicitamente a "transformar isso numa lista longa": sem os PDFs, não dá para afirmar
que Didier, Dinamarco ou Wambier foram efetivamente citados nesses trabalhos.

**(2) Canônicos, sugeridos e não recuperados** (edição/ISBN **não confirmados**, exceto onde indicado):

- *Processo civil, boa-fé e abuso processual:* Fredie Didier Jr., **Curso de Direito Processual Civil**
  (JusPodivm); Humberto Theodoro Júnior, **Curso de Direito Processual Civil** (Forense); Cassio Scarpinella
  Bueno, **Manual de Direito Processual Civil** (Saraiva); Alexandre Freitas Câmara, **O Novo Processo Civil
  Brasileiro** (Atlas); José Carlos Barbosa Moreira (obras sobre efetividade); Cândido Rangel Dinamarco,
  **Instituições de Direito Processual Civil** (Malheiros).
- *Acesso à justiça:* Mauro Cappelletti & Bryant Garth, **Acesso à Justiça**, tradução de Ellen Gracie
  Northfleet, Porto Alegre: Sergio Antonio Fabris Editor, 1988 — **é o único com dados bibliográficos completos**.
- *Tutela coletiva e repetitividade:* Ada Pellegrini Grinover, Kazuo Watanabe et al. (obras coletivas sobre
  processo coletivo e CDC); Kazuo Watanabe (acesso à ordem jurídica justa); Aluísio Gonçalves de Castro Mendes
  (ações coletivas); Sofia Temer, **Incidente de Resolução de Demandas Repetitivas** (JusPodivm).
- *Jurimetria e pesquisa empírica:* a busca **não** recuperou referências completas e verificáveis de livros
  brasileiros de jurimetria — a ferramenta preferiu deixar a subseção curta a inventar metadados.

**Como usar esses manuais (advertência da própria ferramenta):** eles situam boa-fé processual, deveres das
partes, litigância de má-fé, abuso de posições processuais e sanções. **Não** servem como evidência empírica da
prevalência de litigância predatória. Para o nosso artigo, entram na seção normativa, não nos resultados.

**O que falta fazer:** confirmar edição, ano, editora e ISBN de cada um nos catálogos (BDJur/STJ, catálogos das
editoras, Biblioteca Nacional). Isso é trabalho de catálogo, não de IA — eu faço quando você aprovar a lista.

## 7. "O que NÃO encontrei" — e por que isso sustenta o artigo

A resposta trouxe uma seção própria com esse título, e ela é o achado mais valioso da rodada:

> Não encontrei literatura empírica brasileira madura que meça diretamente "litigância predatória" em grandes
> bases de decisões judiciais.

Em particular, não apareceu **nenhum** estudo que simultaneamente: (1) defina unidade observacional de
processo/decisão; (2) operacionalize litigância predatória com critérios reprodutíveis; (3) construa um corpus
judicial grande; (4) faça dupla anotação jurídica independente; (5) publique estatística de concordância; (6)
compare regras, modelos estatísticos e ML; (7) reporte precisão, revocação, taxa de falsos positivos e
calibração; (8) valide temporal ou entre tribunais; (9) investigue desigualdade territorial e por classe
processual dos falsos positivos.

Essa lista de nove itens é, ponto a ponto, o desenho que já está implementado ou especificado neste repositório —
é o argumento de contribuição pronto, e vale citá-lo na introdução como lacuna.

Dois achados laterais igualmente úteis: **não há avaliação quantitativa independente e publicada do NUMOPEDE**
(sensibilidade, especificidade, VPP, taxa de falsos positivos ou desfechos posteriores dos casos sinalizados); e
nos periódicos de referência (Revista de Processo, RDC, REED, Direito GV, Civil Procedure Review) a busca não
produziu conjunto substancial de artigos dedicados à **mensuração empírica** do fenômeno.
