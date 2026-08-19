/**
 * Storage port for FSRS cards.
 *
 * **Book-agnostic on purpose.** Cards are keyed by `LemmaId` — the bare lemma
 * string — and there is no `bookId` anywhere in this interface. A word learned
 * in one book must never be taught again in another, and the cheapest way to
 * guarantee that is to make it impossible to express: there is no method here
 * that could return "this book's cards".
 *
 * That is also why `BookRepository.deleteBook` must not touch this store.
 * Deleting a book removes its text; it does not unlearn its vocabulary.
 *
 * The stored card holds the entire FSRS object, never a subset (CLAUDE.md:
 * partial state cannot be rescheduled).
 */

import type { LemmaId } from '../lemma'
import type { SrsCard } from '../srs/scheduler'

export interface CardRepository {
  get(lemmaId: LemmaId): Promise<SrsCard | undefined>

  /** The cards among `lemmaIds` that exist. Missing ones are simply absent. */
  getMany(lemmaIds: readonly LemmaId[]): Promise<Map<LemmaId, SrsCard>>

  /**
   * Every lemma that has a card, mature or not.
   *
   * This is `teachSet`'s `carded` set. It is deliberately just the ids: the
   * chapter list asks "is this being learned already?" thousands of times and
   * has no use for the schedules.
   */
  listCardedLemmas(): Promise<Set<LemmaId>>

  /**
   * Cards due at or before `now`, soonest first. SPEC §6.5's whole selection.
   *
   * Cross-book by construction, like everything else here. `limit` exists
   * because a neglected week can leave hundreds due and a screen that offers
   * all of them at once is a screen you close.
   */
  listDue(now: Date, limit?: number): Promise<SrsCard[]>

  /** How many are due, without reading their schedules. For the library chip. */
  countDue(now: Date): Promise<number>

  put(card: SrsCard): Promise<void>
}
