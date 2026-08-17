/**
 * Storage port for lemmas marked known by hand.
 *
 * This is the "Ich kenne das" store, and in Phase 5 it is also where the Anki
 * seed lands — SPEC §8's `known.json` is a flat array of lemma strings, which
 * is exactly this store's key. `add` merges rather than replaces for the same
 * reason: §8 says the seed is re-runnable at any time.
 *
 * Note what is *not* here. A lemma is known if it was marked by hand **or** if
 * its card has matured past SPEC §7's threshold. This store holds only the
 * first half; `knownLemmas.ts` unions the two, so that neither this interface
 * nor `CardRepository` has to know the other exists.
 */

import type { LemmaId } from '../lemma'

export interface KnownLemmaRepository {
  listAll(): Promise<Set<LemmaId>>

  /** Merges. Marking a lemma known twice is not an error. */
  add(lemmaIds: readonly LemmaId[]): Promise<void>
}
