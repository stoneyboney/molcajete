/**
 * Every user-facing string in the app is German (CLAUDE.md). This is where the
 * German lives, together with the number formatting, so the domain view models
 * can stay language-neutral and port to Swift without dragging copy along.
 */

import {
  BundleFormatError,
  UnsupportedSchemaVersionError,
} from '../domain/bundle/parseBundle'
import { KnownFormatError } from '../domain/bundle/parseKnown'
import { UnrecognisedFileError, type ImportOutcome } from '../app/importFile'
import type { ImportLogOutcome } from '../domain/ports/DiagnosticsRepository'
import type { FsrsStateLabel } from '../domain/srs/scheduler'

const numbers = new Intl.NumberFormat('de-DE')
const dateTimeFormat = new Intl.DateTimeFormat('de-DE', { dateStyle: 'short', timeStyle: 'medium' })
const dateFormat = new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium' })

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

/** The library's due chip. Null when nothing is due — no chip, no nagging. */
export function dueCards(count: number): string | null {
  return count === 0 ? null : `${cards(count)} fällig`
}

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
  // Deliberately not "um auf 90 % zu kommen" — the number is how many sessions
  // the whole teach set needs, which is not the same as the point at which
  // coverage crosses the threshold. Say the thing that is actually true.
  return `Bei ${percent(fraction)} Abdeckung stehen noch ${sessions(sessionCount)} an. Ein leichteres Buch liest sich vielleicht besser.`
}

export interface ImportFailure {
  headline: string
  detail: string
}

/** What an import actually did, once it worked. */
export function describeImportSuccess(outcome: ImportOutcome): string {
  if (outcome.kind === 'book') {
    return outcome.replaced
      ? `„${outcome.title}“ ersetzt · ${chapters(outcome.chapterCount)}`
      : `„${outcome.title}“ importiert · ${chapters(outcome.chapterCount)}`
  }
  if (outcome.added === 0) {
    // Re-importing the same seed. Worth saying out loud, or it looks broken.
    return `Nichts Neues — diese ${lemmas(outcome.inFile)} sind schon bekannt.`
  }
  return `${lemmas(outcome.added)} neu als bekannt markiert · ${numbers.format(outcome.total)} insgesamt`
}

/**
 * German for the user, the validator's own message underneath it. The technical
 * line stays in English and stays visible: when a bundle is rejected the next
 * step is on the desktop, in the pipeline, and the path that failed is the
 * thing worth knowing there.
 */
export function describeImportFailure(error: unknown): ImportFailure {
  if (error instanceof UnrecognisedFileError) {
    return {
      headline: 'Diese Datei kennt die App nicht.',
      detail:
        'Erwartet wird ein .molcajete.json aus der Pipeline oder ein known.json aus seed_known.py.',
    }
  }
  if (error instanceof KnownFormatError) {
    return {
      headline: 'Diese known.json ist nicht lesbar.',
      detail: error.message,
    }
  }
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

// --- #/diagnose ---------------------------------------------------------

export function dateTime(date: Date): string {
  return dateTimeFormat.format(date)
}

export function shortDate(date: Date): string {
  return dateFormat.format(date)
}

/** `undefined` in, dash out — the storage estimate and the build hash both read this way when unavailable. */
export function orUnknown(value: string | undefined): string {
  return value ?? 'unbekannt'
}

const BYTE_UNITS = ['B', 'KB', 'MB', 'GB'] as const

export function bytes(value: number | undefined): string {
  if (value === undefined) return 'unbekannt'
  let size = value
  let unit = 0
  while (size >= 1024 && unit < BYTE_UNITS.length - 1) {
    size /= 1024
    unit += 1
  }
  const formatted = unit === 0 ? numbers.format(size) : size.toFixed(1).replace('.', ',')
  return `${formatted} ${BYTE_UNITS[unit]}`
}

export const FSRS_STATE_LABELS: Record<FsrsStateLabel, string> = {
  new: 'Neu',
  learning: 'Lernen',
  review: 'Wiederholung',
  relearning: 'Erneut lernen',
}

export function schemaStatus(schema: { live: number; expected: number; matches: boolean }): string {
  return schema.matches
    ? `Schema v${schema.live} (aktuell)`
    : `Schema v${schema.live} — Code erwartet v${schema.expected}`
}

export function serviceWorkerStatus(sw: {
  supported: boolean
  registered: boolean
  waiting: boolean
}): string {
  if (!sw.supported) return 'Service Worker nicht unterstützt'
  if (sw.waiting) return 'Neue Version wartet'
  return sw.registered ? 'Aktiv' : 'Nicht registriert'
}

export function storageStatus(storage: {
  usageBytes: number | undefined
  quotaBytes: number | undefined
  supported: boolean
}): string {
  if (!storage.supported) return 'Nicht verfügbar'
  return `${bytes(storage.usageBytes)} von ${bytes(storage.quotaBytes)}`
}

/** A one-line summary for a row in the import log. */
export function describeImportLogOutcome(outcome: ImportLogOutcome): string {
  if (outcome.result === 'failure') {
    return `Fehlgeschlagen (${outcome.fileShape}) — ${outcome.errorName}: ${outcome.message}`
  }
  if (outcome.fileShape === 'book') {
    return outcome.replaced
      ? `Buch „${outcome.title}“ ersetzt · ${chapters(outcome.chapterCount)}`
      : `Buch „${outcome.title}“ importiert · ${chapters(outcome.chapterCount)}`
  }
  return `Seed: ${lemmas(outcome.added)} neu von ${numbers.format(outcome.inFile)}`
}
