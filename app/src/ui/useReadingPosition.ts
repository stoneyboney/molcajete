import { useEffect, useLayoutEffect, useRef, useState } from 'react'

const SAVE_DEBOUNCE_MS = 1000

/**
 * Tracks which paragraph is at the top of the viewport, restores the saved one
 * on open, and persists changes.
 *
 * An IntersectionObserver rather than a scroll handler: with 1,046 paragraphs
 * the browser is far better at answering "which of these is on screen" than a
 * scroll listener measuring rectangles, and the observer stays quiet while the
 * page is still.
 *
 * Restoring happens twice on purpose. `content-visibility: auto` means
 * off-screen paragraphs are laid out from an estimate, so the first
 * `scrollIntoView` lands near the target rather than on it; once the browser
 * has laid the real content out, the second call corrects the drift. The cost
 * of skipping it is opening a chapter a screen or two away from where you
 * stopped.
 */
export function useReadingPosition(
  paragraphIds: readonly string[],
  savedParagraphId: string | null,
  persist: (paragraphId: string, index: number) => void,
): number {
  const [current, setCurrent] = useState(0)
  const indexOf = useRef(new Map<string, number>())
  const latest = useRef<{ id: string; index: number } | null>(null)
  const timer = useRef<number | null>(null)
  const persistRef = useRef(persist)
  persistRef.current = persist

  indexOf.current = new Map(paragraphIds.map((id, index) => [id, index]))

  // Restore before the first paint the user sees, then again once the real
  // layout has replaced the intrinsic-size estimates.
  useLayoutEffect(() => {
    if (!savedParagraphId) return
    const scrollTo = () => {
      const element = document.querySelector(
        `[data-pid="${CSS.escape(savedParagraphId)}"]`,
      )
      element?.scrollIntoView({ block: 'start' })
    }
    scrollTo()
    const again = window.setTimeout(scrollTo, 120)
    return () => window.clearTimeout(again)
  }, [savedParagraphId])

  useEffect(() => {
    const onScreen = new Set<number>()

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const id = (entry.target as HTMLElement).dataset['pid']
          const index = id === undefined ? undefined : indexOf.current.get(id)
          if (index === undefined) continue
          if (entry.isIntersecting) onScreen.add(index)
          else onScreen.delete(index)
        }
        if (onScreen.size === 0) return

        const topmost = Math.min(...onScreen)
        setCurrent(topmost)

        const id = paragraphIds[topmost]
        if (id === undefined) return
        latest.current = { id, index: topmost }
        if (timer.current === null) {
          timer.current = window.setTimeout(flush, SAVE_DEBOUNCE_MS)
        }
      },
      // Only the top sliver of the viewport counts, so "where you are" is the
      // paragraph you are reading rather than the last one still peeking in.
      { rootMargin: '0px 0px -80% 0px' },
    )

    for (const element of document.querySelectorAll('[data-pid]')) {
      observer.observe(element)
    }

    function flush() {
      if (timer.current !== null) {
        window.clearTimeout(timer.current)
        timer.current = null
      }
      const position = latest.current
      if (position) persistRef.current(position.id, position.index)
    }

    // iOS rarely runs `beforeunload`; `pagehide` and a hidden tab are the two
    // moments that actually happen when the app is swiped away.
    const onHide = () => flush()
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') flush()
    }
    window.addEventListener('pagehide', onHide)
    document.addEventListener('visibilitychange', onVisibility)

    return () => {
      observer.disconnect()
      window.removeEventListener('pagehide', onHide)
      document.removeEventListener('visibilitychange', onVisibility)
      flush()
    }
  }, [paragraphIds])

  return current
}
