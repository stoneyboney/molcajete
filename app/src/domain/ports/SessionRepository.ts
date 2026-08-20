/**
 * Storage port for a teaching session in progress.
 *
 * One open session per chapter, which is why the key is `[bookId, chapterIndex]`
 * and not a session id. There is no history to keep: a finished session's
 * result lives in the cards it created.
 *
 * ## Why `commit` takes the effects as well as the session
 *
 * The obvious shape would be `put(session)` next to `CardRepository.put(card)`,
 * with the screen calling both. That has a failure mode this app is guaranteed
 * to hit: the card write lands, iOS suspends the tab before the session write,
 * and the resumed session shows a card it already graded. Grade it again and
 * FSRS gets two reviews for one answer — a schedule that is wrong rather than
 * merely stale.
 *
 * So one call, one transaction, both writes or neither. The effects come
 * straight from the session reducer, which is also why they are described as
 * data rather than performed by it.
 */

import type { BookId } from '../types'
import type { SessionEffect, TeachingSession } from '../session/session'

export interface SessionRepository {
  load(bookId: BookId, chapterIndex: number): Promise<TeachingSession | undefined>

  /** Atomically: the session, plus every card and known lemma it produced. */
  commit(session: TeachingSession, effects: readonly SessionEffect[]): Promise<void>

  clear(bookId: BookId, chapterIndex: number): Promise<void>

  /** Every in-progress session, across every book. Diagnostics only. */
  listAll(): Promise<TeachingSession[]>
}
