import { describe, expect, it } from 'vitest'
import { parseBundle } from '../../src/domain/bundle/parseBundle'
import { countChapterVocabulary } from '../../src/domain/coverage'
import {
  MAX_CARDS_PER_SESSION,
  sessionsRemaining,
  splitChapterIfNeeded,
} from '../../src/domain/segments'
import { selectTeachSet } from '../../src/domain/teachSet'
import {
  isTappable,
  type Chapter,
  type LemmaKey,
  type LexiconEntry,
} from '../../src/domain/types'
import { readFixture } from '../fixture'

/** A chapter of `n` paragraphs, each introducing `perParagraph` fresh lemmas. */
function chapterOf(paragraphCount: number, perParagraph: number): Chapter {
  let next = 0
  const paragraphs = Array.from({ length: paragraphCount }, (_, p) => ({
    id: `c0p${p}`,
    tokens: Array.from({ length: perParagraph }, () => {
      const key = `m${String(next++).padStart(3, '0')}`
      return { s: key, l: key, p: 'NOUN', t: key }
    }),
  }))
  return {
    index: 0,
    title: 'Capítulo 1',
    tokenCount: paragraphCount * perParagraph,
    paragraphs,
    teachSet: [],
    glossOnly: [],
  }
}

function keysOf(chapter: Chapter): LemmaKey[] {
  const keys: LemmaKey[] = []
  for (const paragraph of chapter.paragraphs) {
    for (const token of paragraph.tokens) {
      if (isTappable(token)) keys.push(token.t)
    }
  }
  return keys
}

describe('a chapter under the cap', () => {
  it('is one segment covering the whole chapter', () => {
    const chapter = chapterOf(4, 3)
    const segments = splitChapterIfNeeded(chapter, keysOf(chapter))

    expect(segments).toHaveLength(1)
    expect(segments[0]!.teachSet).toHaveLength(12)
    expect(segments[0]!.paragraphStart).toBe(0)
    expect(segments[0]!.paragraphEnd).toBe(4)
    expect(segments[0]!.firstParagraphId).toBe('c0p0')
  })

  it('is still one segment when there is nothing to teach', () => {
    // "Nothing to learn here" is a segment the screens can render. An empty
    // array would make every caller handle a case that means the same thing.
    const segments = splitChapterIfNeeded(chapterOf(3, 2), [])
    expect(segments).toHaveLength(1)
    expect(segments[0]!.teachSet).toEqual([])
    expect(segments[0]!.paragraphEnd).toBe(3)
  })
})

describe('a chapter over the cap', () => {
  const chapter = chapterOf(10, 5) // 50 lemmas, 5 per paragraph
  const segments = splitChapterIfNeeded(chapter, keysOf(chapter))

  it('splits into enough sessions to cover it', () => {
    // Segments fill to a paragraph boundary, not to exactly 18: a fourth
    // paragraph would take this segment to 20, so it closes at 15.
    expect(segments.map((s) => s.teachSet.length)).toEqual([15, 15, 15, 5])
    const total = segments.reduce((n, s) => n + s.teachSet.length, 0)
    expect(total).toBe(50)
  })

  it('keeps every session at or under the cap', () => {
    for (const segment of segments) {
      expect(segment.teachSet.length).toBeLessThanOrEqual(MAX_CARDS_PER_SESSION)
    }
  })

  it('covers the chapter end to end with no gap and no overlap', () => {
    expect(segments[0]!.paragraphStart).toBe(0)
    for (let i = 1; i < segments.length; i++) {
      expect(segments[i]!.paragraphStart).toBe(segments[i - 1]!.paragraphEnd)
    }
    expect(segments.at(-1)!.paragraphEnd).toBe(chapter.paragraphs.length)
  })

  it('cuts in reading order, so a session teaches what comes next', () => {
    // Segment 0 must be the *first* lemmas of the chapter, not the commonest
    // ones scattered across it.
    expect(segments[0]!.teachSet).toContain('m000')
    expect(segments[0]!.teachSet).not.toContain('m049')
    expect(segments.at(-1)!.teachSet).toContain('m049')
  })

  it('never splits a paragraph across two sessions', () => {
    for (const segment of segments) {
      expect(segment.paragraphEnd).toBeGreaterThan(segment.paragraphStart)
    }
  })
})

describe('a single paragraph introducing more than the cap', () => {
  it('overflows rather than teaching words from text you were not given', () => {
    const chapter = chapterOf(1, 25)
    const segments = splitChapterIfNeeded(chapter, keysOf(chapter))

    expect(segments).toHaveLength(1)
    expect(segments[0]!.teachSet).toHaveLength(25)
  })
})

describe('ordering within a session', () => {
  it('puts the most useful words first when a lexicon is supplied', () => {
    const chapter = chapterOf(2, 2)
    const lexicon = new Map<LemmaKey, LexiconEntry>(
      keysOf(chapter).map((key, i) => [
        key,
        {
          lemma: key,
          pos: 'NOUN',
          zipf: 3,
          bookCount: i, // m000 rarest, m003 commonest
          firstChapter: 0,
          mexicanism: false,
        },
      ]),
    )

    const [segment] = splitChapterIfNeeded(chapter, keysOf(chapter), 18, lexicon)
    expect(segment!.teachSet).toEqual(['m003', 'm002', 'm001', 'm000'])
  })
})

describe('sessionsRemaining', () => {
  it('rounds up, and is zero when there is nothing left', () => {
    expect(sessionsRemaining(0)).toBe(0)
    expect(sessionsRemaining(1)).toBe(1)
    expect(sessionsRemaining(18)).toBe(1)
    expect(sessionsRemaining(19)).toBe(2)
    expect(sessionsRemaining(3226)).toBe(180)
  })
})

describe('against the real fixture', () => {
  const bundle = parseBundle(readFixture())
  const lexicon = new Map(Object.entries(bundle.lexicon))

  function segmentsFor(chapterIndex: number) {
    const chapter = bundle.chapters[chapterIndex]!
    const { counts } = countChapterVocabulary(chapter)
    const { teach } = selectTeachSet(counts, lexicon, new Set())
    return splitChapterIfNeeded(chapter, teach, MAX_CARDS_PER_SESSION, lexicon)
  }

  it('fits chapter 1 into a single session at exactly the cap', () => {
    const segments = segmentsFor(0)
    expect(segments).toHaveLength(1)
    expect(segments[0]!.teachSet).toHaveLength(18)
  })

  it('splits chapter 2 in two — 22 cards does not fit', () => {
    // Its three paragraphs debut 8, 7 and 7 words. Two fit; the third would
    // make 22, so the first session takes 15 and the second the rest.
    const segments = segmentsFor(1)
    expect(segments.map((s) => s.teachSet.length)).toEqual([15, 7])
    expect(segments[0]!.paragraphEnd).toBe(2)
    expect(segments[1]!.paragraphStart).toBe(2)
  })

  it('teaches every card exactly once across the segments', () => {
    for (const index of [0, 1, 2]) {
      const segments = segmentsFor(index)
      const all = segments.flatMap((s) => s.teachSet)
      expect(new Set(all).size).toBe(all.length)
    }
  })
})
