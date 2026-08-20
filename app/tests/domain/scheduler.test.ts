import { describe, expect, it } from 'vitest'
import {
  countByState,
  dueAt,
  gradeCard,
  isKnown,
  isPassingGrade,
  newCard,
  nextDue,
  type ReviewGrade,
  type SrsCard,
} from '../../src/domain/srs/scheduler'
import { fixedClock } from '../clock'

const START = new Date('2026-01-01T09:00:00Z')

describe('isPassingGrade', () => {
  it('is Gut or better, which is what ends a session', () => {
    expect(isPassingGrade('good')).toBe(true)
    expect(isPassingGrade('easy')).toBe(true)
    expect(isPassingGrade('hard')).toBe(false)
    expect(isPassingGrade('again')).toBe(false)
  })
})

describe('newCard', () => {
  it('starts unknown and due immediately', () => {
    const card = newCard('madriguera', START)
    expect(card.lemmaId).toBe('madriguera')
    expect(isKnown(card)).toBe(false)
    expect(dueAt(card).getTime()).toBe(START.getTime())
  })
})

describe('gradeCard', () => {
  it('does not mutate the card it was given', () => {
    const card = newCard('madriguera', START)
    const before = card.fsrs.state
    gradeCard(card, 'good', START)
    expect(card.fsrs.state).toBe(before)
  })

  it('schedules Leicht further out than Nochmal', () => {
    const card = newCard('madriguera', START)
    const again = gradeCard(card, 'again', START)
    const easy = gradeCard(card, 'easy', START)
    expect(dueAt(easy).getTime()).toBeGreaterThan(dueAt(again).getTime())
  })

  it('is deterministic — fuzz is off, so the same input schedules identically', () => {
    const card = newCard('madriguera', START)
    const a = gradeCard(card, 'good', START)
    const b = gradeCard(card, 'good', START)
    expect(dueAt(a).getTime()).toBe(dueAt(b).getTime())
    expect(a.fsrs.stability).toBe(b.fsrs.stability)
  })
})

/**
 * The reason `Clock` exists. SPEC §7 calls a lemma known once its card reaches
 * `Review` with stability above 21 days — a state that takes weeks of real
 * reviews to reach. Waiting is not a test, so the clock is a variable: each
 * review happens when the card asked to be reviewed, and no real time passes.
 */
describe('a card studied on schedule for three weeks', () => {
  /** Review the card exactly when it falls due, `count` times. */
  function study(lemma: string, grade: ReviewGrade, count: number): SrsCard {
    const clock = fixedClock(START)
    let card = newCard(lemma, clock.now())
    for (let i = 0; i < count; i++) {
      clock.set(dueAt(card))
      card = gradeCard(card, grade, clock.now())
    }
    return card
  }

  it('becomes known, and no wall-clock time is spent finding out', () => {
    const card = study('madriguera', 'good', 6)

    expect(isKnown(card)).toBe(true)
    expect(card.fsrs.stability).toBeGreaterThan(21)
    expect(card.fsrs.reps).toBe(6)
    expect(card.fsrs.lapses).toBe(0)

    const elapsedDays =
      (dueAt(card).getTime() - START.getTime()) / (1000 * 60 * 60 * 24)
    expect(elapsedDays).toBeGreaterThan(21)
  })

  it('never becomes known when every review is Nochmal', () => {
    const card = study('madriguera', 'again', 6)

    expect(isKnown(card)).toBe(false)
    expect(card.fsrs.stability).toBeLessThan(21)
    // It never escapes the learning steps, which is also why `lapses` stays 0:
    // FSRS counts a lapse only for a card that had reached Review and failed.
    expect(card.fsrs.state).toBe(1 /* State.Learning */)
    expect(card.fsrs.lapses).toBe(0)
  })

  it('counts a lapse once a matured card is failed', () => {
    const clock = fixedClock(START)
    let card = newCard('madriguera', clock.now())
    for (let i = 0; i < 6; i++) {
      clock.set(dueAt(card))
      card = gradeCard(card, 'good', clock.now())
    }
    expect(isKnown(card)).toBe(true)

    clock.set(dueAt(card))
    card = gradeCard(card, 'again', clock.now())

    expect(card.fsrs.lapses).toBe(1)
    expect(isKnown(card)).toBe(false)
  })

  it('is not known merely because it has been seen once', () => {
    // The distinction `teachSet.ts` depends on: having a card and being known
    // are different tests. A word graded Gut this morning is neither taught
    // again nor counted as covered.
    const clock = fixedClock(START)
    const card = gradeCard(newCard('madriguera', clock.now()), 'good', clock.now())
    expect(isKnown(card)).toBe(false)
  })

  it('honours a threshold the caller raises', () => {
    const card = study('madriguera', 'good', 6)
    expect(isKnown(card, { minStabilityDays: 21 })).toBe(true)
    expect(isKnown(card, { minStabilityDays: 3650 })).toBe(false)
  })
})

describe('countByState', () => {
  it('buckets an empty list to all zeros', () => {
    expect(countByState([])).toEqual({ new: 0, learning: 0, review: 0, relearning: 0 })
  })

  it('buckets a fresh card as learning, and a matured one as review', () => {
    const learning = gradeCard(newCard('madriguera', START), 'good', START)
    const clock = fixedClock(START)
    let review = newCard('sierra', clock.now())
    for (let i = 0; i < 6; i++) {
      clock.set(dueAt(review))
      review = gradeCard(review, 'good', clock.now())
    }

    expect(countByState([learning, review])).toEqual({
      new: 0,
      learning: 1,
      review: 1,
      relearning: 0,
    })
  })
})

describe('nextDue', () => {
  it('is undefined for an empty list', () => {
    expect(nextDue([])).toBeUndefined()
  })

  it('is the soonest due date, regardless of order', () => {
    const soon = newCard('madriguera', START)
    const later = newCard('sierra', new Date(START.getTime() + 60_000))
    expect(nextDue([later, soon])?.getTime()).toBe(dueAt(soon).getTime())
  })
})
