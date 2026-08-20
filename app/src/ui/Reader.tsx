import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
} from 'react'
import { useRepositories } from '../app/repositories'
import { LIBRARY } from '../app/routes'
import { useAsync } from '../app/useAsync'
import { navigate, useGoBack } from '../app/useRoute'
import type { LemmaId } from '../domain/lemma'
import { buildGlossView } from '../domain/view/glossView'
import { readingFraction } from '../domain/view/progress'
import {
  buildChapterView,
  lexiconKeysOf,
  type ChapterView,
} from '../domain/view/readerView'
import { newCard } from '../domain/srs/scheduler'
import type { LemmaKey, LexiconEntry } from '../domain/types'
import { GlossSheet } from './GlossSheet'
import { Paragraph } from './Paragraph'
import { useReadingPosition } from './useReadingPosition'

interface LoadedChapter {
  view: ChapterView
  lexicon: Map<LemmaKey, LexiconEntry>
  savedParagraphId: string | null
  cardedLemmas: Set<LemmaId>
}

export function Reader({
  bookId,
  chapterIndex,
}: {
  bookId: string
  chapterIndex: number
}) {
  const { books, positions, cards } = useRepositories()

  const state = useAsync<LoadedChapter | null>(async () => {
    const chapter = await books.getChapter(bookId, chapterIndex)
    if (!chapter) return null
    // One bulk read of exactly the entries this chapter can reach. After this
    // the gloss sheet and the reveal toggle are synchronous, which is what
    // lets the components stay free of loading states mid-paragraph.
    const [lexicon, saved, cardedLemmas] = await Promise.all([
      books.getLexiconEntries(bookId, lexiconKeysOf(chapter)),
      positions.get(bookId, chapterIndex),
      cards.listCardedLemmas(),
    ])
    return {
      view: buildChapterView(chapter, lexicon),
      lexicon,
      savedParagraphId: saved?.paragraphId ?? null,
      cardedLemmas,
    }
  }, [books, positions, cards, bookId, chapterIndex])

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
  const { positions, cards, clock, bookmarks } = useRepositories()
  const goBack = useGoBack({ name: 'chapters', bookId })
  const [selected, setSelected] = useState<LemmaKey | null>(null)
  const [revealAll, setRevealAll] = useState(false)
  const [cardedLemmas, setCardedLemmas] = useState(loaded.cardedLemmas)
  const [justAddedKey, setJustAddedKey] = useState<LemmaKey | null>(null)
  const articleRef = useRef<HTMLElement | null>(null)
  const [selectedPhrase, setSelectedPhrase] = useState<string | null>(null)
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
  const onTap = useCallback((event: ReactMouseEvent<HTMLElement>) => {
    // A phrase-selection drag (SPEC §6.4's long-press bookmark) can end on a
    // tap-like release; opening a gloss sheet for whatever word is underneath
    // a real selection would be a second, unwanted action on top of it.
    if (window.getSelection()?.isCollapsed === false) return
    const target = event.target
    if (!(target instanceof Element)) return
    const word = target.closest('[data-t]')
    const key = word?.getAttribute('data-t')
    if (key) {
      setSelected(key)
      setJustAddedKey(null)
    }
  }, [])

  const gloss = selected
    ? buildGlossView(selected, loaded.lexicon.get(selected))
    : null

  const onAddCard = useCallback(async () => {
    if (!gloss) return
    const face = {
      pos: gloss.pos,
      de: gloss.de,
      en: gloss.en,
      example: gloss.example,
      regionNote: gloss.regionNote,
      mexicanism: gloss.mexicanism,
    }
    await cards.put(newCard(gloss.lemmaId, clock.now(), face))
    setCardedLemmas((carded) => new Set(carded).add(gloss.lemmaId))
    setJustAddedKey(gloss.key)
  }, [gloss, cards, clock])

  const cardStatus: 'carded' | 'added' | 'offerable' = gloss
    ? justAddedKey === gloss.key
      ? 'added'
      : cardedLemmas.has(gloss.lemmaId)
        ? 'carded'
        : 'offerable'
    : 'offerable'

  // SPEC §6.4's long-press bookmark, built on the browser's own press-and-hold
  // text selection rather than a custom gesture — see Reader.tsx's onTap
  // comment for why a real selection also has to suppress tap-to-gloss.
  useEffect(() => {
    const onSelectionChange = () => {
      const selection = window.getSelection()
      const anchor = selection?.anchorNode
      if (
        !selection ||
        selection.isCollapsed ||
        !anchor ||
        !articleRef.current?.contains(anchor)
      ) {
        setSelectedPhrase(null)
        return
      }
      const text = selection.toString().trim()
      setSelectedPhrase(text.length > 0 ? text : null)
    }
    document.addEventListener('selectionchange', onSelectionChange)
    return () => document.removeEventListener('selectionchange', onSelectionChange)
  }, [])

  const onSaveBookmark = useCallback(async () => {
    const selection = window.getSelection()
    if (!selection || selection.rangeCount === 0) return
    const text = selection.toString().trim()
    if (!text) return
    const anchor = selection.anchorNode
    const anchorElement =
      anchor instanceof Element ? anchor : anchor?.parentElement ?? null
    const paragraphId = anchorElement?.closest('[data-pid]')?.getAttribute('data-pid')
    if (!paragraphId) return

    await bookmarks.add({ bookId, chapterIndex, paragraphId, text, createdAt: clock.now() })
    selection.removeAllRanges()
    setSelectedPhrase(null)
  }, [bookmarks, bookId, chapterIndex, clock])

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
        ref={articleRef}
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

      {selectedPhrase && (
        <button
          type="button"
          onClick={() => void onSaveBookmark()}
          className="bg-accent text-paper fixed inset-x-0 z-40 mx-auto w-fit rounded-full px-5 py-2.5 text-sm shadow-lg"
          style={{ bottom: 'calc(env(safe-area-inset-bottom) + 1.5rem)' }}
        >
          Notiz speichern
        </button>
      )}

      {gloss && (
        <GlossSheet
          view={gloss}
          cardStatus={cardStatus}
          onAddCard={() => void onAddCard()}
          onDismiss={() => {
            setSelected(null)
            setJustAddedKey(null)
          }}
        />
      )}
    </div>
  )
}

function ProgressBar({ fraction }: { fraction: number }) {
  return (
    <div
      className="bg-accent fixed left-0 z-30 h-0.5 transition-[width] duration-150"
      // Below the status bar, not under it: the web view runs full-bleed in
      // standalone mode, so a bar at top 0 hides behind the clock.
      style={{ width: `${fraction * 100}%`, top: 'env(safe-area-inset-top)' }}
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
