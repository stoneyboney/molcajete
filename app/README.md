# molcajete

The device half of Molcajete. A React PWA that imports a `.molcajete.json`
bundle and lets you read it offline.

It makes **no network calls at runtime**. After one visit and one import it
works in airplane mode — verified on an iPad, launched from the home screen.

Live at https://stoneyboney.github.io/molcajete/

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

```bash
git push
```

`.github/workflows/deploy.yml` runs the tests, builds `app/`, and publishes to
https://stoneyboney.github.io/molcajete/. A red test does not get published.

`origin` is HTTPS and authenticates from a token in the macOS keychain — there
is no SSH key on the development machine.

GitHub's legacy `pages build and deployment` workflow also runs on every push
and fails every time. It is cosmetic: `Deploy` is what publishes. Setting
Settings → Pages → Source explicitly to **GitHub Actions** stops it running.

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
  lemma.ts       LemmaKey (book-scoped) vs LemmaId (global). Read this first.
  teachSet.ts    The SPEC §5 rules — the twin of pipeline/classify.py
  coverage.ts    Lemma counts and the §5 Step 4 figure
  segments.ts    splitChapterIfNeeded. The only module that knows 18.
  knownLemmas.ts §7's two routes to "known", unioned
  bundle/        parseBundle — the validator
  session/       The teaching session as a pure reducer
  srs/           The ts-fsrs wrapper. The only file that imports it.
  ports/         Repository interfaces, and Clock
  view/          View models: the screens receive these and render them
src/infra/       Dexie. The only place that knows IndexedDB exists.
src/ui/          Components. They render view models and compute nothing.
src/app/         Wiring: router, repository injection, import, loadSession
tests/domain/    Vitest, node environment
tests/           teachingLoop.test.ts — the flow, over in-memory ports
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
restoration, and the four measures above are enough — the 1,136-paragraph
chapter was scrolled on the iPad and felt fine. Do not add windowing without a
device measurement saying that stopped being true.

## The teaching loop

Two rules that are easy to break by accident, on top of the two above.

**Nothing reads `Chapter.teachSet`.** It was computed at prep time against a
known-set that is now stale, and it is a display hint at most. Sessions
recompute from the chapter's own lemma counts against what you know right now.
There is a test asserting the two disagree — 18 recomputed against 25 baked on
the fixture's first chapter.

**Cards are keyed by lemma, globally.** `LemmaKey` (`m0031`) is book-scoped and
means nothing outside its bundle; `LemmaId` is the bare lemma string and is what
a card is filed under. `CardRepository` has no `bookId` in it anywhere, which is
the enforcement rather than a convention — and `deleteBook` leaves cards alone,
because removing a book does not unlearn its vocabulary.

`splitChapterIfNeeded` cuts segments in **reading order** and sorts the cards
**within** a segment by `bookCount`. Both orderings are in SPEC §5 Step 3 and
they are not in conflict — they apply at different levels. Segments fill to a
paragraph boundary, so the fixture's chapter 2 lands 15 + 7 rather than 18 + 4.

Segment numbers are never persisted. Finishing a session gives its words cards,
which removes them from the next selection, so the next session is always
segment 0 of what is left.

## Coverage understates readability without a seed

Learning every word the fixture's chapter 1 will ever teach reaches 20 of its 35
word tokens — a ceiling of **57%**. The missing 15 are `el`×7, `su`×2, `de`,
`y`, `por`, `entre`, `desde`: closed-class words the teach set deliberately
never contains, so they never become known, so they never count as covered.

This is not a bug and the fix is not to teach `el`. It is to import a
`known.json`, which marks the function words known in one pass — that is what
the seed is *for*, beyond saving you the cards. There is a test pinning the
ceiling and the explanation.

Unseeded, `Los de abajo` shows the same shape at scale: 263 cards for its first
chapter, 4.3% coverage across the book. With a top-5k vocabulary marked known
that becomes 62 cards and 83%.

## The seed and the review screen

**One import button, two kinds of file.** It cannot narrow its `accept` past
`.json` — iOS matches that against the system's idea of a file type and a double
extension is not one — so `importFile.ts` dispatches on *shape*: an object is a
bundle, an array is a `known.json`. Nothing depends on the filename, which is
what makes AirDrop renaming harmless.

**A card carries its own face.** `SrsCard.face` holds the gloss, the example and
the region note, copied on at creation. The review screen is cross-book and
`deleteBook` deliberately leaves cards alone, so a lemma due today may come from
a book that is no longer imported — resolving the gloss back through a bundle
would undo the whole point of cards being global. Cards made before Phase 5 have
no face and fall back to showing the lemma alone.

**A review keeps no session state, on purpose.** A teaching session is persisted
after every answer because losing it means re-teaching. A review has nothing
worth keeping: every answer writes the card, and resuming is just asking what is
still due. A card graded `Gut` is not due; one graded `Nochmal` is.

Worth knowing when reading the tests: first exposures are still inside FSRS's
learning steps, so the intervals are minutes rather than days — `Nochmal` 1m,
`Schwer` 6m, `Gut` 10m, `Leicht` 8 days. A card answered `Gut` this morning is
genuinely due again this morning. That is the learning phase working.

## What is not here yet

The `Add card` button in the gloss sheet (§6.4) is Phase 6, along with reading
statistics and the Anki TSV export.

The Dexie implementations are exercised by the type checker and by hand, not by
the test suite: `tests/teachingLoop.test.ts` runs the flow over in-memory ports
because covering the real ones in node would mean adding `fake-indexeddb`, and
dependencies get asked about first.
