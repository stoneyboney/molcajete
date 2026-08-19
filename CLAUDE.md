# CLAUDE.md — Molcajete

Read `SPEC.md` before doing anything. This file contains the constraints that `SPEC.md` assumes but does not repeat. Where the two conflict, this file wins.

---

## What this is

A personal, single-user, offline-first Spanish reading app. It pre-teaches the vocabulary of a chapter as flashcards, then lets the user read that chapter with high word coverage.

- Target language: Spanish, Mexican variant (`es-MX`)
- Native languages: German (primary), English (secondary)
- Devices: iPhone and iPad, installed as a PWA via Add to Home Screen
- User: one person, the repo owner. Not a product.

### Naming — use these exact strings

| Where | Value |
|---|---|
| Repo / project | `molcajete` |
| npm package name | `molcajete` |
| PWA manifest `name` | `Molcajete` |
| PWA manifest `short_name` | `Molcajete` |
| Bundle file extension | `.molcajete.json` |
| Python package | `molcajete_prep` |

Do not abbreviate to `mol`, `mc`, or `molca` anywhere user-visible. Internal variable names may shorten freely.

---

## Hard constraints

These are not preferences. Violating one means the change gets reverted.

### 1. The reader makes zero network calls at runtime
After a bundle is imported, the app works with the device in airplane mode. No analytics, no telemetry, no CDN fonts, no remote translation API, no error reporting service. If a feature needs the network, it belongs in the prep pipeline, not the app.

### 2. No accounts, no server, no sync
There is no backend. There is no login. There is no user table. Storage is IndexedDB on the device. If a feature seems to need a server, it is out of scope — ask before building it.

### 3. Domain logic stays pure and portable
Everything in `src/domain/` must:
- import nothing from React, the DOM, `window`, Dexie, or any browser API
- be deterministic and synchronously testable
- pass dates and randomness in as arguments rather than reading the clock directly

This code will be ported to Swift later. Treat it as a library that happens to be consumed by a web app today.

### 4. Storage lives behind interfaces
Define `BookRepository`, `CardRepository`, `KnownLemmaRepository` as TypeScript interfaces in `src/domain/ports/`. Dexie implementations go in `src/infra/`. No component and no domain function may import Dexie directly.

### 5. Views compute nothing
Components receive fully-prepared view models as props and render them. No filtering, sorting, date maths, coverage calculation, or FSRS logic inside a component. If a component needs a derived value, derive it in the domain layer and pass it down.

### 6. The bundle format is a versioned contract
`schemaVersion` is present in every bundle and checked on import. Any change to the bundle shape increments it and comes with a migration path. The prep pipeline and the app are developed as if they were separate products maintained by different people — because eventually one of them will be rewritten in Swift.

---

## Settled product decisions

Do not relitigate these in code.

| Decision | Value |
|---|---|
| Gloss display | German large and primary; English small beneath it |
| Coverage | Displayed as a diagnostic; soft warning under 0.90; never blocks entry |
| Inline translation | None. Tap-to-reveal only. |
| "Reveal all glosses" toggle | Exists, off by default, does not persist across chapters |
| Card direction | ES → DE/EN recognition only. No production cards. |
| Session cap | 18 new cards. Split chapters into segments rather than exceeding it. |
| Scheduler | FSRS via `ts-fsrs`. Never hand-roll scheduling. |
| Source files | DRM-free EPUB only. No DRM circumvention code, ever. |

---

## Repo layout

```
/pipeline           Python 3.11+. Prep pipeline. Runs on desktop.
  build_bundle.py
  seed_known.py
  glossing/         Wiktionary + Claude batch fallback
  tests/
/app                React + TypeScript + Vite. The PWA.
  src/
    domain/         Pure logic. No browser imports. Heavily tested.
      ports/        Repository interfaces
    infra/          Dexie implementations of the ports
    ui/             Components. Dumb.
    app/            Wiring, routing, providers
  tests/
/bundles            Generated *.molcajete.json (gitignored except a small fixture)
SPEC.md
CLAUDE.md
```

---

## Working agreement

- **Build in the phase order from `SPEC.md` §12.** Do not start Phase 4 while Phase 3 is unfinished. Each phase ends with something usable by hand.
- **Tests are required for `src/domain/` and `/pipeline`.** Everything else is optional. The domain tests are the specification of the port target — write them as if someone will read them in Swift.
- **Commit per logical change** with a real message. No mega-commits spanning phases.
- **Ask before adding a dependency.** The current allowed set is in `SPEC.md` §9. Anything else needs a reason.
- **Prefer boring.** This app has five screens and one algorithm. Reach for a state machine library, a monorepo tool, or a component framework and the answer is no.

---

## Things that will be tempting and are wrong

- Adding a "quick translate whole paragraph" button. It defeats the entire premise.
- Running spaCy or any NLP in the browser. That's what the pipeline is for.
- Streaks, XP, daily goals, or any nudge mechanic. Explicitly unwanted.
- Storing FSRS state as anything other than the full card object. Partial state cannot be rescheduled.
- Teaching proper nouns. `PROPN` is skipped entirely — no card, no gloss.
- Generating production (DE → ES) cards "since we have the data anyway".
- Making the reader beautiful before it is correct. Phase 6 exists.

---

## Language and copy

All user-facing strings in the app are **German**. Card review buttons: `Nochmal / Schwer / Gut / Leicht`. The "I already know this" action reads `Ich kenne das`.

Code, comments, commit messages, and this documentation are in English.

---

## Current phase

**Phase 4 — Teaching loop. Built and green. Not verified on the device yet.**

`npm test` in `/app` is 167 tests across 11 files. The domain layer went in
first and the UI after it, per rule 3. What is *not* verified is the Dexie half
and the rendering: `tests/teachingLoop.test.ts` runs the whole flow over
in-memory ports, so the schema, the migration and the screens have been
typechecked and built but not yet exercised on hardware. That is the outstanding
item for this phase — the same boundary Phase 3 closed on the iPad.

Six things settled while building it:

1. **Closed-class parts of speech are never taught.** This answers Phase 1's
   note 2, which forbade inventing a rule silently. Measured on chapter 0 of
   `las-noches-mejicanas`, §5 unmodified makes 16 of the first 18 cards function
   words — `el`, `de`, `él`, `a`, `y`, `en`, `uno`, `que` — because `zipf >= 3.5`
   catches every one and `bookCount` sorts them to the top. Excluded: `ADP AUX
   CCONJ DET NUM PART PRON PUNCT SCONJ SYM X`. `INTJ` is deliberately *not*
   excluded — `¡órale!` is the point. They are still glossed.
2. **`LemmaKey` is book-scoped; `LemmaId` is the bare lemma string and is
   global.** Cards and known-marks are filed under the latter. `classify.py`
   already tests `entry.lemma in known_lemmas` and the Phase 5 seed is a flat
   array of lemma strings, so the app had to agree. `CardRepository` has no
   `bookId` in it anywhere — that absence is the enforcement, not a convention —
   and `deleteBook` deliberately leaves cards alone.
3. **The app never reads `Chapter.teachSet`.** It was computed against a stale
   known-set. Sessions recompute from the chapter's counts against live state;
   a test pins that the two disagree, 18 against the fixture's baked 25.
4. **A lemma is taught where it occurs, not where it debuts.** This diverges
   from `classify.py`'s `firstChapter` on purpose: the pipeline has no card
   store to consult and we do. Opening chapter 3 cold therefore teaches the
   chapter-0 vocabulary it reuses instead of only underlining it.
5. **Having a card and being known are different tests**, and collapsing them
   breaks one thing or the other. A word studied this morning must not be taught
   again (so: `carded`) and must not count towards coverage (so: not `known`).
6. **`SessionRepository.commit` takes the reducer's effects and writes them with
   the session in one transaction.** Split into two calls, iOS suspends the tab
   between them and the resumed session re-grades a card FSRS has already seen.

**Coverage understates readability until Phase 5, by design.** Learning every
word the fixture's chapter 1 will ever teach reaches 20 of its 35 word tokens —
a ceiling of 57%. The missing 15 are `el`×7, `su`×2, `de`, `y`, `por`, `entre`,
`desde`, which are never taught and so never become known. The 0.90 warning will
therefore fire on every book until SPEC §8's Anki seed marks the function words
known in one pass. The warning is premature, not the arithmetic — **do not "fix"
this by teaching `el`.** There is a test pinning the ceiling.

**Windowing is still not built and still not needed.** Nothing in Phase 4 adds a
span per token.

**Next: Phase 5 — Anki seed + review screen.**
Import `known.json`, add cross-book daily review. Success: the app stops
teaching you words you already know. Phase 5 is also what makes the coverage
figure honest, per the note above.

`Los de abajo` makes the case concrete and urgent. Unseeded, its first chapter
asks for **263 cards across 15 sessions** before an 820-word chapter, and the
book totals 2,700 cards. The curve collapses — the last chapters want one
session each — but the entry cost is the problem, and the seed is the fix.
Note the consumer already exists: `build_bundle.py --known` reads `known.json`
today. What is missing is `seed_known.py` to produce one, and the app-side
import. Two of the three pieces of Phase 5 are foundations Phase 4 already laid
(`KnownLemmaRepository`, `CardRepository`).

**One inconsistency to decide on first.** `classify.py` has no closed-class
rule, so the pipeline's baked `teachSet` and its report still teach `el`, `de`,
`y` — the report's TOP 20 is entirely function words. The app ignores the baked
set and recomputes (2,700 rather than 2,876), so nothing is broken, but the
report is a diagnostic you read to judge a book and it currently describes rules
the app does not follow. Porting the rule into `classify.py` would change the
bundle contract; leaving it means the report stays misleading. Not decided.

---

**Phase 3 — Reader shell. Complete.** Verified on the iPad: installed from the
home screen, bundle imported from Files, chapter read, words glossed on tap,
position restored after a kill, and the whole thing working in airplane mode.
That last one is the SPEC §12 success condition.

`/app` is a React + TypeScript + Vite PWA. It imports a bundle, lists chapters,
renders one, and glosses a word on tap. It makes no network call at runtime.
`npm test && npm run build` in `/app`; see `app/README.md`.

Live at **https://stoneyboney.github.io/molcajete/**. Pushing to `main` runs the
tests, builds `app/` and publishes to GitHub Pages — **the deploy step is
`git push`**, and a red test does not publish. `base` in `vite.config.ts` is
`/molcajete/` and the manifest's `start_url` and `scope` must agree with it;
renaming the repo means changing all three.

Two notes on the remote, both cost an hour to work out once. There is no SSH key
on this machine, so `origin` is HTTPS and authenticates from a token in the
macOS keychain. And GitHub's legacy `pages build and deployment` workflow runs
alongside `Deploy` and fails every time; it is cosmetic — `Deploy` is what
publishes — and setting Pages → Source explicitly to GitHub Actions silences it.

Five things settled while building it:

1. **A book is stored shredded, not as one document.** One row per chapter, one
   per lexicon entry, the book id in every compound key. `las-noches-mejicanas`
   is 11 MB; opening a chapter reads ~2.8 MB rather than deserialising all of
   it. The port hands out chapters and lexicon slices and deliberately has no
   `getBundle` — reintroducing one would undo this in a single line.
2. **Runs, not tokens.** Consecutive untappable tokens — whitespace,
   punctuation, and proper nouns, which carry no lexicon key because §5 skips
   them — merge into one text run in `domain/view/readerView.ts`. Measured on a
   real chapter: 27,180 elements plus 27,881 text nodes against 59,830 tokens.
   Add anything that needs a span per token and this is what it costs.
3. **The chapter loader reads its whole lexicon slice up front**, so the gloss
   sheet and the reveal toggle are synchronous. That is what keeps loading
   states out of the middle of a paragraph and lets the components stay dumb.
4. **Reveal-all is CSS, not state.** The ruby annotation is in the DOM whenever
   a glossOnly word has a German gloss, and one attribute on the article
   reveals it. Making it a React prop would re-render a thousand paragraphs on
   a toggle press.
5. **German copy lives in `src/ui/format.ts`, not in the view models.** The
   domain layer stays language-neutral so the Swift port does not inherit
   German strings.

**Windowing is not built, and the iPad says it is not needed.** The
1,136-paragraph chapter of `las-noches-mejicanas` was scrolled on the device and
felt fine, so the four measures above are sufficient at real scale. Windowing
would fight text selection and scroll restoration for no gain — do not add it
without a device measurement that says the four measures stopped being enough.

`CardRepository` and `KnownLemmaRepository` are also not built. Rule 4 names
them; they arrive in Phase 4 with their stores and their first caller, rather
than as empty interfaces guessing at what FSRS needs.

**`Los de abajo` is built.** `bundles/azuela-los-de-abajo.molcajete.json`, 3.9 MB,
42 chapters, 34,442 word tokens, 5,267 lexicon entries. Gitignored like every
bundle but the fixture — it is a copyrighted edition's text.

```bash
uv run build_bundle.py "sources/Los de abajo.epub" \
    --include-documents 'PrimeraParte*' 'SegundaParte*' 'TerceraParte*' \
    --split-on-heading --book-id azuela-los-de-abajo --title "Los de abajo" \
    --gloss-provider ollama          # 398 minutes, free
```

The edition is Marta Portal's, and three things in the pipeline exist because of
it. All are in `pipeline/README.md` under **Critical editions**:

1. **`--include-documents` / `--exclude-documents`.** Nine documents of
   apparatus — notes, analysis, biography, bibliography — sit in the same spine
   as the three of novel, ~200 KB against ~244 KB. Unfiltered they become
   chapters called *Bibliografía* and their words inflate the `bookCount` that
   decides what is taught.
2. **`<sup>` is not prose.** Footnote markers extract as `federales[54]`; 101
   paragraphs of Part I alone carry one.
3. **Chapter titles come from the TOC fragment.** A packed part's headings are
   bare numerals and the numbering restarts, so three chapters were called `I`
   until `_toc_titles` learned to key on `file#fragment`.

**A glossing pass now survives being interrupted.** It used to write to the
cache once, at the end; the first run here was killed at 2,067 of 4,811 and left
nothing. Glosses are written as each chunk lands, and since the cache is read
before the provider is called, a re-run asks only for what is missing. Keep the
write inside the `on_written` callback.

**Do not read a rate off the progress counter in the log.** It counts chunks
completed in memory. What has been kept is `select count(*) from glosses where
provider='ollama'`. Measured properly: **0.19 lemmas/sec**, against 0.25 on
`las-noches`. Both gemma3:12b on the M4 Pro; "about 0.2" is the number to plan
with.

**Phase 2 — Glosses. SPEC §12's target is met. One open question left.**

`95.3%` of teach-set lemmas have a German gloss (2,741 of 2,876), against §12's
`>95%`. On the chapter the app would actually teach first, 261 of 263 cards
carry one.

**Open question 2 is answered: it was the register, not the model.**

| | las-noches (1870s, French author) | Los de abajo (1915, Mexican) |
|---|---|---|
| Mexicanisms | **0** in 200 book lemmas | **116** in the lexicon |
| — of those, on teach-set lemmas | — | 46 |
| — earning a card they would not otherwise get | — | 17 |
| Rejected as not Spanish | 29 of 201 (14%) | 303 of 5,267 (5.8%) |

`güero`, `compadre`, `nomás`, `platicar`, `ranchería`, `zacate`, `chamaco`,
`apaste`, `tovía`, `pos`, `pa`. Given genuinely Mexican prose the model flags
regionalisms readily, so the zero on Payno was a correct reading of archaic
literary Spanish rather than a failure. Nothing about the prompt needed changing.

**Phase 2 — Glosses. The fallback runs. Not declared complete; see the open
question below.**

The Wiktionary half runs and is cached. The model half was written against the
Claude Batches API and could not be run — no credentials — so a local provider
was added to unblock it. That path has now been exercised end to end against
`gemma3:12b`, 201 lemmas of `Las noches mejicanas`, in 17 minutes for nothing.

Four things settled while doing that:

1. **The gloss fallback is behind a port.** `glossing/provider.py` defines
   `GlossProvider`; `claude.py` and `ollama.py` implement it; `--gloss-provider`
   selects one. `pipeline.gloss_lexicon` imports neither. Adding a third is a
   module and a line in `build_provider`. Claude remains the default per SPEC
   §11.2; `--gloss-provider ollama` needs no key and no network.
2. **`--de-wiktionary context-only` is the default.** German Wiktionary glosses
   `lunes` as "der erste Wochentag" — short enough to pass a length filter, and
   a riddle on a card. Fitting a card and teaching the word are different tests,
   and only the model has the book's sentence. `verbatim` still available.
3. **The cache is keyed by provider and model, but the Wiktionary rows are
   not.** Those rows record what the dictionaries said and every provider reads
   them. Scoping them per provider would undo the warm-rebuild fix from 6ff7dce
   — 3.1 GB of dumps re-streamed on the first `--gloss-provider ollama` build.
   There is a test pinning this; do not "tidy" it.
4. **A local model is slow, not expensive.** 0.25 lemmas/second on an M4 Pro at
   `--gloss-concurrency 2`, so a nine-thousand-lemma book is about ten hours.
   More concurrency is *slower*, measured. Plan around it rather than tuning it.

What the trial measured, for comparison when Claude credentials appear:

| | gemma3:12b |
|---|---|
| German gloss on lemmas it accepted as Spanish | 171/171 |
| Rejected as not Spanish | 29 of 201 |
| Needed a stricter retry | 2 · failed after retry 1 |
| Mexicanism recall, gold set asked directly | 21/26 |
| Mexicanisms found in 200 book lemmas | 0 |

**One open question. It does not block Phase 3 or 4; it blocks calling Phase 2
done.**

**It still invents glosses for words that do not exist, and at full scale it is
worse than the sample suggested.** Of 569 zipf-0.00 lemmas in `Los de abajo`,
**435 (76%) received a confident German gloss** — against 28 of 53 (53%) in the
`las-noches` sample. Nothing downstream can detect one, and the prompt forbids
it explicitly.

The complication this book adds is that **zipf 0.00 is a much weaker signal here
than it was on Payno.** Azuela transcribes rural speech, so a lemma wordfreq has
never seen is often exactly the vocabulary worth teaching. Sorting the sample by
hand:

- *Right, and worth having*: `abotagado` "geschwollen", `acalenturado`
  "fieberhaft", `airoplano` "das Flugzeug", `aguardentós`, `achinar`
- *Lemmatizer artifacts given confident wrong German*: `afiladísima` — a
  superlative adjective tagged NOUN and glossed "das Messer, die Klinge";
  `acabólo` — `acabó` + clitic, glossed "erst"; `chapet`, `aguilita`
- Multi-word garbage is handled correctly: 10 of them, and only 1 was glossed

So the failure is real but no longer separable from success by any rule we have
— a length filter or a zipf floor would throw away `zacate` and `chamaco` along
with `afuerar`. **Claude's rejection rate on the same stratum is still
unmeasured**, which is still the way to tell a local-model weakness from a
prompt weakness. Run `gloss_trial.py --provider claude` when credentials exist.

**Phase 1 — Prep pipeline skeleton. Complete.**

`pipeline/build_bundle.py` turns a DRM-free Spanish EPUB into a validated
`schemaVersion: 1` bundle plus a plain-text report. Verified end to end on a
115,765-token Spanish novel in under nine seconds. `uv sync && uv run pytest`
in `/pipeline`.

Three things carried forward:

1. **`Los de abajo` is not on Project Gutenberg — but it is now in
   `pipeline/sources/` and built.** SPEC §13.4 is still wrong and someone will
   follow it: Gutenberg has only the 1929 English translation, and the Spanish
   original is absent from Gutenberg, Spanish Wikisource and textos.info while
   the Internet Archive copies are DRM-locked scans of in-copyright editions.
   A DRM-free Marta Portal edition has since turned up; see the Phase 2 section
   above for the invocation, which needs the document filter.
2. **The §5 `zipf >= 3.5` rule teaches function words.** Unseeded, the top of
   every teach set is `el`, `de`, `y`, `que`. SPEC §8 anticipates this and
   answers it with Anki seeding in Phase 5 — but if Phase 4 arrives first, the
   teaching session will be unusable without either the seed or a rule excluding
   closed-class parts of speech. Not decided; do not invent a rule silently.
3. **`es_core_news_sm` fabricates roughly 10% of its lemmas.** Words wordfreq has
   never seen — `acaeceír`, `abrasadorar`, and multi-word output like
   `abalanzar él` for reflexives. Phase 2 should not pay to gloss those. The
   report's zipf-0.00 diagnostic is the measurement; compare against
   `es_core_news_md` before committing to a glossing pass.

Read `app/README.md` first — it holds the layout, the measurements and the rules
that are easiest to break by accident.

Update this section when a phase completes.
