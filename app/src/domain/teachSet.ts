/**
 * The SPEC §5 vocabulary selection rules, on device.
 *
 * This is the TypeScript twin of `pipeline/molcajete_prep/classify.py`, and the
 * third implementation will be Swift. Read that module's docstring alongside
 * this one — where the two deliberately differ it is written down below, and
 * where they agree they must keep agreeing.
 *
 * ## Why this runs on device at all
 *
 * Every bundle already carries a `teachSet` per chapter. It is a **hint for
 * display**, never the contents of a session. The pipeline computed it at prep
 * time against whatever known-set existed on the desktop that day; by the time
 * you open the chapter you have learned words it did not know about and marked
 * others with "Ich kenne das". Trusting it would re-teach words you know. So
 * the session recomputes from the chapter's own lemma counts against the live
 * known-set, and nothing in the app reads `Chapter.teachSet`.
 *
 * ## Three differences from the pipeline, all deliberate
 *
 * 1. **Closed-class parts of speech are never taught.** §5 as written makes 16
 *    of the first 18 cards of `las-noches-mejicanas` function words — `el`,
 *    `de`, `él`, `a`, `y`, `en`, `uno`, `que` — because `zipf >= 3.5` catches
 *    every one of them and `bookCount` sorts them to the top. A flashcard does
 *    not teach `de`; that is grammar, and it arrives from reading. They are
 *    still glossed, so the reader is unchanged.
 *
 * 2. **A lemma is taught where it occurs, not where it debuts.** The pipeline
 *    files each card under the lemma's `firstChapter`, which is the only thing
 *    it can do with no card store to consult. We have one. "Taught once" then
 *    falls out of `carded` on its own, and opening chapter 3 without having
 *    read chapter 0 teaches the chapter-0 vocabulary that chapter 3 reuses
 *    instead of leaving it merely underlined.
 *
 * 3. **The teach set comes back uncapped.** §5 Step 3's cap of 18 belongs to
 *    `segments.ts`, which is the only module that knows the number. Returning a
 *    capped list here would mean two places could disagree about it.
 *
 * ## Having a card and being known are different tests
 *
 * `known` is SPEC §7's definition — a matured card, or "Ich kenne das". `carded`
 * is merely "a card exists". A word first seen this morning is in `carded` but
 * not `known`: it must not be taught again, and it must not count towards
 * coverage either. Collapsing the two would do one or the other wrong.
 */

import { lemmaId, type LemmaId } from './lemma'
import type { LemmaKey, LexiconEntry } from './types'

/**
 * Parts of speech that never earn a card.
 *
 * `INTJ` is absent on purpose. An interjection is exactly the vocabulary this
 * app exists for — `¡órale!` is worth a card in a way that `de` is not.
 */
export const CLOSED_CLASS_POS: ReadonlySet<string> = new Set([
  'ADP',
  'AUX',
  'CCONJ',
  'DET',
  'NUM',
  'PART',
  'PRON',
  'PUNCT',
  'SCONJ',
  'SYM',
  'X',
])

export interface TeachSetOptions {
  /** §5: `bookCount >= 3` earns a card on its own. */
  minBookCount: number
  /** §5: `zipf >= 3.5`, roughly the top 5000 words. */
  zipfThreshold: number
  /** §5: a mexicanism needs only `bookCount >= 2`. */
  mexicanismMinBookCount: number
  /** See `CLOSED_CLASS_POS`. Injected so a test can vary it. */
  excludedPos: ReadonlySet<string>
  /**
   * Lemmas that already have an FSRS card, however immature.
   *
   * Not a tuning knob like the fields above — this is live state the caller
   * reads from `CardRepository`. It sits in the options object to keep the
   * four-argument shape SPEC Appendix B specifies.
   */
  carded: ReadonlySet<LemmaId>
}

export const DEFAULT_TEACH_SET_OPTIONS: TeachSetOptions = {
  minBookCount: 3,
  zipfThreshold: 3.5,
  mexicanismMinBookCount: 2,
  excludedPos: CLOSED_CLASS_POS,
  carded: new Set(),
}

export interface TeachSetSelection {
  /**
   * Uncapped, ordered by `bookCount` descending so that an abandoned session
   * still taught the most useful words (§5 Step 3). Ties break on the key so
   * that two runs over the same data produce the same list.
   */
  teach: LemmaKey[]
  /** Everything unknown that did not earn a card. Dotted underline, no session. */
  glossOnly: LemmaKey[]
}

/** Whether §5's three teach rules fire for this entry, ignoring what you know. */
export function isTeachable(
  entry: LexiconEntry,
  opts: TeachSetOptions,
): boolean {
  // PROPN is tested before the teach rules, not after. Read §5's table
  // top-down and `Demetrio` — hundreds of occurrences — earns a card.
  // CLAUDE.md: "PROPN is skipped entirely, no card, no gloss."
  if (entry.pos === 'PROPN') return false
  if (opts.excludedPos.has(entry.pos)) return false

  if (entry.bookCount >= opts.minBookCount) return true
  if (entry.zipf >= opts.zipfThreshold) return true
  if (entry.mexicanism && entry.bookCount >= opts.mexicanismMinBookCount) {
    return true
  }
  return false
}

export function selectTeachSet(
  chapterCounts: ReadonlyMap<LemmaKey, number>,
  lexicon: ReadonlyMap<LemmaKey, LexiconEntry>,
  known: ReadonlySet<LemmaId>,
  opts: TeachSetOptions = DEFAULT_TEACH_SET_OPTIONS,
): TeachSetSelection {
  const teach: LemmaKey[] = []
  const glossOnly: LemmaKey[] = []

  for (const key of chapterCounts.keys()) {
    const entry = lexicon.get(key)
    // A key with no entry is a partial import. The reader already degrades to
    // showing no gloss rather than refusing the chapter; do the same here.
    if (!entry) continue
    if (entry.pos === 'PROPN') continue

    const id = lemmaId(entry)
    if (known.has(id)) continue

    if (!isTeachable(entry, opts)) {
      glossOnly.push(key)
      continue
    }

    // Teachable, but you are already learning it. Not a card, and not an
    // underline either — you have seen it introduced.
    if (opts.carded.has(id)) continue

    teach.push(key)
  }

  teach.sort((a, b) => {
    const byCount =
      (lexicon.get(b)?.bookCount ?? 0) - (lexicon.get(a)?.bookCount ?? 0)
    return byCount !== 0 ? byCount : a < b ? -1 : a > b ? 1 : 0
  })
  glossOnly.sort()

  return { teach, glossOnly }
}

/**
 * The `LemmaId`s a set of lexicon keys resolves to.
 *
 * The one place book-scoped keys cross over into global identity, so the
 * "learned in book A, never taught in book B" property has a single home.
 */
export function toLemmaIds(
  keys: readonly LemmaKey[],
  lexicon: ReadonlyMap<LemmaKey, LexiconEntry>,
): LemmaId[] {
  const ids: LemmaId[] = []
  for (const key of keys) {
    const entry = lexicon.get(key)
    if (entry) ids.push(lemmaId(entry))
  }
  return ids
}
