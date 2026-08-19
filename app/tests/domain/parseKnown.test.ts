import { describe, expect, it } from 'vitest'
import {
  KnownFormatError,
  parseKnownLemmas,
} from '../../src/domain/bundle/parseKnown'

describe('parseKnownLemmas', () => {
  it('reads the flat array seed_known.py writes', () => {
    expect(parseKnownLemmas(['perro', 'casa', 'correr'])).toEqual([
      'casa',
      'correr',
      'perro',
    ])
  })

  it('normalises casing and whitespace so a hand-edited seed still matches', () => {
    // The lexicon's lemmas are lowercase; a seed that is not would silently
    // match nothing.
    expect(parseKnownLemmas([' Perro ', 'CASA'])).toEqual(['casa', 'perro'])
  })

  it('deduplicates, so importing twice is a no-op rather than a growing store', () => {
    expect(parseKnownLemmas(['perro', 'Perro', 'perro'])).toEqual(['perro'])
  })

  it('rejects a bundle handed to it by mistake', () => {
    expect(() => parseKnownLemmas({ schemaVersion: 1 })).toThrow(KnownFormatError)
  })

  it('names the index of a bad entry, because the file may be thousands long', () => {
    expect(() => parseKnownLemmas(['perro', 42])).toThrow(/\[1\]/)
  })

  it('rejects an empty seed rather than importing nothing silently', () => {
    expect(() => parseKnownLemmas([])).toThrow(KnownFormatError)
    expect(() => parseKnownLemmas(['', '  '])).toThrow(KnownFormatError)
  })
})
