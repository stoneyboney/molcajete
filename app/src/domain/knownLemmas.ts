/**
 * SPEC §7's two routes to "known", unioned in one place.
 *
 * > A lemma is considered **known** when `state == Review && stability > 21`
 * > days, or when manually marked via "Ich kenne das".
 *
 * Keeping this as a function over data rather than a method on a repository is
 * what lets `teachSet.ts` and `coverage.ts` stay pure, and what lets a test
 * build a known-set out of three lemma strings without a database.
 */

import type { LemmaId } from './lemma'
import {
  isKnown,
  type KnownThresholds,
  type SrsCard,
  DEFAULT_KNOWN_THRESHOLDS,
} from './srs/scheduler'

export interface KnownState {
  /** SPEC §7: matured cards plus hand-marked lemmas. Drives teaching and coverage. */
  known: Set<LemmaId>
  /**
   * Every lemma with a card, mature or not. A word being learned right now is
   * in here but not in `known`: it must not be taught again, and it must not
   * count towards coverage either.
   */
  carded: Set<LemmaId>
}

export function buildKnownState(
  cards: Iterable<SrsCard>,
  markedKnown: Iterable<LemmaId>,
  thresholds: KnownThresholds = DEFAULT_KNOWN_THRESHOLDS,
): KnownState {
  const known = new Set<LemmaId>(markedKnown)
  const carded = new Set<LemmaId>()

  for (const card of cards) {
    carded.add(card.lemmaId)
    if (isKnown(card, thresholds)) known.add(card.lemmaId)
  }

  return { known, carded }
}
