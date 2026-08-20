/**
 * Two device-local ring buffers, read by the `#/diagnose` screen. Not
 * telemetry — nothing here ever leaves the device (hard constraint 1).
 *
 * `ImportLogOutcome` mirrors `ImportOutcome` from `app/importFile.ts`
 * field-for-field, plus a `failure` variant, but is its own type rather than
 * a re-export of it: a domain port depending on an app-layer type would
 * invert the dependency direction CLAUDE.md rule 4 exists to enforce. The
 * mapping from `ImportOutcome` (and from a caught error) lives in
 * `app/importFile.ts`, which already owns and fully understands both.
 *
 * `known.json` either parses in full or the whole import throws — there is
 * no partial-rejection concept in the format, so a failed import here means
 * "this attempt failed, with this error," not a rejected-entries count.
 */

import type { BookId } from '../types'

export type ImportLogOutcome =
  | {
      fileShape: 'book'
      result: 'success'
      bookId: BookId
      title: string
      chapterCount: number
      replaced: boolean
    }
  | {
      fileShape: 'known'
      result: 'success'
      inFile: number
      added: number
      total: number
    }
  | {
      fileShape: 'book' | 'known' | 'unrecognised'
      result: 'failure'
      errorName: string
      message: string
    }

export interface ImportLogEntry {
  id: number
  at: Date
  outcome: ImportLogOutcome
}

export interface ErrorLogEntry {
  id: number
  at: Date
  message: string
  /** Free text, e.g. "window.onerror", "unhandledrejection". Not a taxonomy. */
  context: string
}

export interface DiagnosticsRepository {
  /** Newest first. */
  listErrors(): Promise<ErrorLogEntry[]>
  recordError(entry: { at: Date; message: string; context: string }): Promise<void>

  /** Newest first. */
  listImports(): Promise<ImportLogEntry[]>
  recordImport(entry: { at: Date; outcome: ImportLogOutcome }): Promise<void>
}
