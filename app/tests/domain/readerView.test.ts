import { describe, expect, it } from 'vitest'
import { parseBundle } from '../../src/domain/bundle/parseBundle'
import type { Chapter, LemmaKey, LexiconEntry, Paragraph } from '../../src/domain/types'
import {
  buildChapterView,
  buildParagraphView,
  lexiconKeysOf,
  type ParagraphView,
  type WordRun,
} from '../../src/domain/view/readerView'
import { readFixture } from '../fixture'

const bundle = parseBundle(readFixture())

function lexiconMap(
  overrides: Record<string, Partial<LexiconEntry>> = {},
): Map<LemmaKey, LexiconEntry> {
  const map = new Map<LemmaKey, LexiconEntry>()
  for (const [key, entry] of Object.entries(bundle.lexicon)) {
    map.set(key, { ...entry, ...overrides[key] })
  }
  return map
}

function chapter(index: number): Chapter {
  const found = bundle.chapters[index]
  if (!found) throw new Error(`fixture has no chapter ${index}`)
  return found
}

function paragraph(chapterIndex: number, index: number): Paragraph {
  const found = chapter(chapterIndex).paragraphs[index]
  if (!found) throw new Error(`fixture has no paragraph ${chapterIndex}/${index}`)
  return found
}

function textOf(view: ParagraphView): string {
  return view.runs.map((run) => run.text).join('')
}

function wordsOf(view: ParagraphView): WordRun[] {
  return view.runs.filter((run): run is WordRun => run.kind === 'word')
}

describe('buildParagraphView', () => {
  const source = paragraph(0, 1)
  const view = buildParagraphView(source, new Set(['m0037']), lexiconMap())

  it('reproduces the paragraph verbatim', () => {
    // The runs are a regrouping of the token array, never a rewrite of it.
    // Concatenating them has to give back the source text, spaces included.
    expect(textOf(view)).toBe(source.tokens.map((token) => token.s).join(''))
    expect(textOf(view)).toBe(
      'Los soldados federales venían por el camino, despacio, levantando polvo entre los huizaches.',
    )
  })

  it('merges whitespace and punctuation into the runs around them', () => {
    for (const run of view.runs) {
      if (run.kind !== 'word') continue
      expect(run.text).not.toMatch(/[\s,.;:¡!¿?]/)
    }
    // Every word run is separated by exactly one text run.
    const kinds = view.runs.map((run) => run.kind).join(' ')
    expect(kinds).not.toContain('text text')
  })

  it('emits one element per tappable token and text nodes for the rest', () => {
    // The whole reason this function exists. Only word runs become elements;
    // everything else is a text node, which has no box and is never an event
    // target. On the largest real chapter this is 31,654 elements instead of
    // 68,979.
    const tappable = source.tokens.filter(
      (token) => 't' in token && token.t !== undefined,
    ).length
    expect(wordsOf(view)).toHaveLength(tappable)
    expect(tappable).toBeLessThan(source.tokens.length * 0.6)
  })

  it('marks only the glossOnly words', () => {
    const marked = wordsOf(view).filter((run) => run.marked)
    expect(marked.map((run) => run.text)).toEqual(['huizaches'])
  })

  it('leaves proper nouns untappable', () => {
    // `Demetrio Macías` carries a lemma and a POS but no lexicon key, because
    // SPEC §5 skips PROPN entirely. It must land in a text run.
    const first = buildParagraphView(paragraph(0, 0), new Set(), lexiconMap())
    expect(wordsOf(first).map((run) => run.text)).not.toContain('Demetrio')
    expect(textOf(first)).toContain('Demetrio Macías')
  })

  it('estimates a height that grows with the text', () => {
    const short = buildParagraphView(paragraph(0, 0), new Set(), lexiconMap())
    expect(view.estimatedHeightPx).toBeGreaterThan(0)
    expect(view.estimatedHeightPx).toBeGreaterThanOrEqual(
      short.estimatedHeightPx,
    )
  })

  it('reserves one line for an empty paragraph rather than zero', () => {
    const empty = buildParagraphView(
      { id: 'x', tokens: [] },
      new Set(),
      lexiconMap(),
    )
    expect(empty.runs).toEqual([])
    expect(empty.estimatedHeightPx).toBeGreaterThan(0)
  })
})

describe('reveal-all glosses', () => {
  it('carries the German gloss only for marked words that have one', () => {
    const lexicon = lexiconMap({
      m0037: { de: 'die Akazie' }, // huizach — the chapter's glossOnly word
      m0060: { de: 'der Soldat' }, // soldado — taught, not marked
    })
    const view = buildParagraphView(paragraph(0, 1), new Set(['m0037']), lexicon)

    const revealed = wordsOf(view).filter((run) => run.reveal !== null)
    expect(revealed.map((run) => [run.text, run.reveal])).toEqual([
      ['huizaches', 'die Akazie'],
    ])
  })

  it('leaves a marked word with no German gloss unrevealed', () => {
    // The normal state for a Phase 1 bundle, and for any lemma the provider
    // refused. Constructed rather than taken from the fixture, which is now
    // glossed end to end. It must not render an empty annotation.
    const lexicon = lexiconMap()
    const huizach = lexicon.get('m0037')
    expect(huizach?.de).toBeTruthy()
    delete lexicon.get('m0037')!.de

    const view = buildParagraphView(paragraph(0, 1), new Set(['m0037']), lexicon)
    expect(wordsOf(view).every((run) => run.reveal === null)).toBe(true)
    expect(wordsOf(view).some((run) => run.marked)).toBe(true)
  })
})

describe('buildChapterView', () => {
  it('views every paragraph, in order, keeping its id', () => {
    const source = chapter(1)
    const view = buildChapterView(source, lexiconMap())
    expect(view.title).toBe(source.title)
    expect(view.paragraphs.map((p) => p.id)).toEqual(
      source.paragraphs.map((p) => p.id),
    )
  })

  it('reads glossOnly from the chapter, not from the caller', () => {
    const view = buildChapterView(chapter(1), lexiconMap())
    const marked = view.paragraphs
      .flatMap(wordsOf)
      .filter((run) => run.marked)
      .map((run) => run.key)
    expect(new Set(marked)).toEqual(new Set(['m0016'])) // chaparral
  })
})

describe('lexiconKeysOf', () => {
  it('collects each key once', () => {
    const keys = lexiconKeysOf(chapter(0))
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('covers every tappable token in the chapter', () => {
    const source = chapter(0)
    const keys = new Set(lexiconKeysOf(source))
    for (const p of source.paragraphs) {
      for (const token of p.tokens) {
        if ('t' in token && token.t) expect(keys.has(token.t)).toBe(true)
      }
    }
  })

  it('includes glossOnly keys even if the chapter never used them', () => {
    const source: Chapter = { ...chapter(0), glossOnly: ['m0000'] }
    expect(lexiconKeysOf(source)).toContain('m0000')
  })
})
