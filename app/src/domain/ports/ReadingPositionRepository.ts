/**
 * Where the reader left off, per chapter.
 *
 * Positions are recorded as a paragraph id rather than a scroll offset. An
 * offset is a fact about one device at one font size in one orientation; a
 * paragraph id is a fact about the book, so it survives rotating the iPad,
 * changing the type size, and eventually a native rewrite.
 */

import type { BookId } from '../types'

export interface ReadingPosition {
  bookId: BookId
  chapterIndex: number
  paragraphId: string
  /** 0..1, precomputed so the chapter list needs no paragraph data to draw it. */
  fraction: number
  updatedAt: Date
}

export interface ReadingPositionRepository {
  get(bookId: BookId, chapterIndex: number): Promise<ReadingPosition | undefined>

  /** Every position in a book, keyed by chapter index. */
  listForBook(bookId: BookId): Promise<Map<number, ReadingPosition>>

  put(position: ReadingPosition): Promise<void>
}
