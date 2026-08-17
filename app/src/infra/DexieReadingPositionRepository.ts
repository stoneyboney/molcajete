import type {
  ReadingPosition,
  ReadingPositionRepository,
} from '../domain/ports/ReadingPositionRepository'
import type { BookId } from '../domain/types'
import { db, type MolcajeteDatabase } from './db'

export class DexieReadingPositionRepository
  implements ReadingPositionRepository
{
  constructor(private readonly database: MolcajeteDatabase = db) {}

  async get(
    bookId: BookId,
    chapterIndex: number,
  ): Promise<ReadingPosition | undefined> {
    return this.database.positions.get([bookId, chapterIndex])
  }

  async listForBook(bookId: BookId): Promise<Map<number, ReadingPosition>> {
    const rows = await this.database.positions.where({ bookId }).toArray()
    return new Map(rows.map((row) => [row.chapterIndex, row]))
  }

  async put(position: ReadingPosition): Promise<void> {
    await this.database.positions.put(position)
  }
}
