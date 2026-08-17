import { loadChapterTeaching } from '../app/loadSession'
import { useRepositories } from '../app/repositories'
import { LIBRARY } from '../app/routes'
import { useAsync } from '../app/useAsync'
import { navigate, useGoBack } from '../app/useRoute'
import {
  buildChapterListView,
  type ChapterListView,
} from '../domain/view/chapterListView'
import {
  bookDifficultyNote,
  cardsToLearn,
  coverageNote,
  percent,
  words,
} from './format'
import { Screen } from './Screen'

/**
 * SPEC §6.2, plus §13 decision 2's coverage diagnostic.
 *
 * There is no locked state and no gate. Tapping the row opens the reader,
 * exactly as it did before Phase 4; `Lernen` sits beside it as an offer. The
 * coverage figure is information about the book, not a permission check.
 */
export function ChapterList({ bookId }: { bookId: string }) {
  const { books, positions, cards, known } = useRepositories()
  const goBack = useGoBack(LIBRARY)

  const state = useAsync<ChapterListView | null>(async () => {
    const book = await books.getBook(bookId)
    if (!book) return null

    const [summaries, readingPositions, teaching] = await Promise.all([
      books.listChapters(bookId),
      positions.listForBook(bookId),
      loadChapterTeaching(bookId, { books, cards, known }),
    ])

    return buildChapterListView(
      book,
      summaries,
      readingPositions,
      teaching.teaching,
      teaching.lexicon,
      teaching.state.known,
    )
  }, [books, positions, cards, known, bookId])

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
  const difficulty = bookDifficultyNote(view.bookCoverage, view.bookSessionsToGo)

  return (
    <Screen title={view.title} back={{ label: 'Bibliothek', onClick: goBack }}>
      <p className="text-ink-muted -mt-1 text-sm">{view.author}</p>

      {difficulty && (
        <p className="text-ink-muted border-rule mt-3 rounded-lg border border-dashed px-3 py-2 text-xs">
          {difficulty}
        </p>
      )}

      <ul className="divide-rule mt-5 divide-y">
        {view.rows.map((row) => {
          const learn = cardsToLearn(row.cardsToLearn, row.sessionsToGo)
          const note = coverageNote(row.coverage)

          return (
            <li key={row.index} className="py-4">
              <div className="flex items-center gap-4">
                <button
                  type="button"
                  className="min-w-0 flex-1 text-left"
                  onClick={() =>
                    navigate({ name: 'reader', bookId, chapterIndex: row.index })
                  }
                >
                  <span className="font-serif block truncate text-lg">
                    {row.title}
                  </span>
                  <span className="text-ink-faint block text-xs">
                    {words(row.tokenCount)} · {percent(row.coverage)} Abdeckung
                  </span>
                </button>

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
              </div>

              {note && <p className="text-ink-faint mt-1.5 text-xs">{note}</p>}

              {learn && (
                <button
                  type="button"
                  className="border-rule text-accent mt-2.5 rounded-lg border px-3 py-1.5 text-xs"
                  onClick={() =>
                    navigate({ name: 'session', bookId, chapterIndex: row.index })
                  }
                >
                  {learn} · danach {percent(row.projectedCoverage)}
                </button>
              )}
            </li>
          )
        })}
      </ul>
    </Screen>
  )
}
