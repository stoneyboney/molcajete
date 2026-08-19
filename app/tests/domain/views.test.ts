import { describe, expect, it } from 'vitest'
import { parseRoute, routeToHash, type Route } from '../../src/app/routes'
import type { ChapterSummary } from '../../src/domain/ports/BookRepository'
import type { ReadingPosition } from '../../src/domain/ports/ReadingPositionRepository'
import type { LexiconEntry } from '../../src/domain/types'
import {
  buildChapterListView,
  type ChapterTeachingInput,
} from '../../src/domain/view/chapterListView'
import { buildGlossView } from '../../src/domain/view/glossView'
import { buildLibraryView } from '../../src/domain/view/libraryView'
import { readingFraction } from '../../src/domain/view/progress'

describe('readingFraction', () => {
  it('runs from the first paragraph to the last', () => {
    expect(readingFraction(0, 5)).toBe(0)
    expect(readingFraction(4, 5)).toBe(1)
    expect(readingFraction(2, 5)).toBe(0.5)
  })

  it('treats a one-paragraph chapter as read', () => {
    expect(readingFraction(0, 1)).toBe(1)
    expect(readingFraction(0, 0)).toBe(1)
  })

  it('clamps a position that no longer exists', () => {
    // A re-imported bundle can be shorter than the position saved against it.
    expect(readingFraction(99, 5)).toBe(1)
    expect(readingFraction(-3, 5)).toBe(0)
  })
})

describe('buildLibraryView', () => {
  it('reports emptiness rather than leaving the screen to work it out', () => {
    expect(buildLibraryView([]).isEmpty).toBe(true)
    expect(buildLibraryView([]).rows).toEqual([])
  })
})

describe('buildChapterListView', () => {
  const chapters: ChapterSummary[] = [
    { index: 0, title: 'Capítulo 1', tokenCount: 35, paragraphCount: 3 },
    { index: 1, title: 'Capítulo 2', tokenCount: 40, paragraphCount: 4 },
    { index: 2, title: 'Capítulo 3', tokenCount: 36, paragraphCount: 3 },
  ]

  const position = (
    chapterIndex: number,
    fraction: number,
    updatedAt: Date,
  ): ReadingPosition => ({
    bookId: 'b',
    chapterIndex,
    paragraphId: `c${chapterIndex}p0`,
    fraction,
    updatedAt,
  })

  const build = (
    positions: Map<number, ReadingPosition> = new Map(),
    teaching: Map<number, ChapterTeachingInput> = new Map(),
    lexicon: Map<string, LexiconEntry> = new Map(),
    known: Set<string> = new Set(),
  ) =>
    buildChapterListView(
      { title: 'Los del cerro', author: 'Anónimo' },
      chapters,
      positions,
      teaching,
      lexicon,
      known,
    )

  it('leaves an unopened chapter with no progress at all', () => {
    const view = build()
    expect(view.rows.map((row) => row.fraction)).toEqual([null, null, null])
    expect(view.resumeIndex).toBeNull()
  })

  it('resumes at the most recently read chapter, not the furthest one', () => {
    const view = build(
      new Map([
        [2, position(2, 0.9, new Date('2026-08-01T10:00:00Z'))],
        [0, position(0, 0.2, new Date('2026-08-14T10:00:00Z'))],
      ]),
    )
    expect(view.resumeIndex).toBe(0)
    expect(view.rows[0]?.fraction).toBe(0.2)
    expect(view.rows[1]?.fraction).toBeNull()
    expect(view.rows[2]?.fraction).toBe(0.9)
  })

  describe('coverage and cards, per SPEC §13 decision 2', () => {
    const lexicon = new Map<string, LexiconEntry>([
      ['m1', { lemma: 'jacal', pos: 'NOUN', zipf: 2, bookCount: 5, firstChapter: 0, mexicanism: false }],
      ['m2', { lemma: 'sierra', pos: 'NOUN', zipf: 3, bookCount: 5, firstChapter: 0, mexicanism: false }],
    ])

    /** 10 word tokens: 6 of m1, 2 of m2, 2 proper nouns. */
    const teaching = new Map<number, ChapterTeachingInput>([
      [
        0,
        {
          vocabulary: {
            counts: new Map([['m1', 6], ['m2', 2]]),
            propnTokens: 2,
            tokenCount: 10,
          },
          teach: ['m1', 'm2'],
        },
      ],
    ])

    it('counts proper nouns as covered before anything is learned', () => {
      const view = build(new Map(), teaching, lexicon)
      expect(view.rows[0]?.coverage).toBeCloseTo(0.2)
    })

    it('projects what the pending session would buy', () => {
      const view = build(new Map(), teaching, lexicon)
      expect(view.rows[0]?.projectedCoverage).toBe(1)
      expect(view.rows[0]?.cardsToLearn).toBe(2)
      expect(view.rows[0]?.sessionsToGo).toBe(1)
    })

    it('rises as lemmas become known', () => {
      const view = build(new Map(), teaching, lexicon, new Set(['jacal']))
      expect(view.rows[0]?.coverage).toBeCloseTo(0.8)
    })

    it('weights the book figure by chapter length', () => {
      // Chapter 0 contributes 10 tokens at 0.2; the other two contribute their
      // own tokenCounts at coverage 0, since they have no vocabulary yet.
      const view = build(new Map(), teaching, lexicon)
      expect(view.bookCoverage).toBeLessThan(0.2)
      expect(view.bookCoverage).toBeGreaterThan(0)
    })

    it('offers no lock, ever — there is no such field on a row', () => {
      // SPEC §13 decision 2: displayed, warned about, never blocking. A row
      // carries numbers and nothing a screen could read as permission.
      const view = build(new Map(), teaching, lexicon)
      expect(view.rows[0]).not.toHaveProperty('locked')
      expect(view.rows[0]).not.toHaveProperty('unlocked')
    })
  })
})

describe('buildGlossView', () => {
  const entry = (over: Partial<LexiconEntry> = {}): LexiconEntry => ({
    lemma: 'huizach',
    pos: 'NOUN',
    zipf: 1.2,
    bookCount: 1,
    firstChapter: 0,
    mexicanism: false,
    ...over,
  })

  it('reports a missing German gloss as null rather than an empty string', () => {
    // Wiktionary does not reach SPEC §12's 95% alone and the model half
    // rejects lemmas it doubts, so this is a normal state the sheet has to be
    // able to say out loud.
    const view = buildGlossView('m0037', entry())
    expect(view?.de).toBeNull()
    expect(view?.en).toBeNull()
    expect(view?.example).toBeNull()
  })

  it('carries the glosses and the book sentence when they are there', () => {
    const view = buildGlossView(
      'm0037',
      entry({
        de: 'die Akazie',
        en: 'acacia',
        example: { es: 'levantando polvo entre los huizaches.', chapterIndex: 0 },
      }),
    )
    expect(view?.de).toBe('die Akazie')
    expect(view?.en).toBe('acacia')
    expect(view?.example).toBe('levantando polvo entre los huizaches.')
  })

  it('passes a region note through whether or not the flag is set', () => {
    // The pipeline requires a note whenever `mexicanism` is true, but not the
    // reverse — the fixture's `huizach` is annotated "Mexiko, ländlich" with
    // the flag false. Gating the note on the flag would drop that.
    const unflagged = buildGlossView('m1', entry({ regionNote: 'Mexiko, ländlich' }))
    expect(unflagged?.regionNote).toBe('Mexiko, ländlich')
    expect(unflagged?.mexicanism).toBe(false)

    const flagged = buildGlossView(
      'm1',
      entry({ mexicanism: true, regionNote: 'MX, coloquial' }),
    )
    expect(flagged?.regionNote).toBe('MX, coloquial')
    expect(flagged?.mexicanism).toBe(true)
  })

  it('returns null for a key the lexicon slice does not hold', () => {
    expect(buildGlossView('m9999', undefined)).toBeNull()
  })
})

describe('routes', () => {
  const cases: [string, Route][] = [
    ['', { name: 'library' }],
    ['#', { name: 'library' }],
    ['#/', { name: 'library' }],
    ['#/book/anonimo-los-del-cerro', {
      name: 'chapters',
      bookId: 'anonimo-los-del-cerro',
    }],
    ['#/book/anonimo-los-del-cerro/ch/2', {
      name: 'reader',
      bookId: 'anonimo-los-del-cerro',
      chapterIndex: 2,
    }],
    ['#/book/anonimo-los-del-cerro/ch/2/lernen', {
      name: 'session',
      bookId: 'anonimo-los-del-cerro',
      chapterIndex: 2,
    }],
    ['#/wiederholen', { name: 'review' }],
  ]

  it.each(cases)('parses %s', (hash, route) => {
    expect(parseRoute(hash)).toEqual(route)
  })

  it('round-trips', () => {
    for (const [, route] of cases) {
      expect(parseRoute(routeToHash(route))).toEqual(route)
    }
  })

  it('falls back to the library rather than a dead screen', () => {
    for (const hash of [
      '#/book',
      '#/book//ch/1',
      '#/book/x/ch/nope',
      '#/book/x/ch/-1',
      '#/book/x/chapter/1',
      '#/book/x/ch/1/lesen',
      '#/book/x/ch/1/lernen/2',
      '#/nonsense',
    ]) {
      expect(parseRoute(hash)).toEqual({ name: 'library' })
    }
  })

  it('survives a book id with a slash or a space in it', () => {
    const route: Route = { name: 'chapters', bookId: 'a b/c' }
    expect(parseRoute(routeToHash(route))).toEqual(route)
  })
})
