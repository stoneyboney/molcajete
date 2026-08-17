/**
 * View model for the tap-to-gloss sheet.
 *
 * The interesting case is the missing German gloss. Wiktionary does not reach
 * SPEC §12's 95% on its own, the model half rejects lemmas it does not believe
 * are Spanish, and a Phase 1 bundle has no glosses at all — so "no gloss" is a
 * normal state, not a bug, and the sheet has to say so rather than opening
 * blank and looking broken.
 */

import type { LemmaKey, LexiconEntry } from '../types'

export interface GlossView {
  key: LemmaKey
  lemma: string
  pos: string
  /** null when the pipeline produced no German gloss for this lemma. */
  de: string | null
  en: string | null
  /** The sentence from this book that the gloss was disambiguated against. */
  example: string | null
  /** Non-null only when the entry is flagged Mexican; the two travel together. */
  regionNote: string | null
}

export function buildGlossView(
  key: LemmaKey,
  entry: LexiconEntry | undefined,
): GlossView | null {
  if (!entry) return null
  return {
    key,
    lemma: entry.lemma,
    pos: entry.pos,
    de: entry.de ?? null,
    en: entry.en ?? null,
    example: entry.example?.es ?? null,
    regionNote: entry.mexicanism ? (entry.regionNote ?? null) : null,
  }
}
