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
  | { name: 'chapters'; bookId: string }
  | { name: 'reader'; bookId: string; chapterIndex: number }

export const LIBRARY: Route = { name: 'library' }

/** Anything unrecognised falls back to the library rather than a dead screen. */
export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#\/?/, '')
  if (path === '') return LIBRARY

  const parts = path.split('/').map(decodeURIComponent)

  if (parts[0] === 'book' && parts[1]) {
    const bookId = parts[1]
    if (parts.length === 2) return { name: 'chapters', bookId }
    if (parts.length === 4 && parts[2] === 'ch') {
      const chapterIndex = Number(parts[3])
      if (Number.isInteger(chapterIndex) && chapterIndex >= 0) {
        return { name: 'reader', bookId, chapterIndex }
      }
    }
  }

  return LIBRARY
}

export function routeToHash(route: Route): string {
  switch (route.name) {
    case 'library':
      return '#/'
    case 'chapters':
      return `#/book/${encodeURIComponent(route.bookId)}`
    case 'reader':
      return `#/book/${encodeURIComponent(route.bookId)}/ch/${route.chapterIndex}`
  }
}
