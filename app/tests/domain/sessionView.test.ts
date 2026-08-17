import { describe, expect, it } from 'vitest'
import {
  grade,
  introduce,
  startSession,
  type SessionCardInput,
} from '../../src/domain/session/session'
import type { LemmaKey, LexiconEntry } from '../../src/domain/types'
import {
  buildSessionCardView,
  buildSessionView,
} from '../../src/domain/view/sessionView'

const START = new Date('2026-01-01T09:00:00Z')

function entry(over: Partial<LexiconEntry> = {}): LexiconEntry {
  return {
    lemma: 'jacal',
    pos: 'NOUN',
    zipf: 2.1,
    bookCount: 3,
    firstChapter: 0,
    mexicanism: true,
    de: 'Hütte',
    en: 'hut, shack',
    regionNote: 'MX, ländlich',
    example: { es: 'La puerta del jacal estaba abierta.' },
    ...over,
  }
}

const cards: SessionCardInput[] = [
  { key: 'm1', lemmaId: 'jacal' },
  { key: 'm2', lemmaId: 'sierra' },
]

const lexicon = new Map<LemmaKey, LexiconEntry>([
  ['m1', entry()],
  ['m2', entry({ lemma: 'sierra', de: 'Gebirge', en: 'mountain range' })],
])

describe('buildSessionCardView', () => {
  it('carries the gloss, the example and the regional note', () => {
    const view = buildSessionCardView('m1', entry())
    expect(view.lemma).toBe('jacal')
    expect(view.de).toBe('Hütte')
    expect(view.en).toBe('hut, shack')
    expect(view.example).toBe('La puerta del jacal estaba abierta.')
    expect(view.regionNote).toBe('MX, ländlich')
    expect(view.mexicanism).toBe(true)
  })

  it('reports a missing German gloss as null rather than an empty string', () => {
    // A Phase 1 bundle has no glosses at all, and the model half rejects lemmas
    // it does not believe are Spanish. "No gloss" is a normal state.
    const view = buildSessionCardView('m1', {
      lemma: 'cenir',
      pos: 'VERB',
      zipf: 0,
      bookCount: 3,
      firstChapter: 0,
      mexicanism: false,
    })
    expect(view.de).toBeNull()
    expect(view.en).toBeNull()
    expect(view.example).toBeNull()
  })

  it('degrades to the bare key when the entry is missing', () => {
    const view = buildSessionCardView('m9', undefined)
    expect(view.lemma).toBe('m9')
    expect(view.de).toBeNull()
  })
})

describe('buildSessionView', () => {
  it('starts on the first card with nothing answered', () => {
    const view = buildSessionView(startSession('b', 0, cards, START), lexicon)
    expect(view.phase).toBe('introduction')
    expect(view.card?.lemma).toBe('jacal')
    expect(view.answered).toBe(0)
    expect(view.total).toBe(2)
    expect(view.fraction).toBe(0)
  })

  it('advances the progress fraction as cards are settled', () => {
    let session = startSession('b', 0, cards, START)
    session = introduce(session, 'ichKenneDas', START).session
    const view = buildSessionView(session, lexicon)

    expect(view.answered).toBe(1)
    expect(view.fraction).toBe(0.5)
    expect(view.dismissed).toBe(1)
  })

  it('has no card once the session is complete', () => {
    let session = startSession('b', 0, cards, START)
    session = introduce(session, 'ichKenneDas', START).session
    session = introduce(session, 'weiter', START).session
    session = grade(session, 'good', START).session

    const view = buildSessionView(session, lexicon)
    expect(view.phase).toBe('complete')
    expect(view.card).toBeNull()
    expect(view.fraction).toBe(1)
    expect(view.passed).toBe(1)
    expect(view.dismissed).toBe(1)
  })

  it('calls an empty session complete rather than dividing by zero', () => {
    const view = buildSessionView(startSession('b', 0, [], START), lexicon)
    expect(view.phase).toBe('complete')
    expect(view.fraction).toBe(1)
  })
})
