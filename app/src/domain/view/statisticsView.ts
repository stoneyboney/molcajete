/**
 * View model for #/statistik — snapshot only, per the product decision
 * recorded when this screen was scoped: every number here is derived live
 * from data that already exists (card schedules, known-lemma marks, chapter
 * counts, reading positions), nothing is a logged trend over time, and
 * nothing compares against a target. That keeps it a diagnostic rather than
 * the progress-tracker/nudge CLAUDE.md's non-goals rule out.
 */

import { countKnownByProvenance } from '../knownLemmas'
import type { KnownLemmaSource } from '../ports/KnownLemmaRepository'
import type { LemmaId } from '../lemma'
import type { SrsCard } from '../srs/scheduler'
import type { BookId } from '../types'

export interface StatisticsBookInput {
  id: BookId
  title: string
  chapterCount: number
  /** Chapters with a saved reading position — "opened," not "finished." */
  chaptersOpened: number
  /** 0..1, the same weighted book-coverage figure the chapter list shows. */
  coverage: number
}

export interface StatisticsViewInput {
  cards: readonly SrsCard[]
  knownLemmaSources: ReadonlyMap<LemmaId, KnownLemmaSource | undefined>
  books: readonly StatisticsBookInput[]
}

export interface CardsByWeek {
  /** Monday, UTC midnight, of the week these cards were created in. */
  weekStart: Date
  count: number
}

export interface StatisticsBookRow {
  id: BookId
  title: string
  coverage: number
  chaptersOpened: number
  chapterCount: number
}

export interface StatisticsView {
  vocabularyKnown: number
  cardsTotal: number
  /** Oldest week first. */
  cardsByWeek: CardsByWeek[]
  books: StatisticsBookRow[]
}

/** Monday-start week, UTC-based to stay a pure function of its input. */
function weekStart(date: Date): Date {
  const midnight = new Date(
    Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()),
  )
  const day = midnight.getUTCDay()
  const daysSinceMonday = day === 0 ? 6 : day - 1
  midnight.setUTCDate(midnight.getUTCDate() - daysSinceMonday)
  return midnight
}

export function buildStatisticsView(input: StatisticsViewInput): StatisticsView {
  const known = countKnownByProvenance(input.cards, input.knownLemmaSources)

  const byWeek = new Map<number, number>()
  for (const card of input.cards) {
    const key = weekStart(card.createdAt).getTime()
    byWeek.set(key, (byWeek.get(key) ?? 0) + 1)
  }
  const cardsByWeek = [...byWeek.entries()]
    .sort(([a], [b]) => a - b)
    .map(([time, count]) => ({ weekStart: new Date(time), count }))

  return {
    vocabularyKnown: known.total,
    cardsTotal: input.cards.length,
    cardsByWeek,
    books: input.books.map((book) => ({
      id: book.id,
      title: book.title,
      coverage: book.coverage,
      chaptersOpened: book.chaptersOpened,
      chapterCount: book.chapterCount,
    })),
  }
}
