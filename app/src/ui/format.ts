/**
 * Every user-facing string in the app is German (CLAUDE.md). This is where the
 * German lives, together with the number formatting, so the domain view models
 * can stay language-neutral and port to Swift without dragging copy along.
 */

import {
  BundleFormatError,
  UnsupportedSchemaVersionError,
} from '../domain/bundle/parseBundle'

const numbers = new Intl.NumberFormat('de-DE')

export function words(value: number): string {
  return `${numbers.format(value)} Wörter`
}

export function chapters(value: number): string {
  return value === 1 ? '1 Kapitel' : `${numbers.format(value)} Kapitel`
}

export function lemmas(value: number): string {
  return `${numbers.format(value)} Lemmata`
}

export function percent(fraction: number): string {
  return `${Math.round(fraction * 100)} %`
}

export function cards(value: number): string {
  return value === 1 ? '1 Karte' : `${numbers.format(value)} Karten`
}

export function sessions(value: number): string {
  return value === 1 ? '1 Sitzung' : `${numbers.format(value)} Sitzungen`
}

/** The chapter list's status chip. Null when there is nothing to learn. */
export function cardsToLearn(count: number, sessionCount: number): string | null {
  if (count === 0) return null
  return sessionCount === 1
    ? `${cards(count)} lernen`
    : `${cards(count)} lernen · ${sessions(sessionCount)}`
}

/** SPEC §6.3's four FSRS buttons. */
export const GRADE_LABELS = {
  again: 'Nochmal',
  hard: 'Schwer',
  good: 'Gut',
  easy: 'Leicht',
} as const

export function sessionProgress(answered: number, total: number): string {
  return `${numbers.format(answered)} von ${numbers.format(total)}`
}

/**
 * SPEC §13.2: coverage's real job is to say whether the *book* suits you, not
 * whether you are ready for the chapter. So the warning is about the book. It
 * never appears next to a lock, because there is no lock.
 */
export function coverageNote(fraction: number): string | null {
  if (fraction >= 0.9) return null
  if (fraction < 0.6) {
    return `Nur ${percent(fraction)} Abdeckung — dieses Buch ist im Moment sehr anspruchsvoll.`
  }
  return `${percent(fraction)} Abdeckung — dieses Buch fordert viel Wortschatz.`
}

/**
 * The line under the book title when the whole book is far out of reach.
 * SPEC §13.2 again: "If a chapter needs five sessions to clear 90%, switch
 * books — that signal is worth more than a lock screen."
 */
export function bookDifficultyNote(
  fraction: number,
  sessionCount: number,
): string | null {
  if (fraction >= 0.9 || sessionCount <= 3) return null
  return `Dieses Buch bräuchte ${sessions(sessionCount)}, um auf 90 % zu kommen. Ein leichteres Buch liest sich vielleicht besser.`
}

export interface ImportFailure {
  headline: string
  detail: string
}

/**
 * German for the user, the validator's own message underneath it. The technical
 * line stays in English and stays visible: when a bundle is rejected the next
 * step is on the desktop, in the pipeline, and the path that failed is the
 * thing worth knowing there.
 */
export function describeImportFailure(error: unknown): ImportFailure {
  if (error instanceof UnsupportedSchemaVersionError) {
    return {
      headline: `Dieses Bundle hat Schemaversion ${String(error.found)}. Diese App liest Version ${error.supported}.`,
      detail: 'Bundle mit der aktuellen Pipeline neu erzeugen.',
    }
  }
  if (error instanceof BundleFormatError) {
    return {
      headline: 'Die Datei ist kein gültiges Molcajete-Bundle.',
      detail: error.message,
    }
  }
  return {
    headline: 'Import fehlgeschlagen.',
    detail: error instanceof Error ? error.message : String(error),
  }
}
