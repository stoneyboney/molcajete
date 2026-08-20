import { useCallback, useState } from 'react'
import { useRepositories } from '../app/repositories'
import { LIBRARY } from '../app/routes'
import { useAsync } from '../app/useAsync'
import { navigate, useGoBack } from '../app/useRoute'
import { buildNotizenView, type NotizenView } from '../domain/view/notizenView'
import { dateTime } from './format'
import { Screen } from './Screen'

/**
 * SPEC §6.4's saved phrases, cross-book — same shape of screen as
 * `Review.tsx`/`Diagnose.tsx`, reached from the library.
 */
export function Notizen() {
  const { bookmarks, books } = useRepositories()
  const goBack = useGoBack(LIBRARY)
  const [reloads, setReloads] = useState(0)

  const state = useAsync<NotizenView>(async () => {
    const [entries, bookList] = await Promise.all([
      bookmarks.listAll(),
      books.listBooks(),
    ])
    return buildNotizenView(entries, bookList)
  }, [bookmarks, books, reloads])

  const remove = useCallback(
    async (id: number) => {
      await bookmarks.remove(id)
      setReloads((n) => n + 1)
    },
    [bookmarks],
  )

  return (
    <Screen title="Notizen" back={{ label: 'Bibliothek', onClick: goBack }}>
      {state.status === 'ready' && state.value.isEmpty && (
        <div className="text-ink-muted mt-16 text-center text-sm leading-relaxed text-balance">
          <p className="text-ink font-serif text-lg">Noch keine Notizen.</p>
          <p className="mt-2">
            Im Lesebildschirm eine Textstelle markieren, dann erscheint „Notiz
            speichern".
          </p>
        </div>
      )}

      {state.status === 'ready' && !state.value.isEmpty && (
        <ul className="divide-rule divide-y">
          {state.value.rows.map((row) => (
            <li key={row.id} className="flex items-start gap-3 py-4">
              <button
                type="button"
                className="min-w-0 flex-1 text-left"
                onClick={() =>
                  navigate({
                    name: 'reader',
                    bookId: row.bookId,
                    chapterIndex: row.chapterIndex,
                  })
                }
              >
                <span className="font-serif block text-lg italic" lang="es">
                  „{row.text}"
                </span>
                <span className="text-ink-faint mt-1 block text-xs">
                  {row.bookTitle} · Kapitel {row.chapterIndex + 1} ·{' '}
                  {dateTime(row.createdAt)}
                </span>
              </button>
              <button
                type="button"
                className="text-ink-faint shrink-0 px-2 py-2 text-xs"
                onClick={() => void remove(row.id)}
              >
                Entfernen
              </button>
            </li>
          ))}
        </ul>
      )}

      {state.status === 'failed' && (
        <p className="text-ink-muted mt-10 text-sm">
          Die Notizen konnten nicht gelesen werden.
        </p>
      )}
    </Screen>
  )
}
