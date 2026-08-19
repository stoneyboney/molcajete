/**
 * The other file the import button accepts: SPEC §8's `known.json`.
 *
 * A flat array of lemma strings, which is the shape `seed_known.py` writes and
 * the shape `pipeline/molcajete_prep/cli.py` already reads. Three consumers
 * agreeing on "an array of strings" is the reason it is not something richer.
 *
 * Validated for the same reason a bundle is: the file arrives by AirDrop from
 * whatever version of the pipeline that desktop happens to be running, and a
 * half-valid seed is worse than none — a lemma wrongly marked known is never
 * taught *and* counts as covered, so the app would quietly skip words the
 * reader actually needs.
 */

import { normalizeLemma, type LemmaId } from '../lemma'

export class KnownFormatError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'KnownFormatError'
  }
}

/**
 * Parse an already-decoded JSON value into lemma ids.
 *
 * Duplicates and casing are the seed's business, not the caller's: the array is
 * normalised and deduplicated here, so importing the same file twice is a no-op
 * rather than a growing store.
 */
export function parseKnownLemmas(value: unknown): LemmaId[] {
  if (!Array.isArray(value)) {
    throw new KnownFormatError('expected a flat array of lemma strings')
  }

  const lemmas = new Set<LemmaId>()
  value.forEach((entry, index) => {
    if (typeof entry !== 'string') {
      throw new KnownFormatError(
        `[${index}]: expected a string, got ${entry === null ? 'null' : typeof entry}`,
      )
    }
    const lemma = normalizeLemma(entry)
    // An empty string would match no lexicon entry and silently bloat the
    // store; a seed that contains one is malformed rather than merely odd.
    if (lemma) lemmas.add(lemma)
  })

  if (lemmas.size === 0) {
    throw new KnownFormatError('the file contained no lemmas')
  }

  return [...lemmas].sort()
}
