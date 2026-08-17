/**
 * Decodes and validates a `.molcajete.json` bundle.
 *
 * The mirror of `validate_bundle` in `pipeline/molcajete_prep/schema.py`. It
 * deliberately re-checks what the pipeline already checked: the file arrives by
 * AirDrop from a machine running a version of the pipeline this build knows
 * nothing about, so "the producer validated it" is not a fact the reader has.
 *
 * Failing loudly is the whole point. A bundle that is half-imported, or
 * imported with a token pointing at a lexicon key that does not exist, produces
 * a reader that breaks in the middle of a chapter on the train. Better to
 * refuse the file at the picker.
 *
 * Messages here are English and technical — they name the path that failed, for
 * a developer. The German the user reads is produced by the UI from the error
 * type, not from these strings.
 */

import {
  SUPPORTED_SCHEMA_VERSION,
  type Bundle,
  type Chapter,
  type LexiconEntry,
  type Token,
} from '../types'

/** The file is a bundle, but of a schema version this build cannot read. */
export class UnsupportedSchemaVersionError extends Error {
  readonly found: unknown
  readonly supported: number

  constructor(found: unknown) {
    super(
      `unsupported schemaVersion ${JSON.stringify(found)}, expected ${SUPPORTED_SCHEMA_VERSION}`,
    )
    this.name = 'UnsupportedSchemaVersionError'
    this.found = found
    this.supported = SUPPORTED_SCHEMA_VERSION
  }
}

/** The file is not a valid bundle of the version it claims to be. */
export class BundleFormatError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'BundleFormatError'
  }
}

function require_(condition: boolean, message: string): asserts condition {
  if (!condition) throw new BundleFormatError(message)
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function requireString(value: unknown, where: string): asserts value is string {
  require_(typeof value === 'string', `${where}: expected a string`)
}

function requireNumber(value: unknown, where: string): asserts value is number {
  require_(
    typeof value === 'number' && Number.isFinite(value),
    `${where}: expected a number`,
  )
}

const BOOK_STRINGS = ['id', 'title', 'author', 'language', 'variant'] as const
const BOOK_NUMBERS = ['totalTokens', 'uniqueLemmas'] as const
const CHAPTER_FIELDS = [
  'index',
  'title',
  'tokenCount',
  'paragraphs',
  'teachSet',
  'glossOnly',
] as const
const OPTIONAL_GLOSS_FIELDS = ['de', 'en', 'regionNote'] as const

function validateToken(
  token: unknown,
  where: string,
  lexicon: Record<string, unknown>,
): asserts token is Token {
  require_(isObject(token), `${where}: token is not an object`)
  requireString(token['s'], `${where}: token 's'`)

  if (token['ws'] === true) {
    for (const field of Object.keys(token)) {
      require_(
        field === 's' || field === 'ws',
        `${where}: whitespace token carries '${field}' beyond 's' and 'ws'`,
      )
    }
    return
  }

  const key = token['t']
  if (key !== undefined) {
    require_(
      typeof key === 'string',
      `${where}: 't' must be a string lexicon key`,
    )
    require_(
      Object.prototype.hasOwnProperty.call(lexicon, key),
      `${where}: 't' references unknown lexicon key ${JSON.stringify(key)}`,
    )
    require_(
      typeof token['l'] === 'string',
      `${where}: token with a 't' must also carry 'l'`,
    )
  }
}

function validateLexiconEntry(
  entry: unknown,
  key: string,
): asserts entry is LexiconEntry {
  const where = `lexicon[${JSON.stringify(key)}]`
  require_(isObject(entry), `${where}: not an object`)
  requireString(entry['lemma'], `${where}.lemma`)
  requireString(entry['pos'], `${where}.pos`)
  requireNumber(entry['zipf'], `${where}.zipf`)
  requireNumber(entry['bookCount'], `${where}.bookCount`)
  requireNumber(entry['firstChapter'], `${where}.firstChapter`)
  require_(
    typeof entry['mexicanism'] === 'boolean',
    `${where}.mexicanism: expected a boolean`,
  )

  for (const field of OPTIONAL_GLOSS_FIELDS) {
    const value = entry[field]
    if (value === undefined) continue
    require_(
      typeof value === 'string' && value.trim() !== '',
      `${where}.${field}: present but empty — it should have been omitted`,
    )
  }

  // A card claiming Mexican usage without saying what kind is a claim the
  // reader cannot act on, so the two travel together. The pipeline enforces
  // this on the way out; it is cheap to insist on it on the way in.
  if (entry['mexicanism'] === true) {
    require_(
      typeof entry['regionNote'] === 'string',
      `${where}: mexicanism is true but no 'regionNote' says where or how`,
    )
  }

  const example = entry['example']
  if (example !== undefined) {
    require_(isObject(example), `${where}.example: not an object`)
    requireString(example['es'], `${where}.example.es`)
  }
}

function validateChapter(
  chapter: unknown,
  index: number,
  lexicon: Record<string, unknown>,
): asserts chapter is Chapter {
  const where = `chapters[${index}]`
  require_(isObject(chapter), `${where}: not an object`)
  for (const field of CHAPTER_FIELDS) {
    require_(field in chapter, `${where}: missing '${field}'`)
  }
  require_(
    chapter['index'] === index,
    `${where}: index is ${JSON.stringify(chapter['index'])}, expected ${index}`,
  )
  requireString(chapter['title'], `${where}.title`)
  requireNumber(chapter['tokenCount'], `${where}.tokenCount`)

  const paragraphs = chapter['paragraphs']
  require_(Array.isArray(paragraphs), `${where}.paragraphs: not an array`)

  const seenIds = new Set<string>()
  for (let i = 0; i < paragraphs.length; i += 1) {
    const paragraph: unknown = paragraphs[i]
    const paragraphWhere = `${where}.paragraphs[${i}]`
    require_(isObject(paragraph), `${paragraphWhere}: not an object`)
    requireString(paragraph['id'], `${paragraphWhere}.id`)
    require_(
      !seenIds.has(paragraph['id']),
      `${paragraphWhere}: duplicate paragraph id ${JSON.stringify(paragraph['id'])}`,
    )
    seenIds.add(paragraph['id'])

    const tokens = paragraph['tokens']
    require_(Array.isArray(tokens), `${paragraphWhere}.tokens: not an array`)
    for (const token of tokens) validateToken(token, paragraphWhere, lexicon)
  }

  for (const field of ['teachSet', 'glossOnly'] as const) {
    const keys = chapter[field]
    require_(Array.isArray(keys), `${where}.${field}: not an array`)
    for (const key of keys) {
      require_(
        typeof key === 'string' &&
          Object.prototype.hasOwnProperty.call(lexicon, key),
        `${where}.${field}: unknown lexicon key ${JSON.stringify(key)}`,
      )
    }
  }
}

/**
 * Validate `value` and return it as a `Bundle`.
 *
 * Throws `UnsupportedSchemaVersionError` when the file is recognisably a bundle
 * of the wrong version — checked before anything else, so that a future bundle
 * reports the version rather than whichever unfamiliar field happens to be
 * inspected first. Throws `BundleFormatError` for everything else.
 */
export function parseBundle(value: unknown): Bundle {
  require_(isObject(value), 'bundle is not an object')

  if (value['schemaVersion'] !== SUPPORTED_SCHEMA_VERSION) {
    throw new UnsupportedSchemaVersionError(value['schemaVersion'])
  }

  for (const section of ['book', 'chapters', 'lexicon'] as const) {
    require_(section in value, `bundle has no '${section}'`)
  }

  const book = value['book']
  require_(isObject(book), 'book: not an object')
  for (const field of BOOK_STRINGS) requireString(book[field], `book.${field}`)
  for (const field of BOOK_NUMBERS) requireNumber(book[field], `book.${field}`)
  // The id is the primary key every other store hangs off, so it gets one
  // extra check the loop above cannot express.
  const bookId = book['id']
  requireString(bookId, 'book.id')
  require_(bookId.trim() !== '', 'book.id: empty')

  const lexicon = value['lexicon']
  require_(isObject(lexicon), 'lexicon is not an object')
  for (const [key, entry] of Object.entries(lexicon)) {
    validateLexiconEntry(entry, key)
  }

  const chapters = value['chapters']
  require_(Array.isArray(chapters), 'chapters: not an array')
  require_(chapters.length > 0, 'chapters: empty — nothing to read')
  for (let i = 0; i < chapters.length; i += 1) {
    validateChapter(chapters[i], i, lexicon)
  }

  const lexiconSize = Object.keys(lexicon).length
  require_(
    book['uniqueLemmas'] === lexiconSize,
    `book.uniqueLemmas is ${book['uniqueLemmas']}, lexicon holds ${lexiconSize}`,
  )

  return value as unknown as Bundle
}

/** Parse the text of a `.molcajete.json` file. */
export function parseBundleText(text: string): Bundle {
  let value: unknown
  try {
    value = JSON.parse(text)
  } catch (cause) {
    throw new BundleFormatError(
      `file is not JSON: ${cause instanceof Error ? cause.message : String(cause)}`,
    )
  }
  return parseBundle(value)
}
