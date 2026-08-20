import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { registerSW } from 'virtual:pwa-register'
import { DexieBookmarkRepository } from '../infra/DexieBookmarkRepository'
import { DexieBookRepository } from '../infra/DexieBookRepository'
import { DexieCardRepository } from '../infra/DexieCardRepository'
import { DexieDiagnosticsRepository } from '../infra/DexieDiagnosticsRepository'
import { DexieKnownLemmaRepository } from '../infra/DexieKnownLemmaRepository'
import { DexieReadingPositionRepository } from '../infra/DexieReadingPositionRepository'
import { DexieSessionRepository } from '../infra/DexieSessionRepository'
import { App } from './App'
import { RepositoryProvider } from './repositories'
import '../styles.css'

// `autoUpdate`: a new build takes over on the next launch. There is no update
// prompt because there is nothing the user could usefully decide — the reader
// holds no unsaved state that a reload would lose.
registerSW({ immediate: true })

const root = document.getElementById('root')
if (!root) throw new Error('#root missing from index.html')

// The one place that knows Dexie is the implementation. Everything above this
// line sees only the ports (CLAUDE.md rule 4).
const repositories = {
  books: new DexieBookRepository(),
  positions: new DexieReadingPositionRepository(),
  cards: new DexieCardRepository(),
  known: new DexieKnownLemmaRepository(),
  sessions: new DexieSessionRepository(),
  diagnostics: new DexieDiagnosticsRepository(),
  bookmarks: new DexieBookmarkRepository(),
  // The system clock, injected for the same reason as everything else here:
  // no domain function reads it, and the tests hand over one they control.
  clock: { now: () => new Date() },
}

/**
 * Catches whatever `#/diagnose` exists to catch: an exception with no local
 * `catch`, which on a tethered-less iPad otherwise dies silently. Installed
 * here, outside React, because these events can fire before or between
 * renders and `useRepositories()` only works inside the tree.
 *
 * `.catch(() => {})` on the write is load-bearing, not decoration: a failed
 * `recordError` (quota exceeded, IndexedDB unavailable) rejects its promise,
 * which — left unhandled — fires a second `unhandledrejection`, which calls
 * this handler again. That is an infinite loop on every subsequent page
 * interaction. The bare catch is what breaks the cycle, and is sufficient
 * because nothing else in this path can throw synchronously.
 */
function recordCaught(message: string, context: string): void {
  void repositories.diagnostics
    .recordError({ at: repositories.clock.now(), message, context })
    .catch(() => {})
}
window.addEventListener('error', (event) => {
  recordCaught(String(event.error?.message ?? event.message), 'window.onerror')
})
window.addEventListener('unhandledrejection', (event) => {
  const reason = event.reason as unknown
  recordCaught(String(reason instanceof Error ? reason.message : reason), 'unhandledrejection')
})

createRoot(root).render(
  <StrictMode>
    <RepositoryProvider repositories={repositories}>
      <App />
    </RepositoryProvider>
  </StrictMode>,
)
