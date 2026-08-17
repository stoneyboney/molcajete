import { useEffect } from 'react'
import type { GlossView } from '../domain/view/glossView'

/**
 * Tap-to-reveal, and nothing else. No inline translation anywhere in the
 * reader (SPEC §13 decision 3), and no `Add card` button — cards arrive in
 * Phase 4 with the scheduler that would have to hold them.
 */
export function GlossSheet({
  view,
  onDismiss,
}: {
  view: GlossView
  onDismiss: () => void
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onDismiss()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onDismiss])

  return (
    // Above the progress bar: the scrim covers the page, and a bright line
    // floating over it reads as a rendering fault rather than as progress.
    <div className="fixed inset-0 z-40 flex flex-col justify-end">
      <button
        type="button"
        aria-label="Schließen"
        className="absolute inset-0 h-full w-full"
        style={{ background: 'var(--scrim)' }}
        onClick={onDismiss}
      />

      <div
        role="dialog"
        aria-modal="true"
        aria-label={view.lemma}
        className="bg-paper-raised border-rule relative mx-auto w-full max-w-2xl rounded-t-2xl border-t px-6 pt-5"
        style={{ paddingBottom: 'calc(1.5rem + env(safe-area-inset-bottom))' }}
      >
        <div className="bg-rule mx-auto mb-4 h-1 w-10 rounded-full" />

        <div className="flex items-baseline gap-3">
          <h2 className="font-serif text-2xl" lang="es">
            {view.lemma}
          </h2>
          <span className="text-ink-faint text-xs tracking-wide uppercase">
            {view.pos}
          </span>
        </div>

        {view.regionNote && (
          <p
            className={`mt-1 text-xs ${
              view.mexicanism ? 'text-accent' : 'text-ink-faint'
            }`}
          >
            {view.regionNote}
          </p>
        )}

        {view.de ? (
          <p className="mt-4 text-xl leading-snug" lang="de">
            {view.de}
          </p>
        ) : (
          <p className="text-ink-muted mt-4 text-sm">
            Keine deutsche Übersetzung im Bundle.
          </p>
        )}

        {view.en && (
          <p className="text-ink-muted mt-1 text-sm" lang="en">
            {view.en}
          </p>
        )}

        {view.example && (
          <p
            className="text-ink-muted border-rule font-serif mt-5 border-l-2 pl-3 text-base italic"
            lang="es"
          >
            {view.example}
          </p>
        )}
      </div>
    </div>
  )
}
