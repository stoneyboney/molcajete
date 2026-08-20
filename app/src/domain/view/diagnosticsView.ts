/**
 * View model for `#/diagnose`. Rule 5: the screen computes nothing.
 *
 * Everything here is already-fetched data in, plain numbers/flags/dates out —
 * the same `buildXView(...) → viewModel` shape as `libraryView.ts` and the
 * rest of this folder. The environment-shaped input types (`schemaVersion`,
 * `storageEstimate`, `serviceWorker`, `buildFingerprint`) are defined here,
 * not imported from `src/app/`: `src/app/environment.ts` conforms to these
 * shapes, not the other way around, so this file stays free of any
 * dependency on the app layer (CLAUDE.md rule 4 in spirit, even though these
 * particular fields are environment inspection rather than storage).
 */

import type { BookSummary } from '../ports/BookRepository'
import type { ErrorLogEntry, ImportLogEntry } from '../ports/DiagnosticsRepository'
import type { KnownLemmaSource } from '../ports/KnownLemmaRepository'
import { countKnownByProvenance, type KnownProvenance } from '../knownLemmas'
import type { LemmaId } from '../lemma'
import type { TeachingSession } from '../session/session'
import { countByState, nextDue, type FsrsStateLabel, type SrsCard } from '../srs/scheduler'
import type { BookId } from '../types'

export interface DiagnosticsViewInput {
  books: readonly BookSummary[]
  lexiconCounts: ReadonlyMap<BookId, number>
  cards: readonly SrsCard[]
  knownLemmaSources: ReadonlyMap<LemmaId, KnownLemmaSource | undefined>
  sessions: readonly TeachingSession[]
  errors: readonly ErrorLogEntry[]
  imports: readonly ImportLogEntry[]
  schemaVersion: { live: number; expected: number }
  storageEstimate: { usageBytes: number | undefined; quotaBytes: number | undefined; supported: boolean }
  serviceWorker: { supported: boolean; registered: boolean; waiting: boolean }
  buildFingerprint: { cacheNames: readonly string[]; precacheRevision: string | undefined }
}

export interface DiagnosticsBookRow {
  id: BookId
  title: string
  chapterCount: number
  lexiconEntryCount: number
}

export interface DiagnosticsSessionRow {
  bookId: BookId
  /** Undefined if the book row is somehow gone — defensive, not expected: `deleteBook` removes its sessions too. */
  bookTitle: string | undefined
  chapterIndex: number
  phase: TeachingSession['phase']
  total: number
  passed: number
  remainingInQueue: number
  updatedAt: Date
}

export interface DiagnosticsView {
  schema: { live: number; expected: number; matches: boolean }
  serviceWorker: DiagnosticsViewInput['serviceWorker']
  buildFingerprint: DiagnosticsViewInput['buildFingerprint']
  storage: DiagnosticsViewInput['storageEstimate']
  books: DiagnosticsBookRow[]
  known: KnownProvenance
  cards: { byState: Record<FsrsStateLabel, number>; total: number; nextDueAt: Date | undefined }
  sessions: DiagnosticsSessionRow[]
  lastImport: ImportLogEntry | undefined
  importHistory: readonly ImportLogEntry[]
  errors: readonly ErrorLogEntry[]
}

export function buildDiagnosticsView(input: DiagnosticsViewInput): DiagnosticsView {
  const bookTitles = new Map(input.books.map((book) => [book.id, book.title]))

  return {
    schema: { ...input.schemaVersion, matches: input.schemaVersion.live === input.schemaVersion.expected },
    serviceWorker: input.serviceWorker,
    buildFingerprint: input.buildFingerprint,
    storage: input.storageEstimate,
    books: input.books.map((book) => ({
      id: book.id,
      title: book.title,
      chapterCount: book.chapterCount,
      lexiconEntryCount: input.lexiconCounts.get(book.id) ?? 0,
    })),
    known: countKnownByProvenance(input.cards, input.knownLemmaSources),
    cards: {
      byState: countByState(input.cards),
      total: input.cards.length,
      nextDueAt: nextDue(input.cards),
    },
    sessions: input.sessions.map((session) => ({
      bookId: session.bookId,
      bookTitle: bookTitles.get(session.bookId),
      chapterIndex: session.chapterIndex,
      phase: session.phase,
      total: session.total,
      passed: session.passed.length,
      remainingInQueue: session.queue.length,
      updatedAt: session.updatedAt,
    })),
    lastImport: input.imports[0],
    importHistory: input.imports,
    errors: input.errors,
  }
}
