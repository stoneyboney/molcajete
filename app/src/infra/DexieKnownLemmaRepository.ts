import type { LemmaId } from '../domain/lemma'
import type { KnownLemmaRepository } from '../domain/ports/KnownLemmaRepository'
import { db, type MolcajeteDatabase } from './db'

/**
 * The "Ich kenne das" store, and in Phase 5 the landing place for SPEC §8's
 * Anki seed. `add` is a `bulkPut`, so re-running the seed merges rather than
 * duplicating — which §8 requires.
 */
export class DexieKnownLemmaRepository implements KnownLemmaRepository {
  constructor(private readonly database: MolcajeteDatabase = db) {}

  async listAll(): Promise<Set<LemmaId>> {
    const keys = await this.database.knownLemmas.toCollection().primaryKeys()
    return new Set(keys)
  }

  async add(lemmaIds: readonly LemmaId[], markedAt: Date = new Date()): Promise<void> {
    if (lemmaIds.length === 0) return
    await this.database.knownLemmas.bulkPut(
      lemmaIds.map((lemmaId) => ({ lemmaId, markedAt })),
    )
  }
}
