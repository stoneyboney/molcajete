import type { Table } from 'dexie'
import {
  countChapterVocabulary,
  type ChapterVocabulary,
} from '../domain/coverage'
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
import {
  db,
  type ChapterRow,
  type ChapterVocabularyRow,
  type LexiconRow,
  type MolcajeteDatabase,
} from './db'

/**
 * Written in chunks rather than one bulkPut. A 9,000-entry lexicon in a single
 * call builds one enormous argument array and holds every row live at once;
 * chunks let each batch be collected while the transaction stays open.
 */
const WRITE_CHUNK = 500

function toVocabularyRow(
  bookId: BookId,
  index: number,
  vocabulary: ChapterVocabulary,
): ChapterVocabularyRow {
  return {
    bookId,
    index,
    counts: Object.fromEntries(vocabulary.counts),
    propnTokens: vocabulary.propnTokens,
    tokenCount: vocabulary.tokenCount,
  }
}

function fromVocabularyRow(row: ChapterVocabularyRow): ChapterVocabulary {
  return {
    counts: new Map(Object.entries(row.counts)),
    propnTokens: row.propnTokens,
    tokenCount: row.tokenCount,
  }
}

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

  /**
   * Cached, and computed on a miss rather than migrated.
   *
   * A book imported before this store existed has no row here, and the counts
   * are pure a function of the chapter it already has — so the first read
   * computes them and writes them back. That is why version 2 needs no upgrade
   * function and no re-import.
   */
  async getChapterVocabulary(
    id: BookId,
    index: number,
  ): Promise<ChapterVocabulary | undefined> {
    const cached = await this.database.chapterVocab.get([id, index])
    if (cached) return fromVocabularyRow(cached)

    const chapter = await this.getChapter(id, index)
    if (!chapter) return undefined

    const vocabulary = countChapterVocabulary(chapter)
    await this.database.chapterVocab.put(toVocabularyRow(id, index, vocabulary))
    return vocabulary
  }

  async listChapterVocabularies(
    id: BookId,
  ): Promise<Map<number, ChapterVocabulary>> {
    const rows = await this.database.chapterVocab.where({ bookId: id }).toArray()
    const found = new Map(rows.map((row) => [row.index, fromVocabularyRow(row)]))

    // Fill any gap left by a book imported under version 1. This reads the
    // chapters, which is expensive — but exactly once per book, ever.
    const chapters = await this.database.chapters.where({ bookId: id }).toArray()
    for (const chapter of chapters) {
      if (found.has(chapter.index)) continue
      const vocabulary = countChapterVocabulary(toChapter(chapter))
      await this.database.chapterVocab.put(
        toVocabularyRow(id, chapter.index, vocabulary),
      )
      found.set(chapter.index, vocabulary)
    }

    return found
  }

  async getLexicon(id: BookId): Promise<Map<LemmaKey, LexiconEntry>> {
    const rows = await this.database.lexicon.where({ bookId: id }).toArray()
    return new Map(rows.map((row) => [row.key, row.entry]))
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
    const { books, chapters, lexicon, positions, chapterVocab, sessions } =
      this.database

    await this.database.transaction(
      'rw',
      [books, chapters, lexicon, positions, chapterVocab, sessions],
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

        // Derived here rather than on first read, because the paragraphs are
        // already in memory at this point and will not be again.
        await this.putChunked(
          chapterVocab,
          bundle.chapters.map((chapter) =>
            toVocabularyRow(bookId, chapter.index, countChapterVocabulary(chapter)),
          ),
        )
      },
    )
  }

  async deleteBook(id: BookId): Promise<void> {
    const { books, chapters, lexicon, positions, chapterVocab, sessions } =
      this.database
    await this.database.transaction(
      'rw',
      [books, chapters, lexicon, positions, chapterVocab, sessions],
      () => this.clear(id),
    )
  }

  /**
   * Everything scoped to this book, and deliberately nothing else.
   *
   * `cards` and `knownLemmas` are untouched. Removing a book removes its text;
   * it does not unlearn its vocabulary, and re-importing it must not re-teach
   * words you already know.
   */
  private async clear(id: BookId): Promise<void> {
    await this.database.books.delete(id)
    await this.database.chapters.where({ bookId: id }).delete()
    await this.database.lexicon.where({ bookId: id }).delete()
    await this.database.positions.where({ bookId: id }).delete()
    await this.database.chapterVocab.where({ bookId: id }).delete()
    await this.database.sessions.where({ bookId: id }).delete()
  }

  private async putChunked<T, K>(table: Table<T, K>, rows: T[]): Promise<void> {
    for (let i = 0; i < rows.length; i += WRITE_CHUNK) {
      await table.bulkPut(rows.slice(i, i + WRITE_CHUNK))
    }
  }
}
