import { parseBundleText } from '../domain/bundle/parseBundle'
import type { BookRepository } from '../domain/ports/BookRepository'

export interface ImportResult {
  bookId: string
  title: string
  chapterCount: number
  /** True when a book with this id was already stored and has been replaced. */
  replaced: boolean
}

/**
 * Read a `.molcajete.json` file and store it.
 *
 * Validation happens before a single row is written, so a rejected file leaves
 * the database exactly as it was. `saveBundle` then does the whole write in one
 * transaction, which means the failure mode of a backgrounded tab is "the
 * import did not happen", never "half a book".
 */
export async function importBundleFile(
  file: File,
  books: BookRepository,
  now: Date = new Date(),
): Promise<ImportResult> {
  const bundle = parseBundleText(await file.text())

  const existing = await books.getBook(bundle.book.id)
  await books.saveBundle(bundle, now)
  void requestPersistentStorage()

  return {
    bookId: bundle.book.id,
    title: bundle.book.title,
    chapterCount: bundle.chapters.length,
    replaced: existing !== undefined,
  }
}

/**
 * Ask the browser not to evict the database.
 *
 * Best-effort and deliberately unawaited by the caller: Safari decides on its
 * own terms and a refusal is not a reason to fail an import that has already
 * succeeded. Worth asking anyway — the whole premise is that the book survives
 * until the next train journey.
 */
async function requestPersistentStorage(): Promise<void> {
  try {
    await navigator.storage?.persist?.()
  } catch {
    // Not available, or refused. Nothing to do about either.
  }
}
