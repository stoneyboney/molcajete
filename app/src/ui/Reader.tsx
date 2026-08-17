import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRepositories } from '../app/repositories'
import { LIBRARY } from '../app/routes'
import { useAsync } from '../app/useAsync'
import { navigate, useGoBack } from '../app/useRoute'
import { buildGlossView } from '../domain/view/glossView'
import { readingFraction } from '../domain/view/progress'
import {
  buildChapterView,
  lexiconKeysOf,
  type ChapterView,
} from '../domain/view/readerView'
import type { LemmaKey, LexiconEntry } from '../domain/types'
import { GlossSheet } from './GlossSheet'
import { Paragraph } from './Paragraph'
import { useReadingPosition } from './useReadingPosition'

interface LoadedChapter {
  view: ChapterView
  lexicon: Map<LemmaKey, LexiconEntry>
  savedParagraphId: string | null
}

export function Reader({
  bookId,
  chapterIndex,
}: {
  bookId: string
  chapterIndex: number
}) {
  const { books, positions } = useRepositories()

  const state = useAsync<LoadedChapter | null>(async () => {
    const chapter = await books.getChapter(bookId, chapterIndex)
    if (!chapter) return null
    // One bulk read of exactly the entries this chapter can reach. After this
    // the gloss sheet and the reveal toggle are synchronous, which is what
    // lets the components stay free of loading states mid-paragraph.
    const [lexicon, saved] = await Promise.all([
      books.getLexiconEntries(bookId, lexiconKeysOf(chapter)),
      positions.get(bookId, chapterIndex),
    ])
    return {
      view: buildChapterView(chapter, lexicon),
      lexicon,
      savedParagraphId: saved?.paragraphId ?? null,
    }
  }, [books, positions, bookId, chapterIndex])

  if (state.status === 'loading') return <ReaderBlank />
  if (state.status === 'failed' || !state.value) {
    return <ReaderMissing bookId={bookId} />
  }

  return (
    <ChapterReader
      bookId={bookId}
      chapterIndex={chapterIndex}
      loaded={state.value}
    />
  )
}

function ChapterReader({
  bookId,
  chapterIndex,
  loaded,
}: {
  bookId: string
  chapterIndex: number
  loaded: LoadedChapter
}) {
  const { positions } = useRepositories()
  const goBack = useGoBack({ name: 'chapters', bookId })
  const [selected, setSelected] = useState<LemmaKey | null>(null)
  const [revealAll, setRevealAll] = useState(false)
  const showChrome = useChromeOnScrollUp()

  const paragraphIds = useMemo(
    () => loaded.view.paragraphs.map((paragraph) => paragraph.id),
    [loaded.view],
  )

  const persist = useCallback(
    (paragraphId: string, index: number) => {
      void positions.put({
        bookId,
        chapterIndex,
        paragraphId,
        fraction: readingFraction(index, paragraphIds.length),
        updatedAt: new Date(),
      })
    },
    [positions, bookId, chapterIndex, paragraphIds.length],
  )

  const current = useReadingPosition(
    paragraphIds,
    loaded.savedParagraphId,
    persist,
  )

  // One listener for the whole chapter. Tapping a word means finding the
  // nearest ancestor carrying a lexicon key, which is the word span itself or
  // the ruby around it.
  const onTap = useCallback((event: React.MouseEvent<HTMLElement>) => {
    const target = event.target
    if (!(target instanceof Element)) return
    const word = target.closest('[data-t]')
    const key = word?.getAttribute('data-t')
    if (key) setSelected(key)
  }, [])

  const gloss = selected
    ? buildGlossView(selected, loaded.lexicon.get(selected))
    : null

  return (
    <div className="min-h-dvh">
      <ProgressBar fraction={readingFraction(current, paragraphIds.length)} />

      <div
        className={`fixed inset-x-0 top-0 z-10 transition-opacity duration-200 ${
          showChrome ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
        style={{ paddingTop: 'calc(env(safe-area-inset-top) + 0.25rem)' }}
      >
        <div className="bg-paper/90 mx-auto flex max-w-2xl items-center justify-between px-4 py-2 backdrop-blur">
          <button
            type="button"
            onClick={goBack}
            className="text-accent px-1 py-1 text-sm"
          >
            ‹ Kapitel
          </button>
          <button
            type="button"
            aria-pressed={revealAll}
            onClick={() => setRevealAll((on) => !on)}
            className="border-rule text-ink-muted aria-pressed:border-accent aria-pressed:text-accent rounded-full border px-3 py-1 text-xs"
          >
            Alle Glossen
          </button>
        </div>
      </div>

      <article
        lang="es"
        data-reveal={revealAll ? 'true' : 'false'}
        onClick={onTap}
        className="reader mx-auto"
        style={{
          paddingTop: 'calc(env(safe-area-inset-top) + 3.5rem)',
          paddingBottom: 'calc(env(safe-area-inset-bottom) + 6rem)',
        }}
      >
        <h1 className="reader-title">{loaded.view.title}</h1>
        {loaded.view.paragraphs.map((paragraph) => (
          <Paragraph key={paragraph.id} view={paragraph} />
        ))}
        <p className="reader-end">Ende des Kapitels</p>
      </article>

      {gloss && (
        <GlossSheet view={gloss} onDismiss={() => setSelected(null)} />
      )}
    </div>
  )
}

function ProgressBar({ fraction }: { fraction: number }) {
  return (
    <div
      className="bg-accent fixed top-0 left-0 z-30 h-0.5 transition-[width] duration-150"
      style={{ width: `${fraction * 100}%` }}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(fraction * 100)}
      aria-label="Lesefortschritt"
    />
  )
}

/**
 * SPEC §6.4: no chrome in the reader except the progress indicator. The back
 * button and the reveal toggle still have to exist, so they follow the reading
 * direction — scrolling down is reading and hides them, scrolling up is looking
 * for a control and brings them back.
 */
function useChromeOnScrollUp(): boolean {
  const [visible, setVisible] = useState(true)
  const lastY = useRef(0)
  const ticking = useRef(false)

  useEffect(() => {
    lastY.current = window.scrollY

    const onScroll = () => {
      if (ticking.current) return
      ticking.current = true
      window.requestAnimationFrame(() => {
        ticking.current = false
        const y = window.scrollY
        const delta = y - lastY.current
        if (Math.abs(delta) < 8) return
        lastY.current = y
        setVisible(y < 80 || delta < 0)
      })
    }

    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return visible
}

function ReaderBlank() {
  return <div className="min-h-dvh" />
}

function ReaderMissing({ bookId }: { bookId: string }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-3 px-6 text-center">
      <p className="text-ink-muted text-sm">
        Dieses Kapitel ist nicht mehr da.
      </p>
      <button
        type="button"
        className="text-accent text-sm"
        onClick={() => navigate(bookId ? { name: 'chapters', bookId } : LIBRARY)}
      >
        Zur Kapitelliste
      </button>
    </div>
  )
}
