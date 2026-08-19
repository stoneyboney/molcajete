# molcajete-book

The desktop half of Molcajete. Turns a DRM-free EPUB into a `schemaVersion: 1`
bundle the reader PWA can import, plus a plain-text report describing what the
SPEC §5 rules would teach.

The language half — lemmatisation, the lexicon, glossing, the teach rules, the
Anki seed — is **[`molcajete-prep`](../../molcajete-prep)**, a separate package,
so that a second reader can depend on it rather than fork it. What lives here is
everything that knows about books: the EPUB reader, the bundle schema, the
report. Read that package's README for anything about glosses, providers, the
cache or the seed.

Network access is fine here. The reader is the half that must stay offline.

## Setup

```bash
cd pipeline
uv sync
```

`molcajete-prep` is resolved from `../../molcajete-prep` as an editable install
while both repos are moving — edit the package and this suite sees it with no
reinstall. `[project.dependencies]` carries the version range that a release
would resolve against; swap the `[tool.uv.sources]` entry for a git tag when the
package settles.

Python is pinned to 3.13 in `.python-version`. spaCy 3.8 ships no cp314 wheels,
so building under 3.14 would compile spacy, thinc and blis from source.

### Wiktionary extracts (needed for glossing)

```bash
uv run python -m molcajete_prep.glossing.sources --fetch
```

**No `--dir` any more.** The extracts and the gloss cache live in
molcajete-prep's own default location, `$XDG_CACHE_HOME/molcajete-prep/`, and
the package's default is now simply correct. They moved out of `pipeline/cache/`
when Rocola became the second consumer: what is in there is data about Spanish
rather than about this book, and a per-repo copy means re-downloading 2.9 GB of
extracts and re-inferring glosses that already exist next door.

**A cold build is no longer `rm -rf pipeline/cache`.** That directory is gone,
and deleting the shared one throws away Rocola's glosses too. Pass
`--cache-dir` somewhere empty instead:

```bash
uv run build_bundle.py … --cache-dir /tmp/cold-cache
```

### A gloss provider

`--gloss-provider claude` (the default) needs `ANTHROPIC_API_KEY` in the
environment. `--gloss-provider ollama` needs a local Ollama and no key. Builds
that pass `--gloss-offline` or `--no-gloss` need neither. The package README has
the details and the measurements.

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
| `--known path/to/known.json` | Treat these lemmas as already known (defaults to empty) |
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
in the package README.

**Glossing runs before classification.** `mexicanism` is one of the three SPEC
§5 teach rules, so `--no-gloss` does not merely omit glosses, it changes which
lemmas are taught, because that rule can never fire. The report says which mode
produced it.

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
uv run python make_test_deck.py --count 1000   # writes test-deck.anki.txt
uv run python seed_known.py test-deck.anki.txt --out known.json
```

Both are thin shims over `molcajete_prep`; the word list and the column
detection are described there. What a seed is worth, measured on
`Los de abajo`:

| | chapter 1 | sessions | whole book | coverage |
|---|---|---|---|---|
| nothing seeded | 263 cards | 15 | 2,717 | 4.3% |
| top 200 | 211 cards | 12 | 2,553 | 61.3% |
| top 1000 | **129 cards** | **8** | **1,814** | **75.7%** |

The two seeds do different jobs, and the difference is the point. At 200,
coverage leaps and the teach set barely moves — the commonest words are function
words, which the teach set never contained, so seeding them removes few cards
while covering a large share of the *tokens* on the page. At 1000 the open-class
vocabulary starts coming out and the cards go with it: chapter 1 halves, and 900
cards leave the book.

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

## Trying the glossing on 200 lemmas first

```bash
uv run python gloss_trial.py sources/noches.epub \
    --provider ollama --model gemma3:12b \
    --out ../bundles/gloss-trial-ollama.txt
```

Glosses a stratified sample and writes the answers out. Writes no bundle and
never writes to the shared cache — it reads the extracts from it, but its own
answers stay in the report. Worth running before the first full book, and
again after any change to the prompt. Pass `--model` more than once to compare
local models side by side.

`--gold` now defaults to the mexicanism list shipped inside `molcajete-prep`;
pass a path to score against your own.

## Tests

```bash
uv run pytest -q
```

Tests run against a synthetic fixture EPUB built at test time — no book text is
committed to the repo. `tests/test_prep_integration.py` is where package code is
exercised *through* this half: the EPUB reader and the §4 schema are the parts
`molcajete-prep` deliberately does not have.

The `nlp` and `extracts` fixtures and the two autouse guards come from
`molcajete_prep.pytest_plugin`, not from `conftest.py`.

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

Nothing in this half is book-specific either — it is EPUB-specific.
