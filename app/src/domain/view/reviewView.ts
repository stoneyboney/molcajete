/**
 * View model for the review screen. Rule 5: the screen computes nothing.
 *
 * The card face comes off the card, not out of a book — see `CardFace`. A
 * lemma due today may have been learned in a book that has since been deleted,
 * and the review screen has to render it anyway.
 */

import type { CardFace, SrsCard } from '../srs/scheduler'
import type { SessionCardView } from './sessionView'
import {
  answeredCount,
  currentCard,
  isComplete,
  type ReviewSession,
} from '../review/reviewSession'

export interface ReviewView {
  /** Null exactly when the sitting is over. */
  card: SessionCardView | null
  done: boolean
  answered: number
  total: number
  /** 0..1, for the progress bar. */
  fraction: number
  /** Still in the queue, including cards sent to the back. */
  remaining: number
}

/**
 * Cards created before `CardFace` existed have none. Showing the Spanish with
 * no answer is a poor card but a better outcome than a blank screen, and it
 * self-heals: grading it does not restore the gloss, but re-teaching the word
 * in any book will.
 */
function faceOf(card: SrsCard): CardFace {
  return (
    card.face ?? {
      pos: '',
      de: null,
      en: null,
      example: null,
      regionNote: null,
      mexicanism: false,
    }
  )
}

export function buildReviewCardView(card: SrsCard): SessionCardView {
  const face = faceOf(card)
  return {
    key: card.lemmaId,
    lemma: card.lemmaId,
    pos: face.pos,
    de: face.de,
    en: face.en,
    example: face.example,
    regionNote: face.regionNote,
    mexicanism: face.mexicanism,
  }
}

export function buildReviewView(session: ReviewSession): ReviewView {
  const card = currentCard(session)
  const answered = answeredCount(session)

  return {
    card: card ? buildReviewCardView(card) : null,
    done: isComplete(session),
    answered,
    total: session.total,
    fraction: session.total === 0 ? 1 : answered / session.total,
    remaining: session.queue.length,
  }
}
