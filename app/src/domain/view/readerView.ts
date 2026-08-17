/**
 * Turns a chapter's token arrays into what the reader renders.
 *
 * The one measurement that shapes this file: the largest chapter in
 * `las-noches-mejicanas` holds 68,979 tokens across 1,046 paragraphs. Emitting
 * one span per token would put 68,979 elements on the page for one chapter,
 * which is how a reader stops scrolling at 60 fps on an iPad.
 *
 * So consecutive tokens that are not tappable — whitespace, punctuation,
 * numerals, and proper nouns, which SPEC §5 skips entirely and which therefore
 * carry no lexicon key — are merged into a single text run. `Demetrio Macías
 * miró` becomes two runs, not five, and only the second is an element.
 *
 * Measured on that chapter: 31,654 elements and 32,320 text nodes instead of
 * 68,979 elements. Element count more than halves, and the half that goes is
 * the expensive half — a text node has no box, no class, no attributes and is
 * never an event target.
 *
 * Everything here is pure and takes its type metrics as arguments, so the
 * height estimates can be tested without a browser and ported without one.
 */

import { isTappable, type Chapter, type LemmaKey, type LexiconEntry, type Paragraph } from '../types'

export interface TextRun {
  kind: 'text'
  text: string
}

export interface WordRun {
  kind: 'word'
  text: string
  key: LemmaKey
  /** In this chapter's `glossOnly` list: gets the dotted underline. */
  marked: boolean
  /**
   * The German gloss shown above the word while "reveal all" is on. Non-null
   * only for marked words that actually have one — SPEC §13.3 scopes the
   * exception to the words that never got a card.
   */
  reveal: string | null
}

export type Run = TextRun | WordRun

export interface ParagraphView {
  id: string
  runs: Run[]
  /**
   * A guess at the rendered height, used for `contain-intrinsic-size` so that
   * paragraphs skipped by `content-visibility` still contribute a sensible
   * scrollbar. Wrong by a line here and there is fine; wrong by an order of
   * magnitude would make the scroll thumb jump.
   */
  estimatedHeightPx: number
}

export interface ChapterView {
  index: number
  title: string
  paragraphs: ParagraphView[]
}

export interface TypeMetrics {
  /** Characters that fit on one line at the current measure. */
  charsPerLine: number
  lineHeightPx: number
  /** Space below a paragraph. */
  spacingPx: number
}

export const DEFAULT_TYPE_METRICS: TypeMetrics = {
  // 65ch measure, and Spanish averages a shade under one character per `ch`.
  charsPerLine: 62,
  // 19px at line-height 1.65.
  lineHeightPx: 31,
  spacingPx: 16,
}

export function buildParagraphView(
  paragraph: Paragraph,
  glossOnly: ReadonlySet<LemmaKey>,
  lexicon: ReadonlyMap<LemmaKey, LexiconEntry>,
  metrics: TypeMetrics = DEFAULT_TYPE_METRICS,
): ParagraphView {
  const runs: Run[] = []
  let pending = ''
  let characters = 0

  const flush = () => {
    if (pending !== '') {
      runs.push({ kind: 'text', text: pending })
      pending = ''
    }
  }

  for (const token of paragraph.tokens) {
    characters += token.s.length
    if (!isTappable(token)) {
      pending += token.s
      continue
    }
    flush()
    const marked = glossOnly.has(token.t)
    runs.push({
      kind: 'word',
      text: token.s,
      key: token.t,
      marked,
      reveal: marked ? (lexicon.get(token.t)?.de ?? null) : null,
    })
  }
  flush()

  return {
    id: paragraph.id,
    runs,
    estimatedHeightPx: estimateHeightPx(characters, metrics),
  }
}

export function buildChapterView(
  chapter: Chapter,
  lexicon: ReadonlyMap<LemmaKey, LexiconEntry>,
  metrics: TypeMetrics = DEFAULT_TYPE_METRICS,
): ChapterView {
  const glossOnly = new Set(chapter.glossOnly)
  return {
    index: chapter.index,
    title: chapter.title,
    paragraphs: chapter.paragraphs.map((paragraph) =>
      buildParagraphView(paragraph, glossOnly, lexicon, metrics),
    ),
  }
}

/** Every distinct lexicon key a chapter refers to, for one bulk read. */
export function lexiconKeysOf(chapter: Chapter): LemmaKey[] {
  const keys = new Set<LemmaKey>(chapter.glossOnly)
  for (const paragraph of chapter.paragraphs) {
    for (const token of paragraph.tokens) {
      if (isTappable(token)) keys.add(token.t)
    }
  }
  return [...keys]
}

function estimateHeightPx(characters: number, metrics: TypeMetrics): number {
  const lines = Math.max(1, Math.ceil(characters / metrics.charsPerLine))
  return lines * metrics.lineHeightPx + metrics.spacingPx
}
