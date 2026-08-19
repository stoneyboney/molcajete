/**
 * Routing, by hand, over the location hash.
 *
 * Three screens do not need a router library. Hash routes also sit correctly
 * under the GitHub Pages sub-path and behind the service worker without a
 * navigateFallback rule having to guess which paths are the app's — a deep
 * link is one document plus a fragment, offline included.
 */

export type Route =
  | { name: 'library' }
  /** SPEC §6.5: due cards across every book. Carries nothing — what is due
   * is a question about the clock, asked on arrival. */
  | { name: 'review' }
  | { name: 'chapters'; bookId: string }
  | { name: 'reader'; bookId: string; chapterIndex: number }
  /**
   * The teaching session. Deliberately carries no segment number: which words
   * are still to be taught depends on what you know right now, so the screen
   * works it out on arrival. A stale deep link therefore opens the right
   * session rather than an empty one.
   */
  | { name: 'session'; bookId: string; chapterIndex: number }

export const LIBRARY: Route = { name: 'library' }

/** Anything unrecognised falls back to the library rather than a dead screen. */
export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#\/?/, '')
  if (path === '') return LIBRARY
  if (path === 'wiederholen') return { name: 'review' }

  const parts = path.split('/').map(decodeURIComponent)

  if (parts[0] === 'book' && parts[1]) {
    const bookId = parts[1]
    if (parts.length === 2) return { name: 'chapters', bookId }
    if (parts.length >= 4 && parts[2] === 'ch') {
      const chapterIndex = Number(parts[3])
      if (Number.isInteger(chapterIndex) && chapterIndex >= 0) {
        if (parts.length === 4) return { name: 'reader', bookId, chapterIndex }
        if (parts.length === 5 && parts[4] === 'lernen') {
          return { name: 'session', bookId, chapterIndex }
        }
      }
    }
  }

  return LIBRARY
}

export function routeToHash(route: Route): string {
  switch (route.name) {
    case 'library':
      return '#/'
    case 'review':
      return '#/wiederholen'
    case 'chapters':
      return `#/book/${encodeURIComponent(route.bookId)}`
    case 'reader':
      return `#/book/${encodeURIComponent(route.bookId)}/ch/${route.chapterIndex}`
    case 'session':
      return `#/book/${encodeURIComponent(route.bookId)}/ch/${route.chapterIndex}/lernen`
  }
}
