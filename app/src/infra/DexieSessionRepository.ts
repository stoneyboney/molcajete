import type { SessionRepository } from '../domain/ports/SessionRepository'
import type { SessionEffect, TeachingSession } from '../domain/session/session'
import type { BookId } from '../domain/types'
import { db, type MolcajeteDatabase } from './db'

/**
 * The session store, and the one transaction that makes an interrupted session
 * safe to resume.
 *
 * `commit` writes the session, every card it graded and every lemma it marked
 * known in a single `rw` transaction. Split across three calls, iOS suspending
 * the tab between them leaves a card that was graded inside a session that does
 * not know it — and re-grading on resume gives FSRS two reviews for one answer.
 */
export class DexieSessionRepository implements SessionRepository {
  constructor(private readonly database: MolcajeteDatabase = db) {}

  async load(
    bookId: BookId,
    chapterIndex: number,
  ): Promise<TeachingSession | undefined> {
    const row = await this.database.sessions.get([bookId, chapterIndex])
    return row?.session
  }

  async commit(
    session: TeachingSession,
    effects: readonly SessionEffect[],
    markedAt: Date = session.updatedAt,
  ): Promise<void> {
    const { sessions, cards, knownLemmas } = this.database

    await this.database.transaction('rw', [sessions, cards, knownLemmas], async () => {
      for (const effect of effects) {
        if (effect.kind === 'saveCard') {
          await cards.put({ lemmaId: effect.card.lemmaId, card: effect.card })
        } else {
          // Written directly rather than through `KnownLemmaRepository.add`,
          // so it lands in the same atomic transaction as the card write —
          // see the file header. `source: 'manual'` because this is always
          // "Ich kenne das", never a seed import.
          await knownLemmas.put({ lemmaId: effect.lemmaId, markedAt, source: 'manual' })
        }
      }

      if (session.phase === 'complete') {
        // Nothing to resume, and the result is in the cards. Keeping finished
        // sessions would only give `load` something to filter.
        await sessions.delete([session.bookId, session.chapterIndex])
      } else {
        await sessions.put({
          bookId: session.bookId,
          chapterIndex: session.chapterIndex,
          session,
        })
      }
    })
  }

  async clear(bookId: BookId, chapterIndex: number): Promise<void> {
    await this.database.sessions.delete([bookId, chapterIndex])
  }

  async listAll(): Promise<TeachingSession[]> {
    const rows = await this.database.sessions.toArray()
    return rows.map((row) => row.session)
  }
}
