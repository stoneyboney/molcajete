/**
 * SPEC.md Phase 6's "export mined words back to Anki as TSV."
 *
 * "Mined" = every `SrsCard` with a `face` and a German gloss. Under the
 * current design this is unambiguous: an Anki seed import never creates a
 * card — it only ever writes to `KnownLemmaRepository`, a completely
 * separate table — so the only way an `SrsCard` exists at all is that
 * Molcajete taught it, either through a session or the `Add card` button.
 * `CardRepository.listAll()` is therefore already exactly "vocabulary
 * Molcajete taught you," with no risk of re-exporting something that came
 * from Anki in the first place.
 *
 * Two fields, matching Anki's stock `Basic` note type exactly rather than
 * assuming a custom three-field one exists: `Front` is the Spanish lemma,
 * `Back` combines the German gloss and the disambiguating example sentence
 * as HTML (`#html:true` licenses this).
 *
 * The `#deck:`/`#notetype:` header values are a reasoned default, matching
 * `molcajete-prep`'s own `make_test_deck.py` convention — the closest
 * existing precedent in either repo. Nothing in either repo has ever
 * validated a hand-built TSV against Anki's actual importer, so this is
 * worth checking against a real Anki install and adjusting if the deck or
 * note type names don't match what's actually there.
 */

import type { SrsCard } from '../srs/scheduler'

const HEADER = ['#separator:tab', '#html:true', '#notetype:Basic', '#deck:Spanisch::Molcajete']

/** TSV fields can't contain a literal tab or newline. Prose (example sentences) can have both. */
function escapeField(value: string): string {
  return value.replace(/\t/g, ' ').replace(/\r?\n/g, ' ')
}

export function buildAnkiExport(cards: readonly SrsCard[]): string {
  const lines = [...HEADER]

  for (const card of cards) {
    const face = card.face
    if (!face || !face.de) continue

    const back = face.example ? `${face.de}<br><i>${face.example}</i>` : face.de
    lines.push(`${escapeField(card.lemmaId)}\t${escapeField(back)}`)
  }

  return lines.join('\n') + '\n'
}
