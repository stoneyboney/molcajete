/**
 * The teaching session, as a pure state machine. SPEC §6.3.
 *
 * ## Two phases
 *
 * **Introduction** shows every card once, front and back together — Spanish
 * word, German gloss, English beneath it, and the sentence from this book that
 * the gloss was disambiguated against. Two actions: `Weiter`, and `Ich kenne
 * das`, which SPEC calls essential because it is how you burn through the 40%
 * of words you already have. It marks the lemma known immediately and globally:
 * out of this session, and out of every future teach set in every book.
 *
 * **Recall** puts the Spanish front alone, waits for a tap, then takes one of
 * four FSRS grades. The session ends when every remaining card has been
 * answered `Gut` or better at least once.
 *
 * ## Why it returns effects instead of writing anything
 *
 * `introduce` and `grade` return `{ session, effects }`. The effects say what
 * must be persisted — a new known lemma, a graded card — and the app layer
 * commits them. Rule 3 keeps this file free of storage, and the payoff is that
 * the interrupted-session behaviour is testable without a database: a test can
 * take the session out of one step, feed it back into the next, and assert that
 * nothing was lost.
 *
 * ## The queue
 *
 * A plain round robin. `again` and `hard` send the card to the back; `good` and
 * `easy` retire it. No shuffling and no interval juggling — with at most 18
 * cards, "see it again in a moment" is all the ordering a session needs, and
 * FSRS owns the scheduling that actually matters, which is the one between
 * sessions. It is also deterministic, so no randomness has to be injected to
 * make the tests repeatable.
 *
 * ## Persistence
 *
 * `TeachingSession` is a plain data object with no methods and no class, so it
 * survives `structuredClone` into IndexedDB and comes back the same shape. The
 * caller writes it after every single answer. That is the whole interruption
 * story: a locked screen, a phone call or a killed tab resumes on the card it
 * stopped on, and a session is never restarted from the beginning.
 */

import type { LemmaId } from '../lemma'
import {
  gradeCard,
  isPassingGrade,
  newCard,
  type ReviewGrade,
  type SrsCard,
} from '../srs/scheduler'
import type { BookId, LemmaKey } from '../types'

export type SessionPhase = 'introduction' | 'recall' | 'complete'

/** What the user can do while a card is being introduced. */
export type IntroductionAction = 'weiter' | 'ichKenneDas'

export interface SessionCard {
  key: LemmaKey
  lemmaId: LemmaId
  /** Set once the card has been through the introduction phase. */
  introduced: boolean
}

export interface TeachingSession {
  bookId: BookId
  chapterIndex: number
  phase: SessionPhase
  /**
   * Introduction order first, then the recall queue, consumed from the front.
   * Cards leave when they pass or when you say you already know them.
   */
  queue: SessionCard[]
  /** Cards that have been answered `Gut` or better. Kept for the count only. */
  passed: LemmaKey[]
  /** Cards retired by `Ich kenne das`. Kept so the screen can say how many. */
  dismissed: LemmaKey[]
  /** Every card the session started with, for progress display. */
  total: number
  startedAt: Date
  updatedAt: Date
}

/**
 * Something the caller must write to storage before the next answer is taken.
 * Both variants are commits, never reads — the reducer asks for nothing back.
 */
export type SessionEffect =
  | { kind: 'markKnown'; lemmaId: LemmaId }
  | { kind: 'saveCard'; card: SrsCard }

export interface SessionStep {
  session: TeachingSession
  effects: SessionEffect[]
}

export interface SessionCardInput {
  key: LemmaKey
  lemmaId: LemmaId
}

export function startSession(
  bookId: BookId,
  chapterIndex: number,
  cards: readonly SessionCardInput[],
  now: Date,
): TeachingSession {
  const queue = cards.map((card) => ({ ...card, introduced: false }))
  return {
    bookId,
    chapterIndex,
    // A session with nothing to teach is already over. Saying so here means no
    // screen has to special-case an empty queue.
    phase: queue.length === 0 ? 'complete' : 'introduction',
    queue,
    passed: [],
    dismissed: [],
    total: queue.length,
    startedAt: now,
    updatedAt: now,
  }
}

/** The card the screen is showing, or null when the session is over. */
export function currentCard(session: TeachingSession): SessionCard | null {
  return session.queue[0] ?? null
}

export function introduce(
  session: TeachingSession,
  action: IntroductionAction,
  now: Date,
): SessionStep {
  const card = currentCard(session)
  if (session.phase !== 'introduction' || !card) {
    return { session, effects: [] }
  }

  if (action === 'ichKenneDas') {
    return {
      session: advance(session, {
        queue: session.queue.slice(1),
        dismissed: [...session.dismissed, card.key],
      }, now),
      // Immediately and globally. This is the lemma leaving every future teach
      // set in every book, not just this session.
      effects: [{ kind: 'markKnown', lemmaId: card.lemmaId }],
    }
  }

  // Introduced, so it goes to the back to be recalled once every card has been
  // seen. Introducing all of them first is what makes the recall phase a test
  // rather than a first encounter.
  const rest = session.queue.slice(1)
  const queue = [...rest, { ...card, introduced: true }]

  return { session: advance(session, { queue }, now), effects: [] }
}

export function grade(
  session: TeachingSession,
  reviewGrade: ReviewGrade,
  now: Date,
  existing?: SrsCard,
): SessionStep {
  const card = currentCard(session)
  if (session.phase !== 'recall' || !card) {
    return { session, effects: [] }
  }

  // A word can already have a card from an earlier session in another chapter
  // — the schedule continues rather than restarting.
  const before = existing ?? newCard(card.lemmaId, now)
  const after = gradeCard(before, reviewGrade, now)
  const effects: SessionEffect[] = [{ kind: 'saveCard', card: after }]

  if (isPassingGrade(reviewGrade)) {
    return {
      session: advance(
        session,
        {
          queue: session.queue.slice(1),
          passed: [...session.passed, card.key],
        },
        now,
      ),
      effects,
    }
  }

  // Nochmal or Schwer: to the back of the queue. The session cannot end while
  // it is still there, which is SPEC's "answered Gut or better at least once".
  const queue = [...session.queue.slice(1), card]
  return { session: advance(session, { queue }, now), effects }
}

/** Applies a queue change and works out which phase the session is now in. */
function advance(
  session: TeachingSession,
  change: Partial<TeachingSession>,
  now: Date,
): TeachingSession {
  const next = { ...session, ...change, updatedAt: now }
  return { ...next, phase: phaseOf(next) }
}

function phaseOf(session: TeachingSession): SessionPhase {
  if (session.queue.length === 0) return 'complete'
  // The introduction phase lasts exactly as long as there is a card that has
  // not been seen. Because introduced cards go to the back, that is always the
  // front card's own flag.
  return session.queue[0]!.introduced ? 'recall' : 'introduction'
}

export function isComplete(session: TeachingSession): boolean {
  return session.phase === 'complete'
}

/** Cards settled one way or the other, out of `total`. For the progress line. */
export function answeredCount(session: TeachingSession): number {
  return session.passed.length + session.dismissed.length
}
