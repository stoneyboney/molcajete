/**
 * Placeholder shell. Exists so the deploy path — Actions, HTTPS, the service
 * worker, Add to Home Screen — can be tested on the iPad before any feature
 * is written. Replaced by the router in the next commit.
 */
export function App() {
  return (
    <main
      className="flex min-h-dvh flex-col items-center justify-center gap-2 px-6 text-center"
      style={{
        paddingTop: 'env(safe-area-inset-top)',
        paddingBottom: 'env(safe-area-inset-bottom)',
      }}
    >
      <h1 className="font-serif text-4xl">Molcajete</h1>
      <p className="text-ink-muted text-sm">
        Spanisch lesen, mit vorbereitetem Wortschatz.
      </p>
    </main>
  )
}
