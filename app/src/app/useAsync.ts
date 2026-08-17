import { useEffect, useState } from 'react'

export type Async<T> =
  | { status: 'loading' }
  | { status: 'ready'; value: T }
  | { status: 'failed'; error: unknown }

/**
 * Run an async load and track its outcome, discarding the result if the inputs
 * changed while it was in flight — otherwise flipping between two chapters
 * quickly can leave the slower read painting over the newer one.
 */
export function useAsync<T>(load: () => Promise<T>, deps: unknown[]): Async<T> {
  const [state, setState] = useState<Async<T>>({ status: 'loading' })

  useEffect(() => {
    let live = true
    setState({ status: 'loading' })
    load().then(
      (value) => {
        if (live) setState({ status: 'ready', value })
      },
      (error: unknown) => {
        if (live) setState({ status: 'failed', error })
      },
    )
    return () => {
      live = false
    }
    // The caller states the dependencies; `load` is expected to close over them.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return state
}
