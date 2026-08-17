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
