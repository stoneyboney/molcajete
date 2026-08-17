import { describe, expect, it } from 'vitest'
import { parseBundle } from '../../src/domain/bundle/parseBundle'
import { countChapterVocabulary } from '../../src/domain/coverage'
import { lemmaId } from '../../src/domain/lemma'
import {
  CLOSED_CLASS_POS,
  DEFAULT_TEACH_SET_OPTIONS,
  isTeachable,
  selectTeachSet,
  toLemmaIds,
  type TeachSetOptions,
} from '../../src/domain/teachSet'
import type { LemmaKey, LexiconEntry } from '../../src/domain/types'
import { readFixture } from '../fixture'

function entry(over: Partial<LexiconEntry> = {}): LexiconEntry {
  return {
    lemma: 'madriguera',
    pos: 'NOUN',
    zipf: 2.9,
    bookCount: 14,
    firstChapter: 0,
    mexicanism: false,
    ...over,
  }
}

function options(over: Partial<TeachSetOptions> = {}): TeachSetOptions {
  return { ...DEFAULT_TEACH_SET_OPTIONS, ...over }
}

function select(
  entries: Record<LemmaKey, LexiconEntry>,
  known: string[] = [],
  opts: Partial<TeachSetOptions> = {},
) {
  const lexicon = new Map(Object.entries(entries))
  const counts = new Map([...lexicon.keys()].map((key) => [key, 1]))
  return selectTeachSet(counts, lexicon, new Set(known), options(opts))
}

describe('the SPEC §5 rules, one at a time', () => {
  const base = { zipf: 0, bookCount: 0, mexicanism: false }

  it('teaches a word met three times — a card pays for itself', () => {
    expect(isTeachable(entry({ ...base, bookCount: 3 }), options())).toBe(true)
    expect(isTeachable(entry({ ...base, bookCount: 2 }), options())).toBe(false)
  })

  it('teaches a common word on zipf alone', () => {
    expect(isTeachable(entry({ ...base, zipf: 3.5 }), options())).toBe(true)
    expect(isTeachable(entry({ ...base, zipf: 3.49 }), options())).toBe(false)
  })

  it('teaches a mexicanism on two occurrences — this is why you are here', () => {
    const mex = { ...base, mexicanism: true }
    expect(isTeachable(entry({ ...mex, bookCount: 2 }), options())).toBe(true)
    expect(isTeachable(entry({ ...mex, bookCount: 1 }), options())).toBe(false)
    // Without the flag, two occurrences are not enough.
    expect(isTeachable(entry({ ...base, bookCount: 2 }), options())).toBe(false)
  })

  it('glosses everything else', () => {
    const { teach, glossOnly } = select({ m1: entry({ ...base, bookCount: 1 }) })
    expect(teach).toEqual([])
    expect(glossOnly).toEqual(['m1'])
  })
})

describe('proper nouns', () => {
  it('are skipped before the teach rules, not after', () => {
    // Read §5's table top-down and Demetrio — hundreds of occurrences, so
    // bookCount >= 3 fires first — earns a card. CLAUDE.md says otherwise.
    const demetrio = entry({ lemma: 'demetrio', pos: 'PROPN', bookCount: 400 })
    expect(isTeachable(demetrio, options())).toBe(false)
  })

  it('get no card and no gloss either', () => {
    const { teach, glossOnly } = select({
      m1: entry({ lemma: 'demetrio', pos: 'PROPN', bookCount: 400 }),
    })
    expect(teach).toEqual([])
    expect(glossOnly).toEqual([])
  })
})

describe('closed-class parts of speech', () => {
  // The measurement behind the rule: unmodified, §5 makes 16 of the first 18
  // cards of `las-noches-mejicanas` function words, because zipf >= 3.5 catches
  // every one and bookCount sorts them to the top of the session.
  const functionWords: Array<[string, string]> = [
    ['el', 'DET'],
    ['de', 'ADP'],
    ['él', 'PRON'],
    ['y', 'CCONJ'],
    ['que', 'SCONJ'],
    ['ser', 'AUX'],
  ]

  it.each(functionWords)('never teaches %s (%s)', (lemma, pos) => {
    const word = entry({ lemma, pos, zipf: 7.4, bookCount: 8691 })
    expect(isTeachable(word, options())).toBe(false)
  })

  it('still glosses them — the reader is unchanged', () => {
    const { teach, glossOnly } = select({
      m1: entry({ lemma: 'el', pos: 'DET', zipf: 7.45, bookCount: 8691 }),
    })
    expect(teach).toEqual([])
    expect(glossOnly).toEqual(['m1'])
  })

  it('keeps interjections teachable — ¡órale! is the point of the app', () => {
    expect(CLOSED_CLASS_POS.has('INTJ')).toBe(false)
    const orale = entry({ lemma: 'órale', pos: 'INTJ', bookCount: 4 })
    expect(isTeachable(orale, options())).toBe(true)
  })
})

describe('ordering', () => {
  it('puts the most useful words first, so a partial session still helps', () => {
    const { teach } = select({
      m1: entry({ lemma: 'raro', bookCount: 3 }),
      m2: entry({ lemma: 'casa', bookCount: 90 }),
      m3: entry({ lemma: 'perro', bookCount: 12 }),
    })
    expect(teach).toEqual(['m2', 'm3', 'm1'])
  })

  it('breaks ties on the key, so two runs agree', () => {
    const { teach } = select({
      m9: entry({ lemma: 'nueve', bookCount: 5 }),
      m1: entry({ lemma: 'eins', bookCount: 5 }),
    })
    expect(teach).toEqual(['m1', 'm9'])
  })
})

describe('what you already know', () => {
  it('is not taught and is not underlined', () => {
    const { teach, glossOnly } = select(
      { m1: entry({ lemma: 'madriguera' }) },
      ['madriguera'],
    )
    expect(teach).toEqual([])
    expect(glossOnly).toEqual([])
  })

  it('matches on the bare lemma however the entry is keyed', () => {
    // `estar` is in the real lexicon twice, as AUX and as VERB, under two
    // different keys. Learning the word settles both.
    const { teach } = select(
      {
        m3589: entry({ lemma: 'estar', pos: 'VERB', bookCount: 76 }),
        m3590: entry({ lemma: 'Estar ', pos: 'VERB', bookCount: 76 }),
      },
      ['estar'],
    )
    expect(teach).toEqual([])
  })
})

describe('a word that already has a card', () => {
  it('is not taught again, even though it is not yet known', () => {
    const { teach, glossOnly } = select({ m1: entry({ lemma: 'madriguera' }) }, [], {
      carded: new Set(['madriguera']),
    })
    // Not taught: you are already learning it. Not underlined either: you have
    // seen it introduced.
    expect(teach).toEqual([])
    expect(glossOnly).toEqual([])
  })
})

describe('cards are global, not per book', () => {
  it('never teaches in book B a word that was learned in book A', () => {
    // The two books key the same Spanish word differently, which is exactly the
    // trap: `m0031` means nothing outside its own bundle.
    const bookA = new Map([['m0031', entry({ lemma: 'madriguera' })]])
    const bookB = new Map([['m0777', entry({ lemma: 'madriguera' })]])

    const learnedInA = new Set(toLemmaIds(['m0031'], bookA))
    expect(learnedInA).toEqual(new Set(['madriguera']))

    const { teach } = selectTeachSet(
      new Map([['m0777', 4]]),
      bookB,
      learnedInA,
      options(),
    )
    expect(teach).toEqual([])
  })
})

describe('against the real fixture', () => {
  const bundle = parseBundle(readFixture())
  const lexicon = new Map(Object.entries(bundle.lexicon))

  function recompute(chapterIndex: number, known: string[] = []) {
    const chapter = bundle.chapters[chapterIndex]!
    const vocabulary = countChapterVocabulary(chapter)
    return selectTeachSet(vocabulary.counts, lexicon, new Set(known), options())
  }

  it('recomputes a different set than the bundle baked in', () => {
    // The point of recomputing at all. The pipeline's teachSet was computed
    // against a stale known-set and against `firstChapter`; ours is computed
    // here and now. They are not supposed to match, and nothing in the app
    // reads `Chapter.teachSet`.
    const { teach } = recompute(0)
    expect(bundle.chapters[0]!.teachSet).toHaveLength(25)
    expect(teach).toHaveLength(18)
  })

  it('fills chapter 1 to exactly the session cap', () => {
    const { teach } = recompute(0)
    expect(teach.length).toBe(18)
    const lemmas = teach.map((key) => lexicon.get(key)!.lemma)
    expect(lemmas).toContain('jacal') // the fixture's one mexicanism
    expect(lemmas).not.toContain('el')
  })

  it('drops a chapter’s cards once its shared words have been learned', () => {
    // Chapter 2 reuses sierra, caballo, jacal and fusil from chapter 1.
    const before = recompute(1).teach.length
    const learned = toLemmaIds(recompute(0).teach, lexicon)
    const after = recompute(1, learned).teach.length

    expect(before).toBe(22)
    expect(after).toBeLessThan(before)
  })

  it('teaches no proper noun and no closed-class word anywhere in the book', () => {
    for (const index of [0, 1, 2]) {
      for (const key of recompute(index).teach) {
        const { pos } = lexicon.get(key)!
        expect(pos).not.toBe('PROPN')
        expect(CLOSED_CLASS_POS.has(pos)).toBe(false)
      }
    }
  })

  it('leaves nothing to teach once every lemma is known', () => {
    const everything = Object.values(bundle.lexicon).map(lemmaId)
    const { teach, glossOnly } = recompute(0, everything)
    expect(teach).toEqual([])
    expect(glossOnly).toEqual([])
  })
})
