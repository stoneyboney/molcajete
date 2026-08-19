import { useCallback, useState } from 'react'
import { importFile, type ImportOutcome } from '../app/importFile'
import { useRepositories } from '../app/repositories'
import { navigate } from '../app/useRoute'
import { useAsync } from '../app/useAsync'
import { buildLibraryView, type LibraryView } from '../domain/view/libraryView'
import {
  chapters,
  dueCards,
  describeImportFailure,
  describeImportSuccess,
  lemmas,
  words,
} from './format'
import { ImportButton } from './ImportButton'
import { Screen } from './Screen'

export function Library() {
  const { books, known, cards, clock } = useRepositories()
  const [reloads, setReloads] = useState(0)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<{
    headline: string
    detail: string
  } | null>(null)
  const [done, setDone] = useState<string | null>(null)

  const state = useAsync<LibraryView>(
    async () => buildLibraryView(await books.listBooks()),
    [books, reloads],
  )

  // SPEC §6.5. No chip when nothing is due — the app does not nag, and a zero
  // is not a thing worth drawing.
  const due = useAsync(() => cards.countDue(clock.now()), [cards, clock, reloads])

  const onFile = useCallback(
    async (file: File) => {
      setBusy(true)
      setFailure(null)
      setDone(null)
      try {
        const outcome: ImportOutcome = await importFile(file, { books, known })
        setDone(describeImportSuccess(outcome))
        // A seed changes no book row, but it changes every teach set behind
        // them, so the reload matters either way.
        setReloads((n) => n + 1)
      } catch (error) {
        setFailure(describeImportFailure(error))
      } finally {
        setBusy(false)
      }
    },
    [books, known],
  )

  const remove = useCallback(
    async (id: string, title: string) => {
      if (!window.confirm(`„${title}“ entfernen?`)) return
      await books.deleteBook(id)
      setReloads((n) => n + 1)
    },
    [books],
  )

  return (
    <Screen
      title="Molcajete"
      action={
        <ImportButton onFile={onFile} busy={busy} label="Buch importieren" />
      }
    >
      {due.status === 'ready' && dueCards(due.value) && (
        <button
          type="button"
          onClick={() => navigate({ name: 'review' })}
          className="border-rule mb-6 flex w-full items-center justify-between rounded-lg border px-4 py-3 text-left"
        >
          <span className="text-sm">{dueCards(due.value)}</span>
          <span className="text-accent text-sm">Wiederholen ›</span>
        </button>
      )}

      {done && (
        <p className="border-rule text-ink-muted mb-6 rounded-lg border border-dashed px-4 py-3 text-sm">
          {done}
        </p>
      )}

      {failure && (
        <div className="border-accent/40 bg-accent/5 mb-6 rounded-lg border px-4 py-3">
          <p className="text-sm">{failure.headline}</p>
          <p className="text-ink-muted mt-1 font-mono text-xs break-words">
            {failure.detail}
          </p>
        </div>
      )}

      {state.status === 'ready' && state.value.isEmpty && (
        <div className="text-ink-muted mt-16 text-center text-sm leading-relaxed text-balance">
          <p className="text-ink font-serif text-lg">Noch kein Buch da.</p>
          <p className="mt-2">
            Bundles entstehen auf dem Rechner und kommen per AirDrop hierher.
            Importieren, dann offline lesen.
          </p>
          <p className="mt-4">
            Derselbe Knopf nimmt auch eine <span className="font-mono">known.json</span>{' '}
            aus <span className="font-mono">seed_known.py</span> — dein Anki-Wortschatz,
            damit dir nichts beigebracht wird, was du längst kannst.
          </p>
        </div>
      )}

      {state.status === 'ready' && !state.value.isEmpty && (
        <ul className="divide-rule divide-y">
          {state.value.rows.map((row) => (
            <li key={row.id} className="flex items-center gap-3 py-4">
              <button
                type="button"
                className="min-w-0 flex-1 text-left"
                onClick={() => navigate({ name: 'chapters', bookId: row.id })}
              >
                <span className="font-serif block text-xl">{row.title}</span>
                <span className="text-ink-muted block text-sm">
                  {row.author}
                </span>
                <span className="text-ink-faint mt-1 block text-xs">
                  {chapters(row.chapterCount)} · {words(row.totalTokens)} ·{' '}
                  {lemmas(row.uniqueLemmas)}
                </span>
              </button>
              <button
                type="button"
                className="text-ink-faint shrink-0 px-2 py-2 text-xs"
                onClick={() => void remove(row.id, row.title)}
              >
                Entfernen
              </button>
            </li>
          ))}
        </ul>
      )}

      {state.status === 'failed' && (
        <p className="text-ink-muted mt-10 text-sm">
          Die Bibliothek konnte nicht gelesen werden.
        </p>
      )}
    </Screen>
  )
}
