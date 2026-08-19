/**
 * The IndexedDB schema. The only file in the app that knows Dexie exists,
 * together with the two repositories next to it (CLAUDE.md rule 4).
 *
 * A book is stored shredded rather than as one document. `las-noches-mejicanas`
 * is 11 MB of JSON; putting it in a single row would mean deserialising all of
 * it to open one chapter, on a device that is holding the whole thing in memory
 * while it does so. Instead:
 *
 *   books         one row  — everything the library screen draws
 *   chapters      one row per chapter, ~2.8 MB worst case, read one at a time
 *   lexicon       one row per entry, ~9,000 per book, read as a per-chapter slice
 *   positions     one row per chapter the user has opened
 *   chapterVocab  one row per chapter — derived lemma counts, see below
 *   sessions      one row per teaching session in progress
 *   cards         FSRS state, one row per lemma — NOT scoped to a book
 *   knownLemmas   "Ich kenne das", one row per lemma — NOT scoped to a book
 *
 * The compound primary keys make the book id part of every key, so deleting a
 * book is a handful of range deletes and there is no way to read one book's
 * chapter with another book's lexicon.
 *
 * `cards` and `knownLemmas` are the deliberate exception: they carry no book id
 * at all, because a word learned in one book must never be taught again in
 * another. Deleting a book removes its text and leaves its vocabulary alone.
 *
 * `chapterVocab` is a cache of `countChapterVocabulary`, which is pure and
 * derives from the chapter row that is already stored. There is therefore no
 * upgrade function on version 2 and no reason to re-import: a book stored under
 * version 1 gets its counts computed on first read and kept from then on.
 */

import Dexie, { type Table } from 'dexie'
import type { LemmaId } from '../domain/lemma'
import type { TeachingSession } from '../domain/session/session'
import type { SrsCard } from '../domain/srs/scheduler'
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

/**
 * Derived from the chapter's paragraphs, cached because the chapter list needs
 * it for every chapter at once and the paragraphs are the expensive part.
 * `counts` is a plain object rather than a Map so that old Safari versions
 * structured-clone it without surprises.
 */
export interface ChapterVocabularyRow {
  bookId: string
  index: number
  counts: Record<LemmaKey, number>
  propnTokens: number
  tokenCount: number
}

export interface SessionRow {
  bookId: string
  chapterIndex: number
  session: TeachingSession
}

/** No `bookId`. See the header — that absence is the point. */
export interface CardRow {
  lemmaId: LemmaId
  card: SrsCard
}

/** No `bookId` here either. */
export interface KnownLemmaRow {
  lemmaId: LemmaId
  markedAt: Date
}

export class MolcajeteDatabase extends Dexie {
  books!: Table<BookRow, string>
  chapters!: Table<ChapterRow, [string, number]>
  lexicon!: Table<LexiconRow, [string, string]>
  positions!: Table<PositionRow, [string, number]>
  chapterVocab!: Table<ChapterVocabularyRow, [string, number]>
  sessions!: Table<SessionRow, [string, number]>
  cards!: Table<CardRow, string>
  knownLemmas!: Table<KnownLemmaRow, string>

  constructor(name = 'molcajete') {
    super(name)
    this.version(1).stores({
      books: 'id',
      chapters: '[bookId+index], bookId',
      lexicon: '[bookId+key], bookId',
      positions: '[bookId+chapterIndex], bookId',
    })
    // Phase 4. No upgrade function: every new store is either derived from data
    // already present (chapterVocab) or starts empty (the rest).
    this.version(2).stores({
      chapterVocab: '[bookId+index], bookId',
      sessions: '[bookId+chapterIndex], bookId',
      cards: 'lemmaId',
      knownLemmas: 'lemmaId',
    })
    // Phase 5. The review screen asks "what is due?" of every card there is, so
    // that question needs an index rather than a full scan. The key path reaches
    // into the stored FSRS object, which is where `due` lives and where it has
    // to stay — CLAUDE.md requires the whole card object, not a copy of one
    // field beside it. Dexie builds the index from the existing rows, so there
    // is no upgrade function here either.
    this.version(3).stores({
      cards: 'lemmaId, card.fsrs.due',
    })
  }
}

export const db = new MolcajeteDatabase()
