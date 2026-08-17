/**
 * View model for the chapter list.
 *
 * Phase 4 adds the two numbers SPEC §6.2 asks a row to carry — how much there
 * is to learn, and how much of the chapter you could already read — plus the
 * §13.2 diagnostic about the book as a whole.
 *
 * **Nothing here locks anything.** SPEC §13 decision 2 is explicit: coverage is
 * displayed, warned about below 0.90, and never blocks entry. There is no
 * `locked` field on a row for a screen to be tempted by, and `ChapterList`
 * navigates straight to the reader on tap exactly as it did in Phase 3.
 *
 * The warning is about the *book*, not about the reader. §13.2: coverage's real
 * job "is to tell you whether the book is right for your level, not whether the
 * chapter is ready. If a chapter needs five sessions to clear 90%, switch books
 * — that signal is worth more than a lock screen." German phrasing lives in
 * `src/ui/format.ts`; this file only decides what is true.
 */

import { computeCoverage, type ChapterVocabulary } from '../coverage'
import type { LemmaId } from '../lemma'
import type { ChapterSummary } from '../ports/BookRepository'
import type { ReadingPosition } from '../ports/ReadingPositionRepository'
import { sessionsRemaining } from '../segments'
import { toLemmaIds } from '../teachSet'
import type { LemmaKey, LexiconEntry } from '../types'

export interface ChapterRowView {
  index: number
  title: string
  tokenCount: number
  /** 0..1, or null when the chapter has never been opened. */
  fraction: number | null
  /** 0..1. The share of this chapter's words you can already read. */
  coverage: number
  /** What coverage would be after every pending session. */
  projectedCoverage: number
  /** Cards still to be taught for this chapter, across all its sessions. */
  cardsToLearn: number
  /** How many sessions those cards need at 18 a time. */
  sessionsToGo: number
}

export interface ChapterListView {
  title: string
  author: string
  rows: ChapterRowView[]
  /** The chapter a `Continue reading` action should open. */
  resumeIndex: number | null
  /** Coverage across the whole book, weighted by chapter length. */
  bookCoverage: number
  /** Total sessions the book still needs. Feeds the §13.2 note. */
  bookSessionsToGo: number
}

export interface ChapterTeachingInput {
  vocabulary: ChapterVocabulary
  /** The recomputed teach set for this chapter. Never the bundle's. */
  teach: LemmaKey[]
}

export function buildChapterListView(
  book: { title: string; author: string },
  chapters: readonly ChapterSummary[],
  positions: ReadonlyMap<number, ReadingPosition>,
  teaching: ReadonlyMap<number, ChapterTeachingInput>,
  lexicon: ReadonlyMap<LemmaKey, LexiconEntry>,
  known: ReadonlySet<LemmaId>,
): ChapterListView {
  let coveredTokens = 0
  let totalTokens = 0
  let bookCards = 0

  const rows = chapters.map((chapter) => {
    const input = teaching.get(chapter.index)
    const vocabulary =
      input?.vocabulary ?? emptyVocabulary(chapter.tokenCount)
    const teach = input?.teach ?? []

    const coverage = computeCoverage(vocabulary, lexicon, known)
    // §5 Step 4's "known ∪ justTaught": what the chapter would be like after
    // you have studied it, which is the number worth deciding on.
    const projected = computeCoverage(
      vocabulary,
      lexicon,
      known,
      new Set(toLemmaIds(teach, lexicon)),
    )

    coveredTokens += coverage * vocabulary.tokenCount
    totalTokens += vocabulary.tokenCount
    bookCards += teach.length

    return {
      index: chapter.index,
      title: chapter.title,
      tokenCount: chapter.tokenCount,
      fraction: positions.get(chapter.index)?.fraction ?? null,
      coverage,
      projectedCoverage: projected,
      cardsToLearn: teach.length,
      sessionsToGo: sessionsRemaining(teach.length),
    }
  })

  return {
    title: book.title,
    author: book.author,
    rows,
    resumeIndex: mostRecentlyRead(positions),
    // Weighted by length: a 200-word chapter should not move the book's figure
    // as much as a 30,000-word one.
    bookCoverage: totalTokens === 0 ? 1 : coveredTokens / totalTokens,
    bookSessionsToGo: sessionsRemaining(bookCards),
  }
}

function emptyVocabulary(tokenCount: number): ChapterVocabulary {
  return { counts: new Map(), propnTokens: 0, tokenCount }
}

function mostRecentlyRead(
  positions: ReadonlyMap<number, ReadingPosition>,
): number | null {
  let best: ReadingPosition | null = null
  for (const position of positions.values()) {
    if (!best || position.updatedAt.getTime() > best.updatedAt.getTime()) {
      best = position
    }
  }
  return best?.chapterIndex ?? null
}
