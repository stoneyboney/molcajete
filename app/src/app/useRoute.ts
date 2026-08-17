import { useCallback, useSyncExternalStore } from 'react'
import { parseRoute, routeToHash, type Route } from './routes'

function subscribe(onChange: () => void): () => void {
  window.addEventListener('hashchange', onChange)
  return () => window.removeEventListener('hashchange', onChange)
}

export function useRoute(): Route {
  const hash = useSyncExternalStore(
    subscribe,
    () => window.location.hash,
    () => '',
  )
  return parseRoute(hash)
}

export function navigate(route: Route): void {
  window.location.hash = routeToHash(route)
}

/**
 * Back, but never out of the app. Going back from a chapter on the first
 * screen of a fresh launch has nowhere to return to, so it falls forward to
 * the parent screen instead of leaving a standalone PWA with no way back.
 */
export function useGoBack(fallback: Route): () => void {
  return useCallback(() => {
    if (window.history.length > 1) window.history.back()
    else navigate(fallback)
  }, [fallback])
}
