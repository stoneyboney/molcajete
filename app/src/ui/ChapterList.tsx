import { useRepositories } from '../app/repositories'
import { LIBRARY } from '../app/routes'
import { useAsync } from '../app/useAsync'
import { navigate, useGoBack } from '../app/useRoute'
import {
  buildChapterListView,
  type ChapterListView,
} from '../domain/view/chapterListView'
import { percent, words } from './format'
import { Screen } from './Screen'

export function ChapterList({ bookId }: { bookId: string }) {
  const { books, positions } = useRepositories()
  const goBack = useGoBack(LIBRARY)

  const state = useAsync<ChapterListView | null>(async () => {
    const book = await books.getBook(bookId)
    if (!book) return null
    const [summaries, readingPositions] = await Promise.all([
      books.listChapters(bookId),
      positions.listForBook(bookId),
    ])
    return buildChapterListView(book, summaries, readingPositions)
  }, [books, positions, bookId])

  if (state.status !== 'ready') {
    return <Screen title=" " back={{ label: 'Bibliothek', onClick: goBack }}>{null}</Screen>
  }

  if (!state.value) {
    return (
      <Screen title="Nicht gefunden" back={{ label: 'Bibliothek', onClick: goBack }}>
        <p className="text-ink-muted text-sm">
          Dieses Buch ist nicht mehr importiert.
        </p>
      </Screen>
    )
  }

  const view = state.value

  return (
    <Screen title={view.title} back={{ label: 'Bibliothek', onClick: goBack }}>
      <p className="text-ink-muted -mt-1 mb-5 text-sm">{view.author}</p>

      <ul className="divide-rule divide-y">
        {view.rows.map((row) => (
          <li key={row.index}>
            <button
              type="button"
              className="flex w-full items-center gap-4 py-4 text-left"
              onClick={() =>
                navigate({ name: 'reader', bookId, chapterIndex: row.index })
              }
            >
              <span className="min-w-0 flex-1">
                <span className="font-serif block truncate text-lg">
                  {row.title}
                </span>
                <span className="text-ink-faint block text-xs">
                  {words(row.tokenCount)}
                </span>
              </span>
              {row.fraction !== null && (
                <span className="flex shrink-0 items-center gap-2">
                  <span className="bg-rule h-1 w-12 overflow-hidden rounded-full">
                    <span
                      className="bg-accent block h-full"
                      style={{ width: `${row.fraction * 100}%` }}
                    />
                  </span>
                  <span className="text-ink-faint w-10 text-right text-xs tabular-nums">
                    {percent(row.fraction)}
                  </span>
                </span>
              )}
            </button>
          </li>
        ))}
      </ul>
    </Screen>
  )
}
