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

/**
 * Defined here, not in `src/infra/`: the port owns the vocabulary, and
 * `db.ts` imports this type rather than the reverse (CLAUDE.md rule 4 — no
 * domain file may depend on `src/infra/`, even for a type this small).
 */
export type KnownLemmaSource = 'seed' | 'manual'

export interface KnownLemmaRepository {
  listAll(): Promise<Set<LemmaId>>

  /**
   * Diagnostics only. `source` is `undefined` for rows written before that
   * field existed — a legacy bucket, not a guess.
   */
  listAllWithSource(): Promise<Map<LemmaId, KnownLemmaSource | undefined>>

  /**
   * Merges. Marking a lemma known twice is not an error. `source` applies to
   * the whole batch — both real call sites (a seed import, or a single
   * "Ich kenne das") only ever add from one source at a time.
   */
  add(lemmaIds: readonly LemmaId[], source: KnownLemmaSource): Promise<void>
}
