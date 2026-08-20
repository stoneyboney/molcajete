/**
 * Storage port for SPEC §6.4's "note-to-self bookmark."
 *
 * A phrase saved in the reader, no translation attached. Unlike `cards` and
 * `knownLemmas`, this store is deliberately book-scoped — a bookmark's whole
 * point is *where* in the text, and it has no meaning once its book is gone.
 */

import type { BookId } from '../types'

export interface Bookmark {
  id: number
  bookId: BookId
  chapterIndex: number
  paragraphId: string
  text: string
  createdAt: Date
}

export interface BookmarkRepository {
  /** Cross-book, newest first — #/notizen's whole selection. */
  listAll(): Promise<Bookmark[]>

  add(entry: {
    bookId: BookId
    chapterIndex: number
    paragraphId: string
    text: string
    createdAt: Date
  }): Promise<void>

  remove(id: number): Promise<void>
}
