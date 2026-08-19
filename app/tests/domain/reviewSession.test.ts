import { describe, expect, it } from 'vitest'
import {
  answeredCount,
  currentCard,
  grade,
  isComplete,
  startReview,
} from '../../src/domain/review/reviewSession'
import {
  dueAt,
  gradeCard,
  isDue,
  newCard,
  type CardFace,
  type SrsCard,
} from '../../src/domain/srs/scheduler'
import { buildReviewView } from '../../src/domain/view/reviewView'
import { fixedClock } from '../clock'

const START = new Date('2026-01-01T09:00:00Z')

const face: CardFace = {
  pos: 'NOUN',
  de: 'die Hütte',
  en: 'hut, shack',
  example: 'La puerta del jacal estaba abierta.',
  regionNote: 'MX, ländlich',
  mexicanism: true,
}

function card(lemmaId: string, withFace = true): SrsCard {
  return newCard(lemmaId, START, withFace ? face : undefined)
}

const due = [card('jacal'), card('sierra'), card('fusil')]

describe('isDue', () => {
  it('is true for a new card and false once it is scheduled ahead', () => {
    const fresh = card('jacal')
    expect(isDue(fresh, START)).toBe(true)

    const graded = gradeCard(fresh, 'good', START)
    expect(isDue(graded, START)).toBe(false)
    expect(isDue(graded, dueAt(graded))).toBe(true)
  })
})

describe('a review sitting', () => {
  it('starts on the first due card with nothing answered', () => {
    const session = startReview(due, START)

    expect(currentCard(session)?.lemmaId).toBe('jacal')
    expect(session.total).toBe(3)
    expect(answeredCount(session)).toBe(0)
  })

  it('has no introduction phase — every card here has been seen', () => {
    // The whole reason this is not `session/session.ts`.
    const session = startReview(due, START)
    const { card: graded } = grade(session, 'good', START)

    expect(graded).not.toBeNull()
  })

  it('retires a card answered Gut and returns it for persisting', () => {
    const { session, card: graded } = grade(startReview(due, START), 'good', START)

    expect(session.passed).toEqual(['jacal'])
    expect(session.queue.map((c) => c.lemmaId)).toEqual(['sierra', 'fusil'])
    expect(graded?.lemmaId).toBe('jacal')
    expect(isDue(graded!, START)).toBe(false)
  })

  it('sends a card answered Nochmal to the back, carrying its new schedule', () => {
    const { session, card: graded } = grade(startReview(due, START), 'again', START)

    expect(session.passed).toEqual([])
    expect(session.queue.map((c) => c.lemmaId)).toEqual(['sierra', 'fusil', 'jacal'])
    // The requeued card is the graded one, not the original: a lapse is
    // information FSRS needs and must not be thrown away by the round robin.
    expect(session.queue[2]!.fsrs.reps).toBe(graded!.fsrs.reps)
  })

  it('does not end while a card is still unpassed', () => {
    let session = startReview(due, START)
    session = grade(session, 'good', START).session
    session = grade(session, 'good', START).session
    session = grade(session, 'again', START).session

    expect(isComplete(session)).toBe(false)
    expect(currentCard(session)?.lemmaId).toBe('fusil')

    session = grade(session, 'good', START).session
    expect(isComplete(session)).toBe(true)
    expect(session.passed).toEqual(['jacal', 'sierra', 'fusil'])
  })

  it('is complete from the start when nothing is due', () => {
    const session = startReview([], START)

    expect(isComplete(session)).toBe(true)
    expect(currentCard(session)).toBeNull()
  })

  it('does not mutate the session it was given', () => {
    const session = startReview(due, START)
    const before = session.queue.map((c) => c.lemmaId)
    grade(session, 'good', START)

    expect(session.queue.map((c) => c.lemmaId)).toEqual(before)
  })
})

describe('an interrupted review', () => {
  it('resumes from what is still due, with no session state to lose', () => {
    // Unlike a teaching session there is nothing persisted but the cards. A
    // card graded Gut is no longer due; one graded Nochmal still is.
    const clock = fixedClock(START)
    let session = startReview(due, clock.now())

    const passed = grade(session, 'good', clock.now())
    session = passed.session
    const failed = grade(session, 'again', clock.now())

    const stored = [failed.card!, passed.card!, card('fusil')]

    // Nothing is due at the very instant it was answered: FSRS puts even a
    // failed card a learning step into the future rather than immediately.
    expect(stored.filter((c) => isDue(c, clock.now())).map((c) => c.lemmaId))
      .toEqual(['fusil'])

    // Five minutes later the failed card is back and the passed one is not,
    // which is the whole of "resume from what is still due".
    //
    // Five, specifically. These are first exposures, so FSRS is still walking
    // its learning steps and the intervals are minutes rather than days:
    // Nochmal 1m, Schwer 6m, Gut 10m, Leicht 8 days. A card answered Gut
    // today is genuinely due again this morning — that is the learning phase
    // working, not the review screen leaking.
    clock.advanceDays(5 / (24 * 60))
    const later = stored.filter((c) => isDue(c, clock.now())).map((c) => c.lemmaId)

    expect(later.sort()).toEqual(['fusil', 'sierra'])
    expect(later).not.toContain('jacal')
  })
})

describe('the view model', () => {
  it('renders the face carried on the card', () => {
    const view = buildReviewView(startReview(due, START))

    expect(view.card?.lemma).toBe('jacal')
    expect(view.card?.de).toBe('die Hütte')
    expect(view.card?.example).toBe('La puerta del jacal estaba abierta.')
    expect(view.card?.mexicanism).toBe(true)
  })

  it('falls back to the lemma alone for a card made before faces existed', () => {
    // Phase 4 cards have no face. Showing the Spanish with no answer is a poor
    // card and a better outcome than a blank screen.
    const view = buildReviewView(startReview([card('jacal', false)], START))

    expect(view.card?.lemma).toBe('jacal')
    expect(view.card?.de).toBeNull()
    expect(view.card?.example).toBeNull()
  })

  it('advances the progress fraction as cards are passed', () => {
    let session = startReview(due, START)
    session = grade(session, 'good', START).session

    const view = buildReviewView(session)
    expect(view.answered).toBe(1)
    expect(view.fraction).toBeCloseTo(1 / 3)
    expect(view.remaining).toBe(2)
  })

  it('reports an empty day as done rather than as a card', () => {
    const view = buildReviewView(startReview([], START))

    expect(view.done).toBe(true)
    expect(view.card).toBeNull()
    expect(view.fraction).toBe(1)
  })
})
