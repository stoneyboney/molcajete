/**
 * Storage port for imported books.
 *
 * CLAUDE.md rule 4: this interface is the only thing the app knows about
 * persistence. In Swift the same interface gets a SwiftData implementation and
 * nothing above it changes.
 *
 * The shape is driven by one measurement. `las-noches-mejicanas` is 11 MB, with
 * a single chapter holding 2.8 MB across 1,046 paragraphs and a lexicon of
 * 9,024 entries. Opening chapter three must not deserialise the other eight
 * megabytes, so the port hands out chapters and lexicon slices, never a whole
 * book — there is deliberately no `getBundle`.
 */

import type { BookId, BookMeta, Bundle, Chapter, LemmaKey, LexiconEntry } from '../types'

/** What the library screen needs, without touching a single paragraph. */
export interface BookSummary extends BookMeta {
  chapterCount: number
  importedAt: Date
}

export interface BookRepository {
  listBooks(): Promise<BookSummary[]>

  getBook(id: BookId): Promise<BookSummary | undefined>

  /** Chapter titles and token counts, in order. No paragraphs. */
  listChapters(id: BookId): Promise<ChapterSummary[]>

  getChapter(id: BookId, index: number): Promise<Chapter | undefined>

  /**
   * The lexicon entries for `keys`, as a map. Missing keys are simply absent:
   * a bundle that passed `parseBundle` cannot reference one, so an absence here
   * means a partial import, and the reader degrades to showing no gloss rather
   * than refusing to render the chapter.
   */
  getLexiconEntries(
    id: BookId,
    keys: readonly LemmaKey[],
  ): Promise<Map<LemmaKey, LexiconEntry>>

  /** Import, replacing any book already stored under the same id. */
  saveBundle(bundle: Bundle, importedAt: Date): Promise<void>

  deleteBook(id: BookId): Promise<void>
}

export interface ChapterSummary {
  index: number
  title: string
  tokenCount: number
  paragraphCount: number
}
