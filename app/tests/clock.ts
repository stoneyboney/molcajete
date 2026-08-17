import type { Clock } from '../src/domain/ports/Clock'

export interface FixedClock extends Clock {
  set(at: Date): void
  advanceDays(days: number): void
}

/** A clock the test moves by hand. See `domain/ports/Clock.ts` for why. */
export function fixedClock(start: Date): FixedClock {
  let current = start
  return {
    now: () => current,
    set: (at) => {
      current = at
    },
    advanceDays: (days) => {
      current = new Date(current.getTime() + days * 24 * 60 * 60 * 1000)
    },
  }
}
