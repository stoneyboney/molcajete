import type { SessionCardView } from '../domain/view/sessionView'

/**
 * The face of a card. Shared by both phases so that a word looks the same when
 * it is introduced and when it is recalled — the recall phase simply withholds
 * this half until you tap.
 *
 * SPEC §13.1 and CLAUDE.md's settled decisions: German large and primary,
 * English small beneath it.
 */
export function CardAnswer({ view }: { view: SessionCardView }) {
  return (
    <div className="mt-6">
      {view.de ? (
        <p className="text-2xl leading-snug" lang="de">
          {view.de}
        </p>
      ) : (
        <p className="text-ink-muted text-base">
          Keine deutsche Übersetzung im Bundle.
        </p>
      )}

      {view.en && (
        <p className="text-ink-muted mt-1.5 text-sm" lang="en">
          {view.en}
        </p>
      )}

      {view.example && (
        <p
          className="text-ink-muted border-rule font-serif mt-6 border-l-2 pl-3 text-base italic"
          lang="es"
        >
          {view.example}
        </p>
      )}
    </div>
  )
}

/** The Spanish word, its part of speech, and any regional note. */
export function CardFront({ view }: { view: SessionCardView }) {
  return (
    <div>
      <div className="flex items-baseline justify-center gap-3">
        <h2 className="font-serif text-4xl" lang="es">
          {view.lemma}
        </h2>
        <span className="text-ink-faint text-xs tracking-wide uppercase">
          {view.pos}
        </span>
      </div>

      {view.regionNote && (
        <p
          className={`mt-2 text-center text-xs ${
            view.mexicanism ? 'text-accent' : 'text-ink-faint'
          }`}
        >
          {view.regionNote}
        </p>
      )}
    </div>
  )
}
