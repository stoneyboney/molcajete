/**
 * The IndexedDB schema. The only file in the app that knows Dexie exists,
 * together with the two repositories next to it (CLAUDE.md rule 4).
 *
 * A book is stored shredded rather than as one document. `las-noches-mejicanas`
 * is 11 MB of JSON; putting it in a single row would mean deserialising all of
 * it to open one chapter, on a device that is holding the whole thing in memory
 * while it does so. Instead:
 *
 *   books      one row  — everything the library screen draws
 *   chapters   one row per chapter, ~2.8 MB worst case, read one at a time
 *   lexicon    one row per entry, ~9,000 per book, read as a per-chapter slice
 *   positions  one row per chapter the user has opened
 *
 * The compound primary keys make the book id part of every key, so deleting a
 * book is four range deletes and there is no way to read one book's chapter
 * with another book's lexicon.
 */

import Dexie, { type Table } from 'dexie'
import type { BookMeta, LemmaKey, LexiconEntry, Paragraph } from '../domain/types'

export interface BookRow extends BookMeta {
  chapterCount: number
  importedAt: Date
}

export interface ChapterRow {
  bookId: string
  index: number
  title: string
  tokenCount: number
  paragraphs: Paragraph[]
  teachSet: LemmaKey[]
  glossOnly: LemmaKey[]
}

export interface LexiconRow {
  bookId: string
  key: LemmaKey
  entry: LexiconEntry
}

export interface PositionRow {
  bookId: string
  chapterIndex: number
  paragraphId: string
  fraction: number
  updatedAt: Date
}

export class MolcajeteDatabase extends Dexie {
  books!: Table<BookRow, string>
  chapters!: Table<ChapterRow, [string, number]>
  lexicon!: Table<LexiconRow, [string, string]>
  positions!: Table<PositionRow, [string, number]>

  constructor(name = 'molcajete') {
    super(name)
    this.version(1).stores({
      books: 'id',
      chapters: '[bookId+index], bookId',
      lexicon: '[bookId+key], bookId',
      positions: '[bookId+chapterIndex], bookId',
    })
  }
}

export const db = new MolcajeteDatabase()
