# Retrieval evaluation – method

Results: [results.md](results.md) · questions: [questions.yaml](questions.yaml) · expected postings: [labels.json](labels.json)

```bash
python -m rag.eval.run_eval --label   # derive labels.json from the criteria (only when questions change)
python -m rag.eval.run_eval           # build a fresh index from the snapshot, score, write results.md
```

## How the set was built

1. **Frozen data.** `snapshot.db` is a copy of `data/history.db` from 2026-11-16 (105 postings, 86 online).
   Postings change daily; a frozen copy keeps the numbers reproducible. It contains no description text.
2. **Questions first, labels from rules.** 20 questions in German and English, each with an objective
   criterion (skills, role, title or company pattern, work mode, appearance date). `--label` derives the
   expected postings from the criteria. Questions and labels were committed *before* the first evaluation
   run (see the git history).
3. **Label review without search results.** Reading the derived labels before any run showed two
   criterion errors, fixed before the first run: `steuer` also matched "Waren*steuer*ung", and the time
   rule counted the first collection day (which saw the whole backlog) as "new". The second one was a
   real bug in the retrieval's time filter too.
4. **No tuning on the test set.** Nothing was changed to improve these numbers after the first run.

## Confidence gate ("keine passenden Anzeigen gefunden")

Chosen on 10 development queries that are **not** in the evaluation set (current postings, E5 index):

| query group | best similarity | best − median | BM25 hits |
|---|---|---|---|
| related (Buchhaltung, UX Design, Projektmanagement, Einkauf, quality management) | 0.862–0.892 | 0.026–0.061 | 1–15 |
| unrelated (Bäckerei, Kita, Gartenarbeit, Friseur, Taxifahrer) | 0.804–0.823 | 0.018–0.030 | 0 |

The gap-to-median rule overlapped, so the gate became: confident if a filter from the question matched,
one of the top three shares a word with the question, or the best similarity is ≥ 0.84.

**Known flaw, found by the evaluation:** none of the unrelated dev queries contained the word
"Werkstudent", which appears in almost every posting. "Werkstudent in einer Zahnarztpraxis" therefore
passes the 0.84 threshold and is wrongly treated as relevant. Fixing it needs a new dev set (and new
held-out no-answer questions), not a threshold picked to pass q19. With generation (milestone 3) the
model gets a second chance to say that none of the retrieved postings fit.

## Caveats

- **Circular questions.** Skill and time questions are solved by the parser's filters, which use the same
  rules as the labels. The report splits results into *filter-solvable* and *search* questions; only the
  second group says much about ranking.
- **Lexical bias.** The search questions were written by the same person who knows the titles, so they
  often share words with them. That favours BM25; real users may phrase things differently.
- **Small sample.** 18 answerable and 2 unanswerable questions over 86 current postings – one question
  moves a group's hit rate by 10 percentage points.
- **Structured documents only.** The index has no description text (privacy design), so questions about
  tasks inside a posting can only match via title, role and skills.
