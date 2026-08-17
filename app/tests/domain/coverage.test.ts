import { describe, expect, it } from 'vitest'
import { parseBundle } from '../../src/domain/bundle/parseBundle'
import {
  computeCoverage,
  countChapterVocabulary,
} from '../../src/domain/coverage'
import { lemmaId } from '../../src/domain/lemma'
import type { Chapter, LexiconEntry, Token } from '../../src/domain/types'
import { readFixture } from '../fixture'

function chapter(tokens: Token[]): Chapter {
  return {
    index: 0,
    title: 'Capítulo 1',
    tokenCount: tokens.filter((t) => t.ws !== true && t.l !== undefined).length,
    paragraphs: [{ id: 'c0p0', tokens }],
    teachSet: [],
    glossOnly: [],
  }
}

const word = (s: string, l: string, t: string): Token => ({ s, l, p: 'NOUN', t })
const propn = (s: string, l: string): Token => ({ s, l, p: 'PROPN' })
const space: Token = { s: ' ', ws: true }
const punct = (s: string): Token => ({ s, p: 'PUNCT' })

function entry(lemma: string): LexiconEntry {
  return {
    lemma,
    pos: 'NOUN',
    zipf: 3,
    bookCount: 5,
    firstChapter: 0,
    mexicanism: false,
  }
}

describe('countChapterVocabulary', () => {
  it('counts words, and only words', () => {
    const vocabulary = countChapterVocabulary(
      chapter([
        word('casa', 'casa', 'm1'),
        space,
        punct(','),
        space,
        word('casas', 'casa', 'm1'),
        space,
        word('perro', 'perro', 'm2'),
        punct('.'),
      ]),
    )

    expect(vocabulary.tokenCount).toBe(3)
    expect(vocabulary.counts.get('m1')).toBe(2)
    expect(vocabulary.counts.get('m2')).toBe(1)
    expect(vocabulary.propnTokens).toBe(0)
  })

  it('separates proper nouns out — they have a lemma but no key', () => {
    const vocabulary = countChapterVocabulary(
      chapter([word('casa', 'casa', 'm1'), space, propn('Demetrio', 'demetrio')]),
    )

    expect(vocabulary.tokenCount).toBe(2)
    expect(vocabulary.propnTokens).toBe(1)
    expect(vocabulary.counts.size).toBe(1)
  })
})

describe('computeCoverage', () => {
  const lexicon = new Map([
    ['m1', entry('casa')],
    ['m2', entry('perro')],
  ])

  const vocabulary = countChapterVocabulary(
    chapter([
      word('casa', 'casa', 'm1'),
      space,
      word('casa', 'casa', 'm1'),
      space,
      word('perro', 'perro', 'm2'),
      space,
      propn('Demetrio', 'demetrio'),
    ]),
  )

  it('counts a proper noun as covered', () => {
    // §5 skips PROPN entirely — no card, no gloss. Counting it unknown would
    // penalise a chapter for a decision the pipeline already made.
    expect(computeCoverage(vocabulary, lexicon, new Set())).toBeCloseTo(1 / 4)
  })

  it('rises as lemmas become known, by occurrence not by type', () => {
    // `casa` is one lemma but two tokens.
    expect(computeCoverage(vocabulary, lexicon, new Set(['casa']))).toBeCloseTo(3 / 4)
    expect(computeCoverage(vocabulary, lexicon, new Set(['perro']))).toBeCloseTo(2 / 4)
  })

  it('reaches 1 when everything is known', () => {
    const known = new Set(['casa', 'perro'])
    expect(computeCoverage(vocabulary, lexicon, known)).toBe(1)
  })

  it('projects what a pending session would buy', () => {
    // §5 Step 4's "known ∪ justTaught": the chapter list answers "what will
    // this be like after I study?", not only "what is it like now?".
    const now = computeCoverage(vocabulary, lexicon, new Set(['perro']))
    const after = computeCoverage(
      vocabulary,
      lexicon,
      new Set(['perro']),
      new Set(['casa']),
    )
    expect(now).toBeCloseTo(2 / 4)
    expect(after).toBe(1)
  })

  it('calls an empty chapter fully covered rather than dividing by zero', () => {
    expect(computeCoverage(countChapterVocabulary(chapter([])), lexicon, new Set()))
      .toBe(1)
  })
})

describe('against the real fixture', () => {
  const bundle = parseBundle(readFixture())
  const lexicon = new Map(Object.entries(bundle.lexicon))

  it('agrees with the tokenCount the pipeline wrote', () => {
    // The measurement the denominator rests on: `tokenCount` is exactly the
    // count of tokens carrying a lemma, and it partitions into keyed + PROPN.
    for (const chapter of bundle.chapters) {
      const vocabulary = countChapterVocabulary(chapter)
      const keyed = [...vocabulary.counts.values()].reduce((a, b) => a + b, 0)

      expect(vocabulary.tokenCount).toBe(chapter.tokenCount)
      expect(keyed + vocabulary.propnTokens).toBe(chapter.tokenCount)
    }
  })

  it('starts low and reaches 1 when the whole lexicon is known', () => {
    const vocabulary = countChapterVocabulary(bundle.chapters[0]!)
    const everything = new Set(Object.values(bundle.lexicon).map(lemmaId))

    expect(computeCoverage(vocabulary, lexicon, new Set())).toBeLessThan(0.2)
    expect(computeCoverage(vocabulary, lexicon, everything)).toBe(1)
  })
})
