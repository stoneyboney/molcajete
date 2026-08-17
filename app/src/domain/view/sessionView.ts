/**
 * View model for the teaching session (SPEC §6.3).
 *
 * Rule 5: the screen renders this and works nothing out for itself. In
 * particular it does not decide which phase it is in, whether the answer is
 * showing, or what the progress numbers are — all of that is here, so that
 * porting the screen to SwiftUI is a rebuild of the layout and nothing more.
 *
 * No German in this file. `src/ui/format.ts` owns the copy so the domain layer
 * stays language-neutral for the port.
 */

import type { LemmaKey, LexiconEntry } from '../types'
import {
  answeredCount,
  currentCard,
  type SessionPhase,
  type TeachingSession,
} from '../session/session'

export interface SessionCardView {
  key: LemmaKey
  /** The Spanish word. The front of the card in both phases. */
  lemma: string
  pos: string
  /** German, large and primary. Null when the pipeline produced no gloss. */
  de: string | null
  /** English, small and beneath. */
  en: string | null
  /** The sentence from this book the gloss was disambiguated against. */
  example: string | null
  regionNote: string | null
  mexicanism: boolean
}

export interface SessionView {
  phase: SessionPhase
  /** Null exactly when the session is complete. */
  card: SessionCardView | null
  /** Cards settled one way or another. */
  answered: number
  total: number
  /** 0..1, for the progress bar. */
  fraction: number
  /** How many "Ich kenne das" retired. The end screen reports it. */
  dismissed: number
  passed: number
}

export function buildSessionView(
  session: TeachingSession,
  lexicon: ReadonlyMap<LemmaKey, LexiconEntry>,
): SessionView {
  const card = currentCard(session)
  const answered = answeredCount(session)

  return {
    phase: session.phase,
    card: card ? buildSessionCardView(card.key, lexicon.get(card.key)) : null,
    answered,
    total: session.total,
    fraction: session.total === 0 ? 1 : answered / session.total,
    dismissed: session.dismissed.length,
    passed: session.passed.length,
  }
}

/**
 * A missing entry yields a card showing the key and no gloss rather than
 * nothing at all. It means a partial import; the reader already degrades the
 * same way rather than refusing to render.
 */
export function buildSessionCardView(
  key: LemmaKey,
  entry: LexiconEntry | undefined,
): SessionCardView {
  if (!entry) {
    return {
      key,
      lemma: key,
      pos: '',
      de: null,
      en: null,
      example: null,
      regionNote: null,
      mexicanism: false,
    }
  }

  return {
    key,
    lemma: entry.lemma,
    pos: entry.pos,
    de: entry.de ?? null,
    en: entry.en ?? null,
    example: entry.example?.es ?? null,
    regionNote: entry.regionNote ?? null,
    mexicanism: entry.mexicanism,
  }
}
