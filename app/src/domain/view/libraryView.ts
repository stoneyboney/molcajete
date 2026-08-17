/**
 * View model for the library screen.
 *
 * Carries numbers and flags, never formatted strings. The German copy and the
 * thousands separators live in `src/ui/format.ts`, which keeps this file
 * language-neutral for the Swift port and still leaves the component with
 * nothing to compute (CLAUDE.md rule 5).
 */

import type { BookSummary } from '../ports/BookRepository'
import type { BookId } from '../types'

export interface LibraryRowView {
  id: BookId
  title: string
  author: string
  chapterCount: number
  totalTokens: number
  uniqueLemmas: number
}

export interface LibraryView {
  rows: LibraryRowView[]
  isEmpty: boolean
}

export function buildLibraryView(books: readonly BookSummary[]): LibraryView {
  const rows = books.map((book) => ({
    id: book.id,
    title: book.title,
    author: book.author,
    chapterCount: book.chapterCount,
    totalTokens: book.totalTokens,
    uniqueLemmas: book.uniqueLemmas,
  }))
  return { rows, isEmpty: rows.length === 0 }
}
