import { useCallback, useState } from 'react'
import { importBundleFile } from '../app/importBundle'
import { useRepositories } from '../app/repositories'
import { navigate } from '../app/useRoute'
import { useAsync } from '../app/useAsync'
import { buildLibraryView, type LibraryView } from '../domain/view/libraryView'
import { chapters, describeImportFailure, lemmas, words } from './format'
import { ImportButton } from './ImportButton'
import { Screen } from './Screen'

export function Library() {
  const { books } = useRepositories()
  const [reloads, setReloads] = useState(0)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<{
    headline: string
    detail: string
  } | null>(null)

  const state = useAsync<LibraryView>(
    async () => buildLibraryView(await books.listBooks()),
    [books, reloads],
  )

  const onFile = useCallback(
    async (file: File) => {
      setBusy(true)
      setFailure(null)
      try {
        await importBundleFile(file, books)
        setReloads((n) => n + 1)
      } catch (error) {
        setFailure(describeImportFailure(error))
      } finally {
        setBusy(false)
      }
    },
    [books],
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
