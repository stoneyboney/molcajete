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

### API key (needed for the Claude gloss fallback)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Read from the environment only; nothing writes it to disk. Builds that pass
`--gloss-offline` or `--no-gloss` never need it.

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
| `--known path/to/known.json` | Treat these lemmas as already known (Phase 5; defaults to empty) |
| `--report-only` | Print the report to stdout, write nothing |
| `--gloss-offline` | Wiktionary and the cache only. No API calls, no spend. |
| `--no-gloss` | Skip glossing entirely — **also changes what is taught**, see below |
| `--gloss-limit N` | Send at most N lemmas to Claude, most-used first |
| `--regloss` | Ignore cached glosses and fetch them again |
| `--de-wiktionary context-only` | Let Claude write every German gloss instead of taking short ones from German Wiktionary verbatim |

## Glossing

Three sources, cheapest first: the shared cache, then English Wiktionary
(English glosses and the region labels), then German Wiktionary (thin — about
6,600 Spanish entries), then Claude for whatever still has no German gloss.

**Glossing runs before classification, not after.** `mexicanism` is one of the
three SPEC §5 teach rules, so the flag has to exist before the rules are
applied. The practical consequence: `--no-gloss` does not merely omit glosses,
it changes which lemmas are taught, because that rule can never fire. The
report says which mode produced it.

The gloss cache at `pipeline/cache/glosses.sqlite3` is keyed on `(lemma, pos)`
and shared across books, which is what makes the second book nearly free. It is
derived data — deleting it costs a rebuild, nothing more.

One trade it makes deliberately: a Claude gloss was disambiguated against one
book's example sentence, so reusing it in a book that uses a different sense of
the word is wrong. Each row records the sentence and the book that produced it,
the report counts cache hits, and `--regloss` forces a fresh pass.

### Trying it on 200 lemmas first

```bash
uv run python gloss_trial.py sources/noches.epub --out ../bundles/gloss-trial.txt
```

Glosses a stratified sample at two settings and writes both answers out, for
roughly ten cents. Writes no bundle and never touches the shared cache. Worth
running before the first full book, and again after any change to the prompt.

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

SPEC §13.4 names Azuela's *Los de abajo* as the first development text and says
it is on Project Gutenberg. It is not. Gutenberg carries only the 1929 English
translation (*The Underdogs*, ebook 549). The Spanish original is absent from
Gutenberg, Spanish Wikisource and textos.info; the Internet Archive copies are
DRM-locked scans of modern in-copyright editions.

The novel itself is public domain in Germany (Azuela died 1952) and the US
(published 1915) — the obstacle is purely that no clean DRM-free EPUB of it is
freely downloadable. Until one turns up, develop against any Spanish EPUB from
Gutenberg. Manuel Payno's *Las noches mejicanas* is Mexican and works well:

```bash
mkdir -p sources
curl -Lo sources/noches.epub https://www.gutenberg.org/ebooks/54430.epub3.images
```

Nothing in the pipeline is book-specific. Swapping *Los de abajo* in later is
one CLI invocation.
