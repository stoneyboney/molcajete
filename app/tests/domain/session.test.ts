import { describe, expect, it } from 'vitest'
import {
  answeredCount,
  currentCard,
  grade,
  introduce,
  isComplete,
  startSession,
  type SessionCardInput,
  type SessionEffect,
  type TeachingSession,
} from '../../src/domain/session/session'
import { isKnown, type ReviewGrade, type SrsCard } from '../../src/domain/srs/scheduler'
import { fixedClock } from '../clock'

const START = new Date('2026-01-01T09:00:00Z')

const cards: SessionCardInput[] = [
  { key: 'm1', lemmaId: 'jacal' },
  { key: 'm2', lemmaId: 'sierra' },
  { key: 'm3', lemmaId: 'fusil' },
]

function session(input: SessionCardInput[] = cards): TeachingSession {
  return startSession('anonimo-los-del-cerro', 0, input, START)
}

/** Walk the introduction phase, answering `Weiter` to everything. */
function introduceAll(start: TeachingSession): TeachingSession {
  let current = start
  while (current.phase === 'introduction') {
    current = introduce(current, 'weiter', START).session
  }
  return current
}

describe('starting a session', () => {
  it('begins in the introduction phase on the first card', () => {
    const s = session()
    expect(s.phase).toBe('introduction')
    expect(currentCard(s)?.key).toBe('m1')
    expect(s.total).toBe(3)
    expect(answeredCount(s)).toBe(0)
  })

  it('is already complete when there is nothing to teach', () => {
    // So that no screen has to special-case an empty queue.
    const s = session([])
    expect(isComplete(s)).toBe(true)
    expect(currentCard(s)).toBeNull()
  })
})

describe('the introduction phase', () => {
  it('shows every card once before any recall begins', () => {
    let s = session()
    expect(introduce(s, 'weiter', START).session.phase).toBe('introduction')

    s = introduce(s, 'weiter', START).session
    expect(currentCard(s)?.key).toBe('m2')
    s = introduce(s, 'weiter', START).session
    expect(currentCard(s)?.key).toBe('m3')

    s = introduce(s, 'weiter', START).session
    expect(s.phase).toBe('recall')
    expect(currentCard(s)?.key).toBe('m1')
  })

  it('"Ich kenne das" removes the card and marks the lemma known', () => {
    const { session: s, effects } = introduce(session(), 'ichKenneDas', START)

    expect(effects).toEqual<SessionEffect[]>([
      { kind: 'markKnown', lemmaId: 'jacal' },
    ])
    expect(s.queue.map((c) => c.key)).toEqual(['m2', 'm3'])
    expect(s.dismissed).toEqual(['m1'])
    expect(answeredCount(s)).toBe(1)
  })

  it('never brings a dismissed card back', () => {
    let s = introduce(session(), 'ichKenneDas', START).session
    s = introduceAll(s)
    while (!isComplete(s)) {
      s = grade(s, 'good', START).session
    }
    expect(s.passed).not.toContain('m1')
    expect(s.dismissed).toEqual(['m1'])
  })

  it('writes no card for a dismissed lemma', () => {
    // "Ich kenne das" is not a review. It should not create a schedule.
    const { effects } = introduce(session(), 'ichKenneDas', START)
    expect(effects.some((e) => e.kind === 'saveCard')).toBe(false)
  })

  it('completes a session where every word is already known', () => {
    let s = session()
    for (let i = 0; i < 3; i++) s = introduce(s, 'ichKenneDas', START).session
    expect(isComplete(s)).toBe(true)
    expect(s.dismissed).toEqual(['m1', 'm2', 'm3'])
  })
})

describe('the recall phase', () => {
  it('retires a card answered Gut', () => {
    const s = introduceAll(session())
    const { session: after, effects } = grade(s, 'good', START)

    expect(after.passed).toEqual(['m1'])
    expect(after.queue.map((c) => c.key)).toEqual(['m2', 'm3'])
    expect(effects).toHaveLength(1)
    expect(effects[0]!.kind).toBe('saveCard')
  })

  it('sends a card answered Nochmal to the back', () => {
    const s = introduceAll(session())
    const after = grade(s, 'again', START).session

    expect(after.passed).toEqual([])
    expect(after.queue.map((c) => c.key)).toEqual(['m2', 'm3', 'm1'])
    expect(after.phase).toBe('recall')
  })

  it('sends a card answered Schwer to the back too', () => {
    const s = introduceAll(session())
    const after = grade(s, 'hard', START).session
    expect(after.queue.map((c) => c.key)).toEqual(['m2', 'm3', 'm1'])
  })

  it('does not end while a card is still unpassed', () => {
    let s = introduceAll(session())
    s = grade(s, 'good', START).session
    s = grade(s, 'good', START).session
    s = grade(s, 'again', START).session

    expect(isComplete(s)).toBe(false)
    expect(currentCard(s)?.key).toBe('m3')

    s = grade(s, 'good', START).session
    expect(isComplete(s)).toBe(true)
    expect(s.passed).toEqual(['m1', 'm2', 'm3'])
  })

  it('saves a card on every grade, including the failures', () => {
    // A lapse is information FSRS needs. Dropping it would make the schedule
    // wrong for the card, not merely delayed.
    let s = introduceAll(session())
    const grades: ReviewGrade[] = ['again', 'good', 'good', 'good']
    const saved: SrsCard[] = []
    for (const g of grades) {
      const step = grade(s, g, START)
      s = step.session
      for (const effect of step.effects) {
        if (effect.kind === 'saveCard') saved.push(effect.card)
      }
    }
    expect(saved).toHaveLength(4)
    expect(saved.filter((c) => c.lemmaId === 'jacal')).toHaveLength(2)
  })

  it('continues an existing schedule rather than restarting it', () => {
    // The word has a card from an earlier chapter. Grading it must advance
    // that card, not replace it with a fresh one.
    const clock = fixedClock(START)
    // A card built by an earlier session, through the real scheduler.
    const built = grade(introduceAll(session()), 'good', clock.now())
    const existing = (built.effects[0] as { card: SrsCard }).card

    clock.advanceDays(30)
    const s = introduceAll(session())
    const { effects } = grade(s, 'good', clock.now(), existing)
    const next = (effects[0] as { card: SrsCard }).card

    expect(next.lemmaId).toBe('jacal')
    expect(next.fsrs.reps).toBe(existing.fsrs.reps + 1)
    expect(next.createdAt).toEqual(existing.createdAt)
  })
})

describe('an interrupted session', () => {
  it('resumes on the card it stopped on', () => {
    // The whole point of persisting after every answer. `TeachingSession` is
    // plain data, so a round trip through storage is a round trip through JSON.
    let s = introduceAll(session())
    s = grade(s, 'good', START).session
    s = grade(s, 'again', START).session

    const stored = JSON.parse(JSON.stringify(s)) as TeachingSession
    const resumed: TeachingSession = {
      ...stored,
      startedAt: new Date(stored.startedAt),
      updatedAt: new Date(stored.updatedAt),
    }

    expect(resumed.phase).toBe('recall')
    expect(currentCard(resumed)?.key).toBe(currentCard(s)?.key)
    expect(resumed.passed).toEqual(['m1'])
    expect(resumed.queue.map((c) => c.key)).toEqual(['m3', 'm2'])

    // And it finishes from there rather than starting over.
    let finished = resumed
    while (!isComplete(finished)) {
      finished = grade(finished, 'good', START).session
    }
    expect(finished.passed).toEqual(['m1', 'm3', 'm2'])
  })

  it('never restarts from the beginning mid-introduction', () => {
    let s = introduce(session(), 'weiter', START).session
    s = introduce(s, 'ichKenneDas', START).session

    const resumed = JSON.parse(JSON.stringify(s)) as TeachingSession
    expect(resumed.phase).toBe('introduction')
    expect(currentCard(resumed)?.key).toBe('m3')
    expect(resumed.dismissed).toEqual(['m2'])
  })
})

describe('the reducer', () => {
  it('does not mutate the session it was given', () => {
    const s = session()
    const before = JSON.stringify(s)
    introduce(s, 'weiter', START)
    grade(introduceAll(s), 'good', START)
    expect(JSON.stringify(s)).toBe(before)
  })

  it('ignores a grade during the introduction phase', () => {
    const s = session()
    const { session: after, effects } = grade(s, 'good', START)
    expect(after).toBe(s)
    expect(effects).toEqual([])
  })

  it('ignores an introduction action once recall has started', () => {
    const s = introduceAll(session())
    const { session: after, effects } = introduce(s, 'ichKenneDas', START)
    expect(after).toBe(s)
    expect(effects).toEqual([])
  })

  it('moves updatedAt forward so the store can see progress', () => {
    const clock = fixedClock(START)
    const s = session()
    clock.advanceDays(1)
    const after = introduce(s, 'weiter', clock.now()).session
    expect(after.updatedAt.getTime()).toBeGreaterThan(s.updatedAt.getTime())
  })
})

describe('a session finished today', () => {
  it('leaves cards that are scheduled but not yet known', () => {
    // The distinction teachSet.ts depends on: after one session the words have
    // cards, so they are not taught again, but they are not known either, so
    // they do not count towards coverage.
    let s = introduceAll(session())
    const saved = new Map<string, SrsCard>()
    while (!isComplete(s)) {
      const step = grade(s, 'good', START)
      s = step.session
      for (const effect of step.effects) {
        if (effect.kind === 'saveCard') saved.set(effect.card.lemmaId, effect.card)
      }
    }

    expect(saved.size).toBe(3)
    for (const card of saved.values()) {
      expect(isKnown(card)).toBe(false)
    }
  })
})
