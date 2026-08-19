/**
 * The cross-book daily review. SPEC §6.5.
 *
 * > Daily due cards across all books. Same FSRS interface as the recall phase.
 * > This screen is what makes it a real SRS rather than a cramming tool.
 *
 * ## Why this is not `session/session.ts`
 *
 * A teaching session is chapter-scoped, has an introduction phase, and exists
 * to get a specific chapter readable. A review is none of those: the cards come
 * from every book, every one of them has been seen before — so there is nothing
 * to introduce — and it ends when the day's due list is empty rather than when
 * some chapter is ready.
 *
 * What they share is the part that matters, and they share it by calling it
 * rather than by copying it: `gradeCard` and `isPassingGrade` from
 * `srs/scheduler.ts`, and the same four buttons on screen.
 *
 * ## The queue
 *
 * Same deterministic round robin as a teaching session: `again` and `hard` send
 * the card to the back, `good` and `easy` retire it for the day. FSRS has
 * already decided *when* each card should come back; this only decides what
 * happens within the sitting.
 *
 * ## No persistence
 *
 * Deliberately, and unlike a teaching session. Every answer writes the card
 * itself, which is the durable part — an interrupted review resumes simply by
 * asking what is still due, because a card graded `Gut` is no longer due and a
 * card graded `Nochmal` is. There is no session state worth keeping, so there
 * is none to lose.
 */

import type { LemmaId } from '../lemma'
import {
  gradeCard,
  isPassingGrade,
  type ReviewGrade,
  type SrsCard,
} from '../srs/scheduler'

export interface ReviewSession {
  /** Consumed from the front; a failed card goes to the back. */
  queue: SrsCard[]
  /** Lemmas answered `Gut` or better this sitting. */
  passed: LemmaId[]
  /** How many cards the sitting started with. */
  total: number
  startedAt: Date
  updatedAt: Date
}

export interface ReviewStep {
  session: ReviewSession
  /** The card to persist. Always exactly one; a review is nothing but grading. */
  card: SrsCard | null
}

export function startReview(due: readonly SrsCard[], now: Date): ReviewSession {
  return {
    queue: [...due],
    passed: [],
    total: due.length,
    startedAt: now,
    updatedAt: now,
  }
}

export function currentCard(session: ReviewSession): SrsCard | null {
  return session.queue[0] ?? null
}

export function isComplete(session: ReviewSession): boolean {
  return session.queue.length === 0
}

/** Settled cards out of `total`. Note a failed card is not settled yet. */
export function answeredCount(session: ReviewSession): number {
  return session.passed.length
}

export function grade(
  session: ReviewSession,
  reviewGrade: ReviewGrade,
  now: Date,
): ReviewStep {
  const card = currentCard(session)
  if (!card) return { session, card: null }

  const graded = gradeCard(card, reviewGrade, now)

  if (isPassingGrade(reviewGrade)) {
    return {
      session: {
        ...session,
        queue: session.queue.slice(1),
        passed: [...session.passed, card.lemmaId],
        updatedAt: now,
      },
      card: graded,
    }
  }

  // Back of the queue, carrying its new schedule: the sitting is not over until
  // every card has been answered `Gut` or better, exactly as in a teaching
  // session.
  return {
    session: {
      ...session,
      queue: [...session.queue.slice(1), graded],
      updatedAt: now,
    },
    card: graded,
  }
}
