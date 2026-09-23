# Prompts para o SciSpace — revisão de literatura do artigo 5

Artigo: *Detecting Patterns of Abusive Litigation: An Explainable and Human-Centered Jurimetric Framework*
(STJ, 2021–2025; Rec. CNJ 159/2024; Tema 1198/STJ; triagem assistida, nunca decisão automatizada).

**Como usar.** Prompt A no modo de revisão/*Deep Review* (é o principal e já pede os livros). Prompt B depois,
para a literatura brasileira, que o SciSpace indexa mal. Prompt C é a segunda passada só sobre livros. Prompt D
é para posicionar a contribuição. Cada um é autocontido: cole inteiro, sem editar.

**Regra de volta ao repositório.** Nada entra em `article/references.bib` direto. O que voltar do SciSpace vai
para `notes/references_candidates.bib` com o DOI; eu confiro cada referência no Crossref/DOI antes de promover —
referência sem DOI verificável ou que não bater com o título não entra. (Mesmo protocolo que usamos no
tourism-gravity.)

---

## Prompt A — revisão principal (colar no SciSpace, em inglês)

```text
I am writing an empirical jurimetrics article titled "Detecting Patterns of Abusive Litigation: An Explainable
and Human-Centered Jurimetric Framework".

Design: I use the full text of STJ (Superior Tribunal de Justica, Brazil) terminative decisions and judgments
published from 2021 to 2025 (about 3.5 million documents), plus the structured espelhos de acordaos and the CNJ
DataJud procedural metadata. The labelling strategy is JUDICIAL SIGNALLING: the unit is a decision, and the
positive class is a decision in which the court itself recognises indications of abusive or predatory litigation
and grounds a measure on them. A versioned regex lexicon, built from Annex A of CNJ Recommendation 159/2024 and
from STJ Theme 1198, selects reading candidates; the labels come from manual legal annotation with a written
protocol and an agreement check. Methods: transparent rule-based measurement, regularised logistic regression and
gradient boosting over TF-IDF/embeddings plus procedural metadata, positive-unlabelled learning, anomaly
detection as contrast, SHAP and local explanations, temporal and cross-court validation, fairness checks by
territory and case class. The system is a triage aid for human review, never an automated decision.

Find peer-reviewed literature, and working papers from recognised venues, in these six blocks:
1. Abusive, predatory, vexatious and frivolous litigation: definition, measurement and sanctions; repeat players
   and the structure of mass claiming (e.g. Galanter; Hensler; Bone on frivolous litigation; Kritzer on Rule 11
   sanctions; the UK claims-management and whiplash reforms; Australian vexatious proceedings legislation).
2. Court screening and gatekeeping and its measured effects: pleading standards and dismissal (Twombly/Iqbal
   empirics, Gelbach, Hubbard), standing and interest to sue, pre-filing orders, docket control, and the
   evidence on how screening changes who reaches a court.
3. Legal analytics and NLP on judicial decisions: text-as-data validity, citation and reasoning extraction,
   judgment classification and prediction (e.g. Grimmer & Stewart; Livermore & Rockmore; Aletras; Katz;
   Chalkidis; Zhong), including Brazilian legal NLP (LeNER-Br, Ulysses, Victor/STF).
4. Learning with weak, scarce or one-sided labels, and annotation quality: positive-unlabelled learning (Elkan &
   Noto; Bekker & Davis), weak supervision (Ratner et al./Snorkel), anomaly and outlier detection (Isolation
   Forest, LOF), annotation protocols and inter-annotator agreement in legal corpora (Artstein & Poesio;
   Krippendorff).
5. Explainability, contestability and error costs of decision support inside courts and public administration:
   interpretable vs post-hoc explanation (Rudin; Ribeiro/LIME; Lundberg/SHAP), technological due process (Citron;
   Citron & Pasquale), human-in-the-loop and automation bias (Green & Chen; Skitka), risk-assessment fairness
   debates (Berk et al.; Angwin et al.), and what they imply for false positives against individual litigants.
6. Access to justice and litigation volume as a system-level phenomenon: litigation rates, court congestion,
   repeat players versus one-shotters, and how institutions distinguish legitimate mass litigation from abuse
   (Sandefur; Hadfield; Brazilian evidence including CNJ Justica em Numeros and IPEA/FGV studies).

For every work, return a row with: citation and DOI or stable URL; block (1-6); jurisdiction; research question
in one sentence; data (corpus, size, years, unit of analysis); method (name the models); how the ground truth was
produced and whether human annotation was validated (give the agreement statistic and its value); metrics
reported; what the authors say about false positives and their cost; the main limitation the authors state; and
why it matters for a study that uses judicial signalling as the labelling strategy.

BOOKS - DO THIS EXPLICITLY. Besides the articles, mine the reference lists of the works you retrieve and report
the BOOKS (monographs, treatises, edited volumes, handbooks) that recur across them. Give a separate ranked table
with: title, author/editor, edition, year, publisher, ISBN, how many retrieved works cite it, its block, and one
line on what it is used for (theory, method, jurisdiction background). Split it into (a) international and
methodological books and (b) Brazilian legal literature. Rank by number of citing works and keep anything cited
by two or more. If a canonical book of a block does not appear in the retrieved set, name it anyway and mark it
"suggested, not retrieved".

Also return: a 3-5 sentence map of each block saying what is settled and what is contested; the 10 most cited
works overall with citation counts; and BibTeX for everything, with DOIs.

Rules: only real, verifiable works; every entry carries a DOI, ISBN or stable URL; anything you cannot verify
goes to a separate "unverified - do not cite" list instead of being dropped or invented; do not paraphrase
abstracts as findings; include non-English work (Portuguese above all) and mark the language; and state
explicitly where the literature is thin.
```

---

## Prompt B — fatia brasileira (colar depois, em português)

```text
Faça agora um levantamento específico da literatura BRASILEIRA sobre litigância predatória, litigância abusiva,
demandas predatórias, advocacia predatória e assédio processual, incluindo:

- artigos em periódicos jurídicos brasileiros (Revista de Processo, Revista de Direito do Consumidor, Revista
  Brasileira de Direito Processual, Civil Procedure Review, revistas de tribunais e de escolas da magistratura);
- trabalhos empíricos e de jurimetria sobre litigiosidade, litigância de massa, repeat players e congestionamento
  judicial no Brasil (inclusive relatórios do CNJ, FGV, Insper, ABJ e IPEA, identificados como literatura cinzenta);
- estudos sobre o NUMOPEDE/TJSP e núcleos equivalentes de monitoramento de perfil de demandas;
- comentários e análises da Recomendação CNJ 159/2024, da Resolução CNJ 615/2025 e do Tema 1198 do STJ;
- trabalhos sobre uso de inteligência artificial pelo Judiciário brasileiro e suas balizas normativas
  (Resolução CNJ 332/2020 e sucessoras).

Para cada trabalho, traga: autoria, ano, veículo, DOI ou link estável, tipo (artigo, capítulo, livro, relatório,
dissertação/tese), se é empírico ou doutrinário, base de dados usada (se houver), e a tese central em uma frase.

LIVROS: ao final, liste os LIVROS brasileiros e traduções mais citados nesses trabalhos (manuais e tratados de
processo civil, obras sobre acesso à justiça, litigiosidade e tutela coletiva), com autor, edição, ano, editora e
quantos dos trabalhos levantados os citam. Ordene por recorrência.

Assinale explicitamente o que NÃO encontrou: se houver poucos trabalhos empíricos com dados e avaliação
quantitativa sobre o tema, diga isso com todas as letras — essa lacuna é parte do argumento do artigo.

Regra: só obras reais e verificáveis, com DOI, ISBN ou link estável. O que não puder verificar vai para uma lista
separada "não verificado — não citar".
```

---

## Prompt C — segunda passada, só livros (se o Prompt A devolver pouco)

```text
From the works you retrieved in the previous answers, extract ONLY the books and edited volumes. For each one:
title, author/editor, edition, year, publisher, ISBN, number of retrieved works citing it, and the strand it
serves. Then answer three questions in prose, citing the books:

1. Which books define the concept of litigation abuse / vexatious litigation and its limits, and how do they
   distinguish abuse from legitimate mass or repeat litigation?
2. Which books are the standard methodological references for (a) empirical legal research design, (b) text-as-
   data and NLP applied to legal corpora, and (c) annotation protocols and inter-annotator agreement?
3. Which books discuss algorithmic decision support inside courts, explainability and the cost of false
   positives for access to justice?

If a canonical book on any of the three is missing from the retrieved set, name it anyway and mark it as
"suggested, not retrieved from the corpus" with its ISBN, so it can be checked separately.
```

---

## Prompt D — posicionamento e lacuna (para a seção de contribuição)

```text
Based on everything retrieved, write a critical gap analysis (not a summary) answering:

- Has any published work used decisions that EXPLICITLY signal abusive litigation as the labelling strategy for
  a supervised or positive-unlabelled model? If yes, who, with what corpus and what accuracy; if no, say so.
- Has any work combined the text of judicial decisions with procedural trajectory metadata (docket movements,
  duration, court and subject) to study abusive filing? Name the closest attempts.
- How do existing works handle the fact that a keyword or an allegation is not a finding? What validation
  designs do they use?
- What is reported about transfer across courts (training on one court, testing on another) in legal text
  classification?
- Which fairness and access-to-justice risks are documented when screening tools are used against individual
  litigants, and what safeguards are recommended?

End with the three strongest objections a reviewer could raise against a study that infers patterns of abusive
litigation from decisions that flag it, and which literature already answers each objection.
```

---

## O que eu faço com o retorno

1. Você me manda o resultado (texto ou BibTeX).
2. Eu verifico cada item no Crossref/DOI e no ISBN, separo o que não bater e gravo em
   `notes/references_candidates.bib` com um comentário por entrada (strand, por que entra).
3. Só depois da sua aprovação as entradas sobem para `article/references.bib`.
4. Os livros recorrentes entram numa nota do `docs/` com a indicação de quais valem leitura integral — os
   metodológicos servem para a seção de Métodos, os processuais para a seção normativa.
