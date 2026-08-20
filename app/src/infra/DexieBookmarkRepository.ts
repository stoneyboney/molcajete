import type { Bookmark, BookmarkRepository } from '../domain/ports/BookmarkRepository'
import type { BookId } from '../domain/types'
import { db, type MolcajeteDatabase } from './db'

export class DexieBookmarkRepository implements BookmarkRepository {
  constructor(private readonly database: MolcajeteDatabase = db) {}

  async listAll(): Promise<Bookmark[]> {
    const rows = await this.database.bookmarks.orderBy(':id').reverse().toArray()
    return rows.map((row) => ({ ...row, id: row.id! }))
  }

  async add(entry: {
    bookId: BookId
    chapterIndex: number
    paragraphId: string
    text: string
    createdAt: Date
  }): Promise<void> {
    await this.database.bookmarks.add(entry)
  }

  async remove(id: number): Promise<void> {
    await this.database.bookmarks.delete(id)
  }
}
