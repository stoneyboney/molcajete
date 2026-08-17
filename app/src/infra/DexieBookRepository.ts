import type { Table } from 'dexie'
import type {
  BookRepository,
  BookSummary,
  ChapterSummary,
} from '../domain/ports/BookRepository'
import type {
  BookId,
  Bundle,
  Chapter,
  LemmaKey,
  LexiconEntry,
} from '../domain/types'
import { db, type ChapterRow, type LexiconRow, type MolcajeteDatabase } from './db'

/**
 * Written in chunks rather than one bulkPut. A 9,000-entry lexicon in a single
 * call builds one enormous argument array and holds every row live at once;
 * chunks let each batch be collected while the transaction stays open.
 */
const WRITE_CHUNK = 500

function toChapter(row: ChapterRow): Chapter {
  return {
    index: row.index,
    title: row.title,
    tokenCount: row.tokenCount,
    paragraphs: row.paragraphs,
    teachSet: row.teachSet,
    glossOnly: row.glossOnly,
  }
}

export class DexieBookRepository implements BookRepository {
  constructor(private readonly database: MolcajeteDatabase = db) {}

  async listBooks(): Promise<BookSummary[]> {
    const rows = await this.database.books.toArray()
    rows.sort((a, b) => b.importedAt.getTime() - a.importedAt.getTime())
    return rows
  }

  async getBook(id: BookId): Promise<BookSummary | undefined> {
    return this.database.books.get(id)
  }

  async listChapters(id: BookId): Promise<ChapterSummary[]> {
    // `paragraphs` is the expensive field and the chapter list needs none of
    // it, but IndexedDB has no projection: a row comes back whole or not at
    // all. Reading its length and dropping it is still cheaper than the
    // alternative of a duplicate summary store to keep in sync.
    const rows = await this.database.chapters.where({ bookId: id }).toArray()
    rows.sort((a, b) => a.index - b.index)
    return rows.map((row) => ({
      index: row.index,
      title: row.title,
      tokenCount: row.tokenCount,
      paragraphCount: row.paragraphs.length,
    }))
  }

  async getChapter(id: BookId, index: number): Promise<Chapter | undefined> {
    const row = await this.database.chapters.get([id, index])
    return row ? toChapter(row) : undefined
  }

  async getLexiconEntries(
    id: BookId,
    keys: readonly LemmaKey[],
  ): Promise<Map<LemmaKey, LexiconEntry>> {
    const found = new Map<LemmaKey, LexiconEntry>()
    if (keys.length === 0) return found

    const rows = await this.database.lexicon.bulkGet(
      keys.map((key) => [id, key] as [string, string]),
    )
    for (const row of rows) {
      if (row) found.set(row.key, row.entry)
    }
    return found
  }

  async saveBundle(bundle: Bundle, importedAt: Date): Promise<void> {
    const bookId = bundle.book.id
    const { books, chapters, lexicon, positions } = this.database

    await this.database.transaction(
      'rw',
      [books, chapters, lexicon, positions],
      async () => {
        // Re-importing a book replaces it. Anything else leaves a chapter from
        // the old build sitting next to the lexicon of the new one.
        await this.clear(bookId)

        await books.put({
          ...bundle.book,
          chapterCount: bundle.chapters.length,
          importedAt,
        })

        const chapterRows: ChapterRow[] = bundle.chapters.map((chapter) => ({
          bookId,
          index: chapter.index,
          title: chapter.title,
          tokenCount: chapter.tokenCount,
          paragraphs: chapter.paragraphs,
          teachSet: chapter.teachSet,
          glossOnly: chapter.glossOnly,
        }))
        await this.putChunked(chapters, chapterRows)

        const lexiconRows: LexiconRow[] = Object.entries(bundle.lexicon).map(
          ([key, entry]) => ({ bookId, key, entry }),
        )
        await this.putChunked(lexicon, lexiconRows)
      },
    )
  }

  async deleteBook(id: BookId): Promise<void> {
    const { books, chapters, lexicon, positions } = this.database
    await this.database.transaction(
      'rw',
      [books, chapters, lexicon, positions],
      () => this.clear(id),
    )
  }

  private async clear(id: BookId): Promise<void> {
    await this.database.books.delete(id)
    await this.database.chapters.where({ bookId: id }).delete()
    await this.database.lexicon.where({ bookId: id }).delete()
    await this.database.positions.where({ bookId: id }).delete()
  }

  private async putChunked<T, K>(table: Table<T, K>, rows: T[]): Promise<void> {
    for (let i = 0; i < rows.length; i += WRITE_CHUNK) {
      await table.bulkPut(rows.slice(i, i + WRITE_CHUNK))
    }
  }
}
