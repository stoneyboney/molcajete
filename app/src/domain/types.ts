/**
 * The bundle format, as the reader decodes it.
 *
 * This is the TypeScript half of the contract written down in
 * `pipeline/molcajete_prep/schema.py`. The two files are maintained as if by
 * different people, because eventually one of them will be Swift. When the
 * pipeline's schema module changes, this one changes with it and
 * `SUPPORTED_SCHEMA_VERSION` moves.
 *
 * Two clarifications carried over from that module, both of which contradict a
 * casual reading of SPEC §4:
 *
 * 1. `t` is a **string** lexicon key (`"m0118"`), not a number. The §4 example
 *    shows integers while its own lexicon is keyed by strings; the strings win.
 * 2. **Not every token carries every field.** Whitespace has only `s` and `ws`.
 *    Punctuation and numerals have `s` and `p`. A proper noun has `s`, `l` and
 *    `p` but no `t`, because SPEC §5 gives it no lexicon entry — which is also
 *    what makes proper nouns untappable in the reader for free.
 */

export type LemmaKey = string
export type BookId = string

export const SUPPORTED_SCHEMA_VERSION = 1

/** A whitespace run. Carries no lemma, no POS and no lexicon key. */
export interface WhitespaceToken {
  s: string
  ws: true
}

/**
 * Anything that is not whitespace. `l` is absent on punctuation and numerals;
 * `t` is absent whenever the token has no lexicon entry to point at.
 */
export interface WordToken {
  s: string
  l?: string
  p?: string
  t?: LemmaKey
  ws?: undefined
}

export type Token = WhitespaceToken | WordToken

export interface Paragraph {
  id: string
  tokens: Token[]
}

export interface Chapter {
  index: number
  title: string
  tokenCount: number
  paragraphs: Paragraph[]
  /** SPEC §5 teach set. Stored verbatim; Phase 4 is what reads it. */
  teachSet: LemmaKey[]
  /** Gets the dotted underline in the reader, and nothing else. */
  glossOnly: LemmaKey[]
}

export interface Example {
  es: string
  de?: string
  chapterIndex?: number
}

export interface LexiconEntry {
  lemma: string
  pos: string
  zipf: number
  bookCount: number
  firstChapter: number
  mexicanism: boolean
  /**
   * Present only where the glossing pass found something. An absent `de` means
   * "no German gloss" and the reader has to say so out loud; the pipeline's
   * validator rejects an empty string precisely so that the two cannot be
   * confused here.
   */
  de?: string
  en?: string
  regionNote?: string
  example?: Example
}

export type Lexicon = Record<LemmaKey, LexiconEntry>

export interface BookMeta {
  id: BookId
  title: string
  author: string
  language: string
  variant: string
  totalTokens: number
  uniqueLemmas: number
}

export interface Bundle {
  schemaVersion: number
  book: BookMeta
  chapters: Chapter[]
  lexicon: Lexicon
}

/** True for tokens the reader turns into a tappable span. */
export function isTappable(token: Token): token is WordToken & { t: LemmaKey } {
  return token.ws !== true && typeof (token as WordToken).t === 'string'
}
