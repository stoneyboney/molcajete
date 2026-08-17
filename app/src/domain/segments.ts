/**
 * SPEC §5 Step 3: the cap, and what to do when a chapter exceeds it.
 *
 * "Hard cap: 18 new cards per teaching session. If `teachSet(chapter) > 18`,
 * split the chapter into 2+ reading segments with their own sessions." This is
 * the only module that knows the number 18.
 *
 * ## Two orderings that look like they conflict, and do not
 *
 * §5 Step 3 also says to sort the teach set by `bookCount` descending, "most
 * useful words first, so a partial session still helps". But a segment has to
 * teach the words you are about to read, which is reading order. Sorting the
 * whole chapter by `bookCount` and slicing it into eighteens would give the
 * first session the eighteen commonest words of the chapter, scattered across
 * forty pages — and then send you off to read page one, for which you were
 * taught almost nothing.
 *
 * The two requirements live at different levels. **Segments are cut in reading
 * order**, so segment one teaches segment one's vocabulary. **Within a segment**
 * the cards are ordered by `bookCount`, so abandoning a session halfway still
 * banked the words worth having. Both hold at once.
 *
 * ## Why the caller only ever runs the first segment
 *
 * Segment indices are not persisted anywhere. They cannot be: the candidate list
 * shrinks as words gain cards, so a segment numbered 3 today is numbered 1
 * tomorrow. Finishing a session removes exactly its own words from the next
 * selection, so "the next session for this chapter" is always the first segment
 * of what is left. Everything past `[0]` is a forecast for the chapter list —
 * how much is still ahead — not a plan to be followed.
 */

import type { Chapter, LemmaKey, LexiconEntry } from './types'

/** SPEC §5 Step 3, and CLAUDE.md's settled decisions table. */
export const MAX_CARDS_PER_SESSION = 18

export interface ReadingSegment {
  /** Position within this chapter, for display only. Never persisted. */
  index: number
  /** At most `maxCards`, ordered by `bookCount` descending. */
  teachSet: LemmaKey[]
  /** Index of the first paragraph this segment covers. */
  paragraphStart: number
  /** One past the last paragraph. `slice(start, end)` covers the segment. */
  paragraphEnd: number
  firstParagraphId: string
}

/**
 * Cut a chapter into sessions.
 *
 * Always returns at least one segment, even for an empty teach set — "nothing
 * to learn here" is a segment the screens can render, and returning an empty
 * array would make every caller handle a case that means the same thing.
 */
export function splitChapterIfNeeded(
  chapter: Chapter,
  teachSet: readonly LemmaKey[],
  maxCards: number = MAX_CARDS_PER_SESSION,
  lexicon?: ReadonlyMap<LemmaKey, LexiconEntry>,
): ReadingSegment[] {
  const pending = new Set(teachSet)
  const segments: ReadingSegment[] = []

  let current: LemmaKey[] = []
  let start = 0

  const close = (end: number) => {
    segments.push({
      index: segments.length,
      teachSet: orderByBookCount(current, lexicon),
      paragraphStart: start,
      paragraphEnd: end,
      firstParagraphId: chapter.paragraphs[start]?.id ?? '',
    })
    current = []
    start = end
  }

  for (let i = 0; i < chapter.paragraphs.length; i++) {
    // The teach lemmas making their first appearance in this paragraph. A
    // paragraph is never split across two sessions: you cannot read half of it.
    const debuts: LemmaKey[] = []
    for (const token of chapter.paragraphs[i]!.tokens) {
      if (token.ws === true || token.t === undefined) continue
      if (pending.delete(token.t)) debuts.push(token.t)
    }

    // Closing *before* adding is what keeps a segment at or under the cap. A
    // single paragraph introducing more than `maxCards` words overflows on its
    // own — splitting it would mean a session that teaches words from text you
    // are not given, which is worse than a session of 19.
    if (current.length > 0 && current.length + debuts.length > maxCards) {
      close(i)
    }
    current.push(...debuts)
  }

  close(chapter.paragraphs.length)

  // Lemmas the counts claimed but no token carries — a partial import, or a
  // chapter whose teach set was computed against different paragraphs. They
  // still have to be taught, so they go in the last segment rather than
  // vanishing silently.
  if (pending.size > 0) {
    const last = segments[segments.length - 1]!
    last.teachSet = orderByBookCount(
      [...last.teachSet, ...pending],
      lexicon,
    ).slice(0, Math.max(maxCards, last.teachSet.length))
  }

  return segments
}

/** §5 Step 3's "most useful words first", applied within a single session. */
function orderByBookCount(
  keys: readonly LemmaKey[],
  lexicon?: ReadonlyMap<LemmaKey, LexiconEntry>,
): LemmaKey[] {
  const ordered = [...keys]
  if (!lexicon) return ordered
  ordered.sort((a, b) => {
    const byCount =
      (lexicon.get(b)?.bookCount ?? 0) - (lexicon.get(a)?.bookCount ?? 0)
    return byCount !== 0 ? byCount : a < b ? -1 : a > b ? 1 : 0
  })
  return ordered
}

/** How many sessions this chapter still needs. Display only. */
export function sessionsRemaining(
  teachSetSize: number,
  maxCards: number = MAX_CARDS_PER_SESSION,
): number {
  return Math.ceil(teachSetSize / maxCards)
}
