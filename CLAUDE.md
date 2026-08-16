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

**Next: Phase 2 — Glosses.**
Wiktionary extracts from kaikki.org, DE and EN, with a Claude batch fallback.
Success: >95% of teach-set lemmas have a German gloss.

Update this section when a phase completes.
