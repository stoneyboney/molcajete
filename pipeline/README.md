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
