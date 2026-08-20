import { describe, expect, it } from 'vitest'
import type { KnownLemmaSource } from '../../src/domain/ports/KnownLemmaRepository'
import { newCard } from '../../src/domain/srs/scheduler'
import { buildStatisticsView } from '../../src/domain/view/statisticsView'

describe('buildStatisticsView', () => {
  it('counts vocabulary known from the same union buildKnownState uses', () => {
    const cards = [newCard('sierra', new Date('2026-01-01'))]
    const sources = new Map<string, KnownLemmaSource | undefined>([['jacal', 'seed']])
    const view = buildStatisticsView({ cards, knownLemmaSources: sources, books: [] })
    // `sierra` is carded but not matured, so only the seeded `jacal` counts.
    expect(view.vocabularyKnown).toBe(1)
    expect(view.cardsTotal).toBe(1)
  })

  it('buckets cards by the Monday of the week they were created', () => {
    // A Wednesday and the following Tuesday sit in different Mon-Sun weeks.
    const cards = [
      newCard('a', new Date('2026-01-07T10:00:00Z')), // Wednesday
      newCard('b', new Date('2026-01-13T10:00:00Z')), // Tuesday, next week
      newCard('c', new Date('2026-01-08T10:00:00Z')), // Thursday, same week as a
    ]
    const view = buildStatisticsView({ cards, knownLemmaSources: new Map(), books: [] })
    expect(view.cardsByWeek).toEqual([
      { weekStart: new Date('2026-01-05T00:00:00.000Z'), count: 2 },
      { weekStart: new Date('2026-01-12T00:00:00.000Z'), count: 1 },
    ])
  })

  it('is empty for no cards', () => {
    const view = buildStatisticsView({ cards: [], knownLemmaSources: new Map(), books: [] })
    expect(view.cardsByWeek).toEqual([])
    expect(view.vocabularyKnown).toBe(0)
    expect(view.cardsTotal).toBe(0)
  })

  it('passes book stats through unchanged', () => {
    const view = buildStatisticsView({
      cards: [],
      knownLemmaSources: new Map(),
      books: [
        { id: 'b1', title: 'Los de abajo', chapterCount: 42, chaptersOpened: 3, coverage: 0.61 },
      ],
    })
    expect(view.books).toEqual([
      { id: 'b1', title: 'Los de abajo', coverage: 0.61, chaptersOpened: 3, chapterCount: 42 },
    ])
  })
})
