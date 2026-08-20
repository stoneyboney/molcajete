import type { LemmaId } from '../domain/lemma'
import type { CardRepository } from '../domain/ports/CardRepository'
import type { SrsCard } from '../domain/srs/scheduler'
import { db, type MolcajeteDatabase } from './db'

/**
 * FSRS cards in IndexedDB, keyed by lemma and by nothing else.
 *
 * The stored `card` is the whole `SrsCard`, FSRS object included. Its `due` and
 * `last_review` are `Date`s and IndexedDB's structured clone keeps them as
 * `Date`s, so nothing has to be revived on the way out.
 */
export class DexieCardRepository implements CardRepository {
  constructor(private readonly database: MolcajeteDatabase = db) {}

  async get(lemmaId: LemmaId): Promise<SrsCard | undefined> {
    return (await this.database.cards.get(lemmaId))?.card
  }

  async getMany(lemmaIds: readonly LemmaId[]): Promise<Map<LemmaId, SrsCard>> {
    const found = new Map<LemmaId, SrsCard>()
    if (lemmaIds.length === 0) return found

    const rows = await this.database.cards.bulkGet([...lemmaIds])
    for (const row of rows) {
      if (row) found.set(row.lemmaId, row.card)
    }
    return found
  }

  async listCardedLemmas(): Promise<Set<LemmaId>> {
    // Primary keys only — the schedules are not wanted here and are by far the
    // larger half of the row.
    const keys = await this.database.cards.toCollection().primaryKeys()
    return new Set(keys)
  }

  async listDue(now: Date, limit?: number): Promise<SrsCard[]> {
    // Soonest first, so a capped review starts with what is most overdue.
    let query = this.database.cards
      .where('card.fsrs.due')
      .belowOrEqual(now)
      .limit(limit ?? Infinity)
    const rows = await query.sortBy('card.fsrs.due')
    return rows.map((row) => row.card)
  }

  async countDue(now: Date): Promise<number> {
    return this.database.cards.where('card.fsrs.due').belowOrEqual(now).count()
  }

  async listAll(): Promise<SrsCard[]> {
    const rows = await this.database.cards.toArray()
    return rows.map((row) => row.card)
  }

  async put(card: SrsCard): Promise<void> {
    await this.database.cards.put({ lemmaId: card.lemmaId, card })
  }
}
