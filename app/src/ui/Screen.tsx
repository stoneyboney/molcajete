import type { ReactNode } from 'react'

/**
 * The chrome-bearing screens: library and chapter list. `100dvh` rather than
 * `100vh` so the layout does not jump as iOS Safari's toolbars collapse, and
 * the safe-area insets are applied here so no screen has to remember them.
 */
export function Screen({
  title,
  back,
  action,
  children,
}: {
  title: string
  back?: { label: string; onClick: () => void }
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <div
      className="flex min-h-dvh flex-col"
      style={{
        paddingTop: 'env(safe-area-inset-top)',
        paddingBottom: 'env(safe-area-inset-bottom)',
        paddingLeft: 'env(safe-area-inset-left)',
        paddingRight: 'env(safe-area-inset-right)',
      }}
    >
      <header className="mx-auto flex w-full max-w-2xl items-baseline gap-3 px-5 pt-4 pb-2">
        {back && (
          <button
            type="button"
            onClick={back.onClick}
            className="text-accent -ml-1 shrink-0 px-1 py-2 text-sm"
          >
            ‹ {back.label}
          </button>
        )}
        <h1 className="font-serif min-w-0 flex-1 truncate text-2xl">{title}</h1>
        {action}
      </header>
      <main className="mx-auto w-full max-w-2xl flex-1 px-5 pb-10">
        {children}
      </main>
    </div>
  )
}
