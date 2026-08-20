/**
 * View model for #/notizen — SPEC §6.4's saved phrases, cross-book.
 */

import type { BookSummary } from '../ports/BookRepository'
import type { Bookmark } from '../ports/BookmarkRepository'
import type { BookId } from '../types'

export interface NotizenRow {
  id: number
  bookId: BookId
  bookTitle: string
  chapterIndex: number
  text: string
  createdAt: Date
}

export interface NotizenView {
  rows: NotizenRow[]
  isEmpty: boolean
}

export function buildNotizenView(
  bookmarks: readonly Bookmark[],
  books: readonly BookSummary[],
): NotizenView {
  const titles = new Map(books.map((book) => [book.id, book.title]))
  const rows = bookmarks.map((bookmark) => ({
    id: bookmark.id,
    bookId: bookmark.bookId,
    bookTitle: titles.get(bookmark.bookId) ?? bookmark.bookId,
    chapterIndex: bookmark.chapterIndex,
    text: bookmark.text,
    createdAt: bookmark.createdAt,
  }))
  return { rows, isEmpty: rows.length === 0 }
}
