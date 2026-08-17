/**
 * View model for the chapter list.
 *
 * Phase 3 shows what a chapter is and how far into it you are. It deliberately
 * does not show the SPEC §6.2 status chips — `Ready to learn`, `18 cards to
 * learn`, `Due: 12` all describe teach-set and scheduler state, which Phase 4
 * owns. The chapters carry their `teachSet` in storage already; nothing reads
 * it yet.
 */

import type { ChapterSummary } from '../ports/BookRepository'
import type { ReadingPosition } from '../ports/ReadingPositionRepository'

export interface ChapterRowView {
  index: number
  title: string
  tokenCount: number
  /** 0..1, or null when the chapter has never been opened. */
  fraction: number | null
}

export interface ChapterListView {
  title: string
  author: string
  rows: ChapterRowView[]
  /** The chapter a `Continue reading` action should open. */
  resumeIndex: number | null
}

export function buildChapterListView(
  book: { title: string; author: string },
  chapters: readonly ChapterSummary[],
  positions: ReadonlyMap<number, ReadingPosition>,
): ChapterListView {
  const rows = chapters.map((chapter) => ({
    index: chapter.index,
    title: chapter.title,
    tokenCount: chapter.tokenCount,
    fraction: positions.get(chapter.index)?.fraction ?? null,
  }))

  return {
    title: book.title,
    author: book.author,
    rows,
    resumeIndex: mostRecentlyRead(positions),
  }
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
