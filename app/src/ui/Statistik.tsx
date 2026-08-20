import { useCallback, useState } from 'react'
import { loadChapterTeaching } from '../app/loadSession'
import { useRepositories } from '../app/repositories'
import { LIBRARY } from '../app/routes'
import { useAsync } from '../app/useAsync'
import { useGoBack } from '../app/useRoute'
import { buildAnkiExport } from '../domain/export/ankiExport'
import { buildChapterListView } from '../domain/view/chapterListView'
import {
  buildStatisticsView,
  type StatisticsBookInput,
  type StatisticsView,
} from '../domain/view/statisticsView'
import { cards as cardsLabel, chapters, lemmas, percent, shortDate } from './format'
import { Screen } from './Screen'

/**
 * Snapshot reading statistics (SPEC.md Phase 6) plus the Anki TSV export —
 * both about "what has been learned," so they share a screen. Everything
 * shown is computed live; see `statisticsView.ts` for why this stays a
 * snapshot rather than a logged history.
 */
export function Statistik() {
  const { books, cards, known, positions } = useRepositories()
  const goBack = useGoBack(LIBRARY)
  const [exportStatus, setExportStatus] = useState<'idle' | 'done' | 'failed'>('idle')

  const state = useAsync<StatisticsView>(async () => {
    const [cardList, knownSources, bookList] = await Promise.all([
      cards.listAll(),
      known.listAllWithSource(),
      books.listBooks(),
    ])

    const bookInputs: StatisticsBookInput[] = await Promise.all(
      bookList.map(async (book) => {
        const [summaries, readingPositions, teaching] = await Promise.all([
          books.listChapters(book.id),
          positions.listForBook(book.id),
          loadChapterTeaching(book.id, { books, cards, known }),
        ])
        const view = buildChapterListView(
          book,
          summaries,
          readingPositions,
          teaching.teaching,
          teaching.lexicon,
          teaching.state.known,
        )
        return {
          id: book.id,
          title: book.title,
          chapterCount: book.chapterCount,
          chaptersOpened: readingPositions.size,
          coverage: view.bookCoverage,
        }
      }),
    )

    return buildStatisticsView({
      cards: cardList,
      knownLemmaSources: knownSources,
      books: bookInputs,
    })
  }, [books, cards, known, positions])

  const onExport = useCallback(async () => {
    setExportStatus('idle')
    try {
      const content = buildAnkiExport(await cards.listAll())
      const file = new File([content], 'molcajete-export.txt', { type: 'text/plain' })

      if (navigator.canShare?.({ files: [file] })) {
        await navigator.share({ files: [file] })
      } else {
        const url = URL.createObjectURL(file)
        const link = document.createElement('a')
        link.href = url
        link.download = file.name
        link.click()
        URL.revokeObjectURL(url)
      }
      setExportStatus('done')
    } catch {
      // Includes the user cancelling a share sheet — not a real failure, but
      // nothing to confirm either, so stay quiet rather than show an error.
      setExportStatus('idle')
    }
  }, [cards])

  if (state.status !== 'ready') {
    return <Screen title="Statistik" back={{ label: 'Bibliothek', onClick: goBack }}>{null}</Screen>
  }

  const view = state.value

  return (
    <Screen title="Statistik" back={{ label: 'Bibliothek', onClick: goBack }}>
      <section>
        <h2 className="text-ink-faint mb-2 text-xs tracking-wide uppercase">
          Wortschatz
        </h2>
        <p className="text-lg">{lemmas(view.vocabularyKnown)} bekannt</p>
        <p className="text-ink-muted text-sm">{cardsLabel(view.cardsTotal)} insgesamt</p>
      </section>

      {view.cardsByWeek.length > 0 && (
        <section className="mt-8">
          <h2 className="text-ink-faint mb-2 text-xs tracking-wide uppercase">
            Neue Karten pro Woche
          </h2>
          <ul className="divide-rule divide-y">
            {view.cardsByWeek.map((week) => (
              <li
                key={week.weekStart.getTime()}
                className="flex items-center justify-between py-2 text-sm"
              >
                <span>{shortDate(week.weekStart)}</span>
                <span className="text-ink-muted">{cardsLabel(week.count)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="mt-8">
        <h2 className="text-ink-faint mb-2 text-xs tracking-wide uppercase">
          Bücher
        </h2>
        {view.books.length === 0 ? (
          <p className="text-ink-faint text-sm">Keine Bücher importiert.</p>
        ) : (
          <ul className="divide-rule divide-y">
            {view.books.map((book) => (
              <li key={book.id} className="py-3">
                <span className="block text-sm">{book.title}</span>
                <span className="text-ink-faint block text-xs">
                  {percent(book.coverage)} Abdeckung · {book.chaptersOpened} von{' '}
                  {chapters(book.chapterCount)} geöffnet
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-8">
        <h2 className="text-ink-faint mb-2 text-xs tracking-wide uppercase">
          Anki-Export
        </h2>
        <p className="text-ink-muted mb-3 text-xs">
          Alle in Molcajete gelernten Karten als TSV, zum Import in Anki
          (Deck „Spanisch::Molcajete", Notiztyp „Basic").
        </p>
        <button
          type="button"
          onClick={() => void onExport()}
          className="border-rule text-accent rounded-xl border px-4 py-2.5 text-sm"
        >
          Als TSV exportieren
        </button>
        {exportStatus === 'done' && (
          <p className="text-ink-muted mt-2 text-sm">Exportiert.</p>
        )}
      </section>
    </Screen>
  )
}
