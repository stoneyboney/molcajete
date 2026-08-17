/**
 * Two kinds of key, and the difference between them is the whole of this file.
 *
 * A **`LemmaKey`** (`"m0031"`) is book-scoped. It indexes one bundle's lexicon
 * and means nothing outside it: `m0031` is `madriguera` in one book and
 * `mirar` in the next. Chapters, glosses and teach sets all speak in these.
 *
 * A **`LemmaId`** is global. It is what a flashcard is filed under, what "I
 * already know this" records, and the reason a word learned in one book is
 * never taught again in another. It is the bare lemma string.
 *
 * Bare lemma, not lemma + part of speech, for three reasons:
 *
 * 1. `pipeline/molcajete_prep/classify.py` already tests `entry.lemma in
 *    known_lemmas`. The two implementations of §5 have to agree, and that one
 *    was written first.
 * 2. SPEC §8's `known.json` — the Phase 5 Anki seed — is a flat array of lemma
 *    strings. There is no part of speech to match against even if we wanted one.
 * 3. It is the answer that re-teaches least. The lexicon of
 *    `las-noches-mejicanas` holds `estar` twice, as `AUX` (bookCount 613) and
 *    as `VERB` (76), under two different keys. They are the same Spanish word
 *    and learning it once should settle both.
 */

import type { LexiconEntry } from './types'

/** Globally unique across every book. See the note above. */
export type LemmaId = string

/**
 * The pipeline already lowercases (`tok.lemma_.lower()`), so this is a
 * belt-and-braces normalisation rather than a transformation. It exists so that
 * a hand-written `known.json` or a future seed file cannot introduce a lemma
 * that fails to match the identical word arriving from a bundle.
 */
export function normalizeLemma(lemma: string): LemmaId {
  return lemma.trim().toLowerCase()
}

export function lemmaId(entry: LexiconEntry): LemmaId {
  return normalizeLemma(entry.lemma)
}
