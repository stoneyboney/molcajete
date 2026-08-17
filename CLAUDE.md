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

**Phase 2 — Glosses. The fallback runs. Not declared complete; see the two open
questions below.**

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

**Two open questions. Neither blocks Phase 3; both block calling Phase 2 done.**

1. **It invents glosses for words that do not exist.** Of 53 zipf-0.00 lemmas
   in the sample it rejected 25 and glossed 28. Some of those 28 are real rare
   words (`acecinar`, `bambolear`, `bergante`); many are lemmatizer garbage
   — `cenir`, `correspondar`, `majadeer` — that received confident, plausible,
   invented German. It also glossed `soon` and `niente`, English and Italian
   leaking in from Gutenberg boilerplate. The prompt forbids this explicitly and
   nothing downstream can detect it. Unknown whether it is a local-model
   weakness or a prompt weakness: Claude's rejection rate on the same stratum is
   unmeasured. Run the same trial with `--provider claude` to find out.
2. **Zero mexicanisms across 200 book lemmas, against 21/26 on the same model
   minutes later.** The difference is the example sentence: given 1870s literary
   prose the model reads the register as archaic rather than Mexican. That may
   be correct for Payno and would be a serious failure on a modern Mexican
   novel. It cannot be told apart until the pipeline is pointed at one — which
   is a reason to keep looking for a DRM-free `Los de abajo`, or anything
   twentieth-century.

**Phase 1 — Prep pipeline skeleton. Complete.**

`pipeline/build_bundle.py` turns a DRM-free Spanish EPUB into a validated
`schemaVersion: 1` bundle plus a plain-text report. Verified end to end on a
115,765-token Spanish novel in under nine seconds. `uv sync && uv run pytest`
in `/pipeline`.

Three things carried forward:

1. **`Los de abajo` is not on Project Gutenberg.** SPEC §13.4 is wrong: Gutenberg
   has only the 1929 English translation. The Spanish original is absent from
   Gutenberg, Spanish Wikisource and textos.info, and the Internet Archive copies
   are DRM-locked scans of in-copyright modern editions. Pipeline development
   therefore used another Spanish EPUB. Drop a DRM-free `Los de abajo` into
   `pipeline/sources/` whenever one turns up; nothing in the pipeline is
   book-specific. See `pipeline/README.md`.
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

**Next: Phase 4 — Teaching loop.**
Teach-set selection, introduction phase, FSRS recall phase, chapter gating.
Success: you learn 18 words, then read the chapter and notice the difference.

Read `app/README.md` first — it holds the layout, the measurements and the two
rules that are easiest to break by accident.

Phase 4 is the first phase that touches the domain layer's real subject matter,
and two things already recorded here decide how it starts: the unseeded teach
set is full of function words (Phase 1, note 2 — unresolved, do not invent a
rule silently), and every chapter of the fixture already exceeds the 18-card
cap, so `splitChapterIfNeeded` is not optional.

Update this section when a phase completes.
