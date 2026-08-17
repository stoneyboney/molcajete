import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { registerSW } from 'virtual:pwa-register'
import { DexieBookRepository } from '../infra/DexieBookRepository'
import { DexieReadingPositionRepository } from '../infra/DexieReadingPositionRepository'
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
}

createRoot(root).render(
  <StrictMode>
    <RepositoryProvider repositories={repositories}>
      <App />
    </RepositoryProvider>
  </StrictMode>,
)
