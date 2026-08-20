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
import type { KnownLemmaSource } from './ports/KnownLemmaRepository'
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

/**
 * How many known lemmas came from each route. Diagnostics only.
 *
 * Same traversal as `buildKnownState`, bucketed by provenance instead of
 * collapsed into one `Set`. A lemma matured via a card AND separately marked
 * known is counted once, by its stored `source` — the `knownLemmas` row is
 * what "known" actually keys off, so a matured card whose lemma has no such
 * row falls into `maturedOnly`.
 */
export interface KnownProvenance {
  seed: number
  manual: number
  /** A `knownLemmas` row from before the `source` field existed (CLAUDE.md's diagnostics note). */
  legacy: number
  /** Known only because a card matured — never marked by hand or by seed. */
  maturedOnly: number
  total: number
}

export function countKnownByProvenance(
  cards: Iterable<SrsCard>,
  knownLemmaSources: ReadonlyMap<LemmaId, KnownLemmaSource | undefined>,
  thresholds: KnownThresholds = DEFAULT_KNOWN_THRESHOLDS,
): KnownProvenance {
  const provenance: KnownProvenance = {
    seed: 0,
    manual: 0,
    legacy: 0,
    maturedOnly: 0,
    total: 0,
  }

  const known = new Set<LemmaId>(knownLemmaSources.keys())
  for (const card of cards) {
    if (isKnown(card, thresholds)) known.add(card.lemmaId)
  }

  for (const lemmaId of known) {
    const source = knownLemmaSources.get(lemmaId)
    if (source === 'seed') provenance.seed += 1
    else if (source === 'manual') provenance.manual += 1
    else if (knownLemmaSources.has(lemmaId)) provenance.legacy += 1
    else provenance.maturedOnly += 1
  }

  provenance.total = known.size
  return provenance
}
