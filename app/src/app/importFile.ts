/**
 * One import path for the two kinds of file the app accepts.
 *
 * `ImportButton` cannot narrow its `accept` past `.json` — iOS matches it
 * against the system's idea of a file's type and a double extension is not one
 * — so the extension was never going to be the discriminator anyway. The file
 * is parsed once and dispatched on its *shape*: a bundle is an object with a
 * `schemaVersion`, a seed is an array of strings. Nothing depends on the name,
 * which is what makes AirDrop's renaming harmless.
 */

import { parseBundle } from '../domain/bundle/parseBundle'
import { parseKnownLemmas } from '../domain/bundle/parseKnown'
import type { BookRepository } from '../domain/ports/BookRepository'
import type { KnownLemmaRepository } from '../domain/ports/KnownLemmaRepository'

export type ImportOutcome =
  | {
      kind: 'book'
      bookId: string
      title: string
      chapterCount: number
      /** True when a book with this id was already stored and has been replaced. */
      replaced: boolean
    }
  | {
      kind: 'known'
      /** Lemmas in the file, after normalising and deduplicating. */
      inFile: number
      /** How many of those the store did not already hold. */
      added: number
      total: number
    }

export class UnrecognisedFileError extends Error {
  constructor() {
    super('not a Molcajete bundle and not a known.json')
    this.name = 'UnrecognisedFileError'
  }
}

export interface ImportTargets {
  books: BookRepository
  known: KnownLemmaRepository
}

export async function importFile(
  file: File,
  targets: ImportTargets,
  now: Date = new Date(),
): Promise<ImportOutcome> {
  const text = await file.text()

  let value: unknown
  try {
    value = JSON.parse(text)
  } catch (cause) {
    throw new UnrecognisedFileError()
  }

  if (Array.isArray(value)) return importKnown(value, targets.known)
  if (value !== null && typeof value === 'object') {
    return importBook(value, targets.books, now)
  }
  throw new UnrecognisedFileError()
}

async function importBook(
  value: unknown,
  books: BookRepository,
  now: Date,
): Promise<ImportOutcome> {
  // Validation before a single row is written, so a rejected file leaves the
  // database exactly as it was.
  const bundle = parseBundle(value)

  const existing = await books.getBook(bundle.book.id)
  await books.saveBundle(bundle, now)
  void requestPersistentStorage()

  return {
    kind: 'book',
    bookId: bundle.book.id,
    title: bundle.book.title,
    chapterCount: bundle.chapters.length,
    replaced: existing !== undefined,
  }
}

async function importKnown(
  value: unknown,
  known: KnownLemmaRepository,
): Promise<ImportOutcome> {
  const lemmas = parseKnownLemmas(value)

  // Counted before writing, so re-importing the same seed reports "0 new"
  // rather than claiming to have learned everything again.
  const before = await known.listAll()
  const added = lemmas.filter((lemma) => !before.has(lemma)).length

  await known.add(lemmas)
  void requestPersistentStorage()

  return {
    kind: 'known',
    inFile: lemmas.length,
    added,
    total: before.size + added,
  }
}

/**
 * Ask the browser not to evict the database.
 *
 * Best-effort and deliberately unawaited: Safari decides on its own terms and a
 * refusal is not a reason to fail an import that has already succeeded.
 */
async function requestPersistentStorage(): Promise<void> {
  try {
    await navigator.storage?.persist?.()
  } catch {
    // Not available, or refused. Nothing to do about either.
  }
}
