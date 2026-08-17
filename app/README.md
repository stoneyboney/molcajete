# molcajete

The device half of Molcajete. A React PWA that imports a `.molcajete.json`
bundle and lets you read it offline.

It makes **no network calls at runtime**. After one visit and one import it
works in airplane mode, and there is nothing in it that would need a server.

## Running it

```bash
npm install
npm run dev        # http://localhost:5173/molcajete/
npm test           # the domain suite
npm run build      # typecheck, then bundle
npm run preview    # serve the built output
```

The service worker is disabled in `dev`. To exercise it, `npm run build &&
npm run preview`.

## Deploying

One-time, in the browser: create the GitHub repo, then
**Settings → Pages → Source → GitHub Actions**.

After that:

```bash
git push
```

`.github/workflows/deploy.yml` runs the tests, builds `app/`, and publishes to
`https://<user>.github.io/molcajete/`. A red test does not get published.

`base` in `vite.config.ts` is `/molcajete/` and the manifest's `start_url` and
`scope` have to agree with it. Renaming the repo means changing all three.

## Installing on the iPad

Open the Pages URL in Safari → Share → **Add to Home Screen**. Launch it from
the icon rather than from Safari: only then does it run standalone, and only
then do the safe-area insets and the status-bar handling look right.

To get a bundle onto the device, AirDrop it. It lands in Files; the import
button picks it up from there.

## Layout

```
src/domain/      Pure. No React, no DOM, no Dexie. Heavily tested.
  types.ts       The bundle format as the reader decodes it
  bundle/        parseBundle — the validator
  ports/         Repository interfaces
  view/          View models: the screens receive these and render them
src/infra/       Dexie. The only place that knows IndexedDB exists.
src/ui/          Components. They render view models and compute nothing.
src/app/         Wiring: router, repository injection, import
tests/domain/    Vitest, node environment
```

The rules behind that split are in `../CLAUDE.md`. Two of them are worth
repeating because they are easy to break by accident:

- **Nothing outside `src/infra/` imports Dexie.** Screens take repositories
  from `useRepositories()`, typed as the ports.
- **Components compute nothing.** If a screen needs a derived value, it is
  built in `src/domain/view/` and passed down. `tests/` runs in a node
  environment partly to keep the domain layer honest about this: anything
  reaching for `window` fails there.

## The bundle contract

`src/domain/types.ts` and `src/domain/bundle/parseBundle.ts` are the
TypeScript half of `pipeline/molcajete_prep/schema.py`. The two are maintained
as if by different people, because eventually one of them will be Swift.

The reader re-validates every bundle even though the pipeline already did.
A file arrives by AirDrop from a machine running some version of the pipeline,
and a half-valid import is a book that breaks in the middle of a chapter on the
train. `schemaVersion` is checked first, and a mismatch is its own error type so
the screen can name the version instead of guessing.

Tests read `../bundles/anonimo-los-del-cerro.molcajete.json` directly rather
than keeping a copy, so a change to what the pipeline emits shows up here.

## Performance notes

The numbers that shaped the reader, measured on
`las-noches-mejicanas` — 11 MB, 5 chapters, largest chapter 68,979 tokens in
1,046 paragraphs, lexicon of 9,024 entries:

- **Books are stored shredded.** One row per chapter, one per lexicon entry.
  Opening a chapter reads ~2.8 MB, not 11 MB.
- **Runs, not tokens.** Untappable tokens merge into text runs, so that chapter
  renders 31,654 elements and 32,320 text nodes instead of 68,979 elements.
- **One delegated tap handler** on the article, not one per word.
- **`content-visibility: auto`** per paragraph, with `contain-intrinsic-size`
  from a height estimate in the view model.

Windowing is deliberately not used. It fights text selection and scroll
restoration, and the four measures above were expected to be enough; if a real
iPad disagrees, that is the next thing to reach for.

## What is not here yet

Phase 3 is the reader shell. Teach sets, FSRS, chapter gating, the review
screen, the `Add card` button in the gloss sheet, coverage display and Anki
seeding are Phases 4–6. Chapters carry their `teachSet` in storage already;
nothing reads it.
