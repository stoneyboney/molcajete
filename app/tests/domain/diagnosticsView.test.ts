import { describe, expect, it } from 'vitest'
import type { BookSummary } from '../../src/domain/ports/BookRepository'
import { buildDiagnosticsView } from '../../src/domain/view/diagnosticsView'
import { newCard } from '../../src/domain/srs/scheduler'
import type { TeachingSession } from '../../src/domain/session/session'

const NOW = new Date('2026-08-20T09:00:00Z')

function book(over: Partial<BookSummary> = {}): BookSummary {
  return {
    id: 'azuela-los-de-abajo',
    title: 'Los de abajo',
    author: 'Mariano Azuela',
    language: 'es',
    variant: 'es-MX',
    totalTokens: 34442,
    uniqueLemmas: 5267,
    chapterCount: 42,
    importedAt: NOW,
    ...over,
  }
}

function session(over: Partial<TeachingSession> = {}): TeachingSession {
  return {
    bookId: 'azuela-los-de-abajo',
    chapterIndex: 0,
    phase: 'recall',
    queue: [{ key: 'm1', lemmaId: 'jacal', introduced: true }],
    passed: ['m2'],
    dismissed: [],
    total: 3,
    startedAt: NOW,
    updatedAt: NOW,
    ...over,
  }
}

const emptyEnvironment = {
  schemaVersion: { live: 4, expected: 4 },
  storageEstimate: { usageBytes: undefined, quotaBytes: undefined, supported: false },
  serviceWorker: { supported: false, registered: false, waiting: false },
  buildFingerprint: { cacheNames: [], precacheRevision: undefined },
}

describe('buildDiagnosticsView', () => {
  it('flags a schema mismatch', () => {
    const view = buildDiagnosticsView({
      books: [],
      lexiconCounts: new Map(),
      cards: [],
      knownLemmaSources: new Map(),
      sessions: [],
      errors: [],
      imports: [],
      ...emptyEnvironment,
      schemaVersion: { live: 3, expected: 4 },
    })
    expect(view.schema).toEqual({ live: 3, expected: 4, matches: false })
  })

  it('pairs each book with its lexicon count, defaulting to zero when uncounted', () => {
    const view = buildDiagnosticsView({
      books: [book(), book({ id: 'other', title: 'Other' })],
      lexiconCounts: new Map([['azuela-los-de-abajo', 5267]]),
      cards: [],
      knownLemmaSources: new Map(),
      sessions: [],
      errors: [],
      imports: [],
      ...emptyEnvironment,
    })
    expect(view.books).toEqual([
      { id: 'azuela-los-de-abajo', title: 'Los de abajo', chapterCount: 42, lexiconEntryCount: 5267 },
      { id: 'other', title: 'Other', chapterCount: 42, lexiconEntryCount: 0 },
    ])
  })

  it('resolves a session against its book title', () => {
    const view = buildDiagnosticsView({
      books: [book()],
      lexiconCounts: new Map(),
      cards: [],
      knownLemmaSources: new Map(),
      sessions: [session()],
      errors: [],
      imports: [],
      ...emptyEnvironment,
    })
    expect(view.sessions).toEqual([
      {
        bookId: 'azuela-los-de-abajo',
        bookTitle: 'Los de abajo',
        chapterIndex: 0,
        phase: 'recall',
        total: 3,
        passed: 1,
        remainingInQueue: 1,
        updatedAt: NOW,
      },
    ])
  })

  it('reports the newest import as lastImport, and keeps the rest as history', () => {
    const imports = [
      { id: 2, at: NOW, outcome: { fileShape: 'known' as const, result: 'success' as const, inFile: 5, added: 2, total: 5 } },
      { id: 1, at: NOW, outcome: { fileShape: 'unrecognised' as const, result: 'failure' as const, errorName: 'UnrecognisedFileError', message: 'nope' } },
    ]
    const view = buildDiagnosticsView({
      books: [],
      lexiconCounts: new Map(),
      cards: [],
      knownLemmaSources: new Map(),
      sessions: [],
      errors: [],
      imports,
      ...emptyEnvironment,
    })
    expect(view.lastImport).toBe(imports[0])
    expect(view.importHistory).toBe(imports)
  })

  it('assembles card state counts and known provenance from the same inputs used elsewhere', () => {
    const cards = [newCard('sierra', NOW)]
    const view = buildDiagnosticsView({
      books: [],
      lexiconCounts: new Map(),
      cards,
      knownLemmaSources: new Map([['jacal', 'seed']]),
      sessions: [],
      errors: [],
      imports: [],
      ...emptyEnvironment,
    })
    expect(view.cards.total).toBe(1)
    expect(view.cards.byState.new).toBe(1)
    expect(view.known.seed).toBe(1)
    expect(view.known.total).toBe(1)
  })
})
