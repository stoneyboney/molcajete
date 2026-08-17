import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { registerSW } from 'virtual:pwa-register'
import { App } from './App'
import '../styles.css'

// `autoUpdate`: a new build takes over on the next launch. There is no update
// prompt because there is nothing the user could usefully decide — the reader
// has no unsaved state that a reload would lose.
registerSW({ immediate: true })

const root = document.getElementById('root')
if (!root) throw new Error('#root missing from index.html')

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
