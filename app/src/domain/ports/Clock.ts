/**
 * Where the current time comes from.
 *
 * CLAUDE.md rule 3 forbids the domain layer from reading the clock: every
 * function that needs a date takes `now: Date` as an argument. This interface is
 * how the *caller* obtains that argument — the screens hold a `Clock`, ask it
 * once per user action, and pass the answer down.
 *
 * The reason is testability at a scale a real clock cannot reach. A card's
 * schedule has to be checked across three weeks of review, and waiting three
 * weeks is not a test. `fixedClock` in the test suite advances by days between
 * calls and the scheduler cannot tell the difference.
 */

export interface Clock {
  now(): Date
}
