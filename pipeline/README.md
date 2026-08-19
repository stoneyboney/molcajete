# molcajete-prep

The desktop half of Molcajete. Turns a DRM-free EPUB into a `schemaVersion: 1`
bundle the reader PWA can import, plus a plain-text report describing what the
SPEC §5 rules would teach.

Network access is fine here. The reader is the half that must stay offline.

## Setup

```bash
cd pipeline
uv sync
```

That installs the dependencies and the `es_core_news_sm` spaCy model (pulled
from its GitHub release; the models are not on PyPI).

Python is pinned to 3.13 in `.python-version`. spaCy 3.8 ships no cp314 wheels,
so building under 3.14 would compile spacy, thinc and blis from source.

### Wiktionary extracts (needed for glossing)

```bash
uv run python -m molcajete_prep.glossing.sources --fetch
```

Downloads two whole-edition wiktextract dumps from kaikki.org into
`pipeline/cache/` (gitignored): English Wiktionary at 2.6 GB compressed, German
at 288 MB. Re-running is a no-op unless the checksum changed, and `--force`
picks up kaikki's weekly refresh. Without the flag the command just reports
what is present.

kaikki publishes per Wiktionary *edition*, not per target language, so the
English dump covers hundreds of languages and Spanish is filtered out of it as
it streams — about a minute, once. The per-language files kaikki also offers are
marked deprecated there and are not used.

### A gloss provider

Wiktionary cannot get near the SPEC §12 target of a German gloss on 95% of the
teach set — German Wiktionary holds about 6,600 Spanish entries against a book's
nine thousand lemmas — so something has to write the rest. There are two
options, chosen with `--gloss-provider`.

**Claude** (`--gloss-provider claude`, the default) uses the Message Batches API:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Read from the environment only; nothing writes it to disk.

**Ollama** (`--gloss-provider ollama`) runs a model on this machine. No key, no
account, no network beyond the loopback interface:

```bash
brew install ollama
brew services start ollama
ollama pull gemma3:12b
```

`gemma3:12b` is the default and is about 8 GB. Google's multilingual line is
strong at translation and writes idiomatic German, which is what a gloss with
the right article needs. `--gloss-model qwen3:8b` is faster and smaller;
`--gloss-model mistral-small3.2:24b` knows more and needs 14 GB.

Builds that pass `--gloss-offline` or `--no-gloss` need neither provider.

## Running

```bash
uv run python build_bundle.py sources/book.epub --out ../bundles/
```

Writes `../bundles/<book-id>.molcajete.json` and `../bundles/<book-id>.report.txt`.

Useful flags:

| Flag | Effect |
|---|---|
| `--book-id`, `--title`, `--author` | Override what was read from the EPUB metadata |
| `--split-on-heading` | Split each spine document on `<h1>`–`<h6>`. Use when an edition packs several chapters into one file. |
| `--include-documents GLOB…` | Keep only the spine documents matching these globs — for critical editions, see below |
| `--exclude-documents GLOB…` | Drop the spine documents matching these globs. Applied after `--include-documents`. |
| `--known path/to/known.json` | Treat these lemmas as already known (Phase 5; defaults to empty) |
| `--report-only` | Print the report to stdout, write nothing |
| `--gloss-offline` | Wiktionary and the cache only. No model, no spend. |
| `--no-gloss` | Skip glossing entirely — **also changes what is taught**, see below |
| `--gloss-provider ollama` | Gloss with a local model instead of the Claude API |
| `--gloss-model NAME` | Override the provider's model (`claude-haiku-4-5`, `qwen3:8b`, …) |
| `--gloss-limit N` | Send at most N lemmas to the model, most-used first |
| `--regloss` | Ignore cached glosses and fetch them again |
| `--de-wiktionary verbatim` | Take short German Wiktionary glosses as they stand, instead of demoting them to context |

Local-model flags — `--gloss-concurrency` (default 2), `--gloss-retries`
(default 1), `--gloss-chunk` (default 1 locally, 25 for Claude) — are described
under **Running a local model** below.

## Seeding what you already know

Without a seed the app teaches you *tener* and *más*: unseeded, the first
chapter of `Los de abajo` asks for 263 cards across 15 sessions. SPEC §8 answers
that with your Anki collection.

```bash
# Anki: File -> Export -> Notes in Plain Text (.txt), your Spanisch:: decks
uv run python seed_known.py ~/Desktop/Spanisch.txt --out known.json
uv run python build_bundle.py "sources/Los de abajo.epub" --known known.json …
```

### Trying it without your deck

```bash
uv run python make_test_deck.py            # writes test-deck.anki.txt
uv run python seed_known.py test-deck.anki.txt --out known.json
```

200 of the commonest Spanish words as a synthetic export, German in the first
column so the detection has to earn its answer. `--count` takes fewer or more.

What a 200-word seed is worth, measured on `Los de abajo`:

| | chapter 1 | sessions | book coverage |
|---|---|---|---|
| nothing seeded | 263 cards | 15 | 4.3% |
| top-200 seed | 211 cards | 12 | **61.3%** |

Coverage leaps and the teach set barely moves. That is the closed-class rule
showing through rather than a bug: the commonest 200 Spanish words are mostly
function words, which the teach set never contained, so seeding them removes few
cards — but they are a large share of the *tokens* on the page, so marking them
known moves coverage enormously. `--count 1000` reaches the open-class
vocabulary where the cards actually are.

### How the column is chosen

An export is tab-separated notes with `#` headers, and the columns are whatever
the note type has — so **which column holds the Spanish is decided by looking,
and the working is always printed**:

```
Columns, by how Spanish they look:
  [0]    6% of    18 words   der Hund · die Katze · laufen
  [1]  100% of    17 words   el perro · el gato · correr <- chosen
  [2]    0% of     0 words   A1 · A1 · A1
```

The test is comparative — is a word *more* Spanish than it is German or English
— because "has Spanish ever seen this" says yes to most German too (*Hund*
scores 1.67 in Spanish). `--field N` overrides the guess, `--dry-run` writes
nothing, and `--merge` unions with an existing `known.json` so it stays
re-runnable as the deck grows.

Getting the column wrong is worth catching, which is why it prints: a lemma
marked known is never taught **and** counts as covered, so a German seed would
quietly skip words you actually need.

## Critical editions

A scholarly edition carries an introduction, endnotes, an analysis, a biography
and a bibliography in the same spine as the novel, and they are not the book.
Taken in, their words become the book's vocabulary and inflate the `bookCount`
that decides what gets taught — on prose you will never read — and they arrive
in the reader as chapters called *Bibliografía*.

The Marta Portal `Los de abajo` is the case that prompted the flags: three
documents of novel (~244 KB) against nine of apparatus (~200 KB).

```bash
uv run python build_bundle.py "sources/Los de abajo.epub" \
    --include-documents 'PrimeraParte*' 'SegundaParte*' 'TerceraParte*' \
    --split-on-heading \
    --book-id azuela-los-de-abajo --title "Los de abajo"
```

Look at the spine before choosing globs — `unzip -l book.epub` lists the
documents, and the table of contents names them. An include that matches nothing
is an error rather than an empty book.

Two things that edition also needs, both automatic:

- **Footnote markers are dropped.** An annotated edition writes them inline as
  `<a href="notas.xhtml#nt54"><sup>[54]</sup></a>`, which extracts as
  `federales[54]`. `<sup>` is treated as non-prose.
- **Chapter names come from the table of contents.** With `--split-on-heading`
  the headings of a packed part are often bare numerals, and the numbering
  restarts in each part — three chapters called `I`. The TOC addresses each one
  by fragment and names it properly, so `Los de abajo` comes out as 42 chapters
  with 42 distinct titles.

## Glossing

Sources, cheapest first: the shared cache, then English Wiktionary (English
glosses and the region labels), then German Wiktionary (thin — about 6,600
Spanish entries), then whichever provider is selected, for everything that still
has no German gloss.

### German Wiktionary is context by default

`--de-wiktionary` decides whether a *short* German Wiktionary gloss is used as
it stands. It defaults to `context-only`, meaning it is not: every German gloss
is written by the model, with the Wiktionary text passed along as a hint.

The reason is that fitting on a card and teaching the word are different tests.
German Wiktionary glosses `lunes` as "der erste Wochentag" — four words, fits
fine, and reads like a riddle. Length is the only thing a filter can measure;
whether the text names the thing is not. Only the model has the book's own
sentence in front of it. `--de-wiktionary verbatim` restores the old behaviour.

**Glossing runs before classification, not after.** `mexicanism` is one of the
three SPEC §5 teach rules, so the flag has to exist before the rules are
applied. The practical consequence: `--no-gloss` does not merely omit glosses,
it changes which lemmas are taught, because that rule can never fire. The
report says which mode produced it.

### The cache

The gloss cache at `pipeline/cache/glosses.sqlite3` is keyed on
`(lemma, pos, provider, model)` and shared across books, which is what makes the
second book nearly free. It is derived data — deleting it costs a rebuild,
nothing more.

The provider is part of the key because a gloss from Sonnet and one from a 12B
model on this laptop are two different claims about the same word. The
Wiktionary rows deliberately are *not* scoped that way: they record what the
dictionaries said, which no model wrote, so every provider reads them. That is
what keeps a rebuild warm — the empty rows recording "we looked and found
nothing" are the reason a second build does not re-stream 3.1 GB of dumps, and
scoping them per provider would have undone that the moment anyone switched.

One trade it makes deliberately: a model's gloss was disambiguated against one
book's example sentence, so reusing it in a book that uses a different sense of
the word is wrong. Each row records the sentence and the book that produced it,
the report counts cache hits, and `--regloss` forces a fresh pass.

An existing pre-provider cache is migrated in place on first open.

## Running a local model

```bash
uv run python build_bundle.py sources/noches.epub --gloss-provider ollama
```

A local model follows instructions less reliably than a hosted one, and the
local path is written for that rather than hoping otherwise:

- **Answers are checked, not trusted.** The echoed lemma must match what was
  asked, and the one-to-three-words rule is re-derived in Python rather than
  believed. A gloss that breaks it is rejected.
- **One stricter retry, then a miss.** A rejected answer is sent back with its
  own text quoted and the rule restated (`--gloss-retries`). If it still fails,
  the lemma is recorded as ungloszed and counted in the report. Nothing guesses,
  and nothing crashes the build.
- **One lemma per request** (`--gloss-chunk`). Claude batches 25 because a
  cached prompt prefix is worth amortizing; locally there is no bill, and a
  12B model asked for 25 aligned objects starts merging and dropping them.
- **Two requests in flight** (`--gloss-concurrency`). One already saturates the
  GPU and more is measurably *slower* — gemma3:12b on an M4 Pro/24 GB does 20
  lemmas in 81 s at concurrency 2, 84 s at 4, 96 s at 6.

### How long a book takes

About **0.2 lemmas per second** — measured at 0.25 on `las-noches` and 0.19 on
`Los de abajo`, both gemma3:12b on an M4 Pro. So a five-thousand-lemma novel is
around six hours and a nine-thousand-lemma one is ten. That is not a problem to
fix so much as a fact to plan around: start it and go to bed. The gloss cache
means you pay it once across all books, and `--gloss-limit` is there if you want
the commonest few hundred lemmas glossed now and the tail later.

Do not trust the progress counter in the log as a rate. It reports chunks
dispatched and completed in memory; what has actually been *kept* is rows in the
cache:

```bash
sqlite3 cache/glosses.sqlite3 \
  "select count(*) from glosses where provider='ollama';"
```

### An interrupted pass keeps its work

Glosses are written to the cache as each chunk lands, not once at the end, and
the cache is read before the provider is called. So a run that is killed — a
closed lid, a stopped process, a restarted Ollama — loses at most the chunk in
flight, and starting it again asks only for what is still missing. Re-run the
same command; there is no resume flag.

This was not always true. The first full pass over `Los de abajo` was killed at
2,067 of 4,811 lemmas and left **nothing** behind, because the pass persisted
only on completion. About an hour of compute, discarded. If you are changing
`glossing/pipeline.py`, keep the write inside the `on_written` callback.

An unreachable Ollama server stops the build rather than producing a bundle with
no glosses in it. Everything else is a number in the report.

### Trying it on 200 lemmas first

```bash
uv run python gloss_trial.py sources/noches.epub \
    --provider ollama --model gemma3:12b \
    --gold gold/mexicanisms.txt \
    --out ../bundles/gloss-trial-ollama.txt
```

Glosses a stratified sample and writes the answers out. Writes no bundle and
never touches the shared cache. Worth running before the first full book, and
again after any change to the prompt. Pass `--model` more than once to compare
local models side by side.

`--gold` scores mexicanism recall against a list of lemmas already known to be
Mexican — `pipeline/gold/mexicanisms.txt`, one lemma per line. It is the only
measurement in the trial that is not self-reported: everything else says how
confidently the model answered, and this says whether it was right about the
flag SPEC §5 teaches from. Scoring covers only the gold lemmas the book actually
contains, and those are force-added to the sample; the rest are listed as absent
rather than counted as misses.

## Tests

```bash
uv run pytest -q
```

Tests run against a synthetic fixture EPUB built at test time — no book text is
committed to the repo.

## Getting a source EPUB

`pipeline/sources/` is gitignored. Put DRM-free EPUBs there.

**DRM-free only.** The pipeline contains no DRM circumvention and never will;
where a book is unavailable DRM-free, the answer is to read it on paper.

### On `Los de abajo`

**It is here now.** `sources/Los de abajo.epub` is the Marta Portal edition,
DRM-free, Spanish original. Build it with the invocation under **Critical
editions** above — it needs the document filter, because that edition ships as
much apparatus as novel.

The history is worth keeping, because SPEC §13.4 is wrong and someone will
follow it. It says the novel is on Project Gutenberg; it is not. Gutenberg
carries only the 1929 English translation (*The Underdogs*, ebook 549), and the
Spanish original is absent from Gutenberg, Spanish Wikisource and textos.info,
while the Internet Archive copies are DRM-locked scans of modern in-copyright
editions. The novel itself is public domain in Germany (Azuela died 1952) and
the US (published 1915) — the obstacle was only ever finding a clean DRM-free
EPUB.

Manuel Payno's *Las noches mejicanas* remains a useful second text, and is one
`curl` away:

```bash
mkdir -p sources
curl -Lo sources/noches.epub https://www.gutenberg.org/ebooks/54430.epub3.images
```

Nothing in the pipeline is book-specific.
