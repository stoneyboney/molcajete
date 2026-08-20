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

import type { ChapterVocabulary } from '../coverage'
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
   * A chapter's lemma counts, without its paragraphs.
   *
   * The chapter list needs coverage and a card count for every chapter at once.
   * Doing that through `getChapter` would deserialise the entire book — 11 MB
   * for `las-noches-mejicanas` — to answer a question about a few thousand
   * integers. This returns the derived counts instead, which the implementation
   * computes once and keeps.
   */
  getChapterVocabulary(
    id: BookId,
    index: number,
  ): Promise<ChapterVocabulary | undefined>

  /** Every chapter's counts, keyed by chapter index. What the chapter list calls. */
  listChapterVocabularies(id: BookId): Promise<Map<number, ChapterVocabulary>>

  /**
   * Every lexicon entry in the book.
   *
   * The exception to "never read a whole book". Entries are small — no
   * paragraphs, no tokens — and the chapter list has to classify all of them
   * against the §5 rules anyway. 9,024 of them is well under a megabyte, next
   * to the 11 MB that reading the chapters would cost.
   */
  getLexicon(id: BookId): Promise<Map<LemmaKey, LexiconEntry>>

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

  /** A count, not the entries. Diagnostics only — cheaper than `getLexicon`. */
  countLexiconEntries(id: BookId): Promise<number>

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
