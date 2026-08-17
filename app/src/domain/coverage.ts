/**
 * SPEC §5 Step 4, and §13.2's insistence that it is a diagnostic and not a gate.
 *
 * ## What the denominator is
 *
 * §5 writes `coverage = known tokens / totalTokens`, which read literally would
 * put whitespace and punctuation in the denominator — a third of every chapter,
 * all of it trivially "covered", inflating every figure by roughly 30 points and
 * making the 0.90 warning threshold meaningless.
 *
 * The denominator is word tokens: the ones carrying a lemma. That number is
 * already in the bundle. Measured across every chapter of both bundles in
 * `bundles/`, `chapter.tokenCount` is *exactly* the count of tokens with an `l`
 * field, and it partitions cleanly:
 *
 *     tokenCount = tokens with a lexicon key + PROPN tokens
 *     32257      = 31654                     + 603          (las-noches ch0)
 *
 * so nothing new has to be stored to know it, and it is the same number the
 * chapter list already prints as "N Wörter".
 *
 * ## Why proper nouns count as covered
 *
 * §5 skips `PROPN` entirely — no card, no gloss — which is the pipeline
 * asserting that a name needs no teaching. Counting those same tokens as
 * unknown would then penalise a chapter for a decision the pipeline already
 * made, and a book heavy with place names would look unreadable for a reason
 * that has nothing to do with vocabulary.
 *
 * ## Splitting counting from computing
 *
 * `countChapterVocabulary` needs paragraphs; `computeCoverage` does not. That
 * split is what lets the chapter list show a figure for five chapters without
 * deserialising 11 MB — counts are derived once at import and cached, and the
 * coverage arithmetic afterwards is a walk over a few thousand integers.
 */

import { lemmaId, type LemmaId } from './lemma'
import type { Chapter, LemmaKey, LexiconEntry } from './types'

/** Everything about a chapter's vocabulary that does not need its paragraphs. */
export interface ChapterVocabulary {
  /** Occurrences per lexicon key. Proper nouns are absent — they have no key. */
  counts: Map<LemmaKey, number>
  /** Tokens skipped by §5 as names. Covered without ever being taught. */
  propnTokens: number
  /** Word tokens in total. The coverage denominator. */
  tokenCount: number
}

export function countChapterVocabulary(chapter: Chapter): ChapterVocabulary {
  const counts = new Map<LemmaKey, number>()
  let propnTokens = 0
  let tokenCount = 0

  for (const paragraph of chapter.paragraphs) {
    for (const token of paragraph.tokens) {
      if (token.ws === true) continue
      // A lemma is what makes a token a word. Punctuation and numerals carry a
      // POS but no lemma, and they are not vocabulary.
      if (token.l === undefined) continue

      tokenCount++
      if (token.t === undefined) {
        // No lexicon key, but it has a lemma: §5 skipped it as a proper noun.
        propnTokens++
        continue
      }
      counts.set(token.t, (counts.get(token.t) ?? 0) + 1)
    }
  }

  return { counts, propnTokens, tokenCount }
}

/**
 * The share of this chapter's words you can read without a gloss, 0..1.
 *
 * `justTaught` is §5 Step 4's "known ∪ justTaught": the lemmas a pending session
 * would teach, so the chapter list can answer "what will this be like *after* I
 * study?" rather than only "what is it like now".
 */
export function computeCoverage(
  vocabulary: ChapterVocabulary,
  lexicon: ReadonlyMap<LemmaKey, LexiconEntry>,
  known: ReadonlySet<LemmaId>,
  justTaught: ReadonlySet<LemmaId> = new Set(),
): number {
  if (vocabulary.tokenCount === 0) return 1

  let covered = vocabulary.propnTokens

  for (const [key, count] of vocabulary.counts) {
    const entry = lexicon.get(key)
    if (!entry) continue
    const id = lemmaId(entry)
    if (known.has(id) || justTaught.has(id)) covered += count
  }

  return covered / vocabulary.tokenCount
}

/** SPEC §13.2: warn below 0.90, never block. */
export const COVERAGE_WARNING_THRESHOLD = 0.9
