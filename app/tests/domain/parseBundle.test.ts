import { describe, expect, it } from 'vitest'
import {
  BundleFormatError,
  parseBundle,
  parseBundleText,
  UnsupportedSchemaVersionError,
} from '../../src/domain/bundle/parseBundle'
import { readFixture, readFixtureText } from '../fixture'

/** Assert that `mutate` makes the fixture unacceptable, and why. */
function rejects(mutate: (bundle: any) => void, because: RegExp): void {
  const bundle = readFixture()
  mutate(bundle)
  expect(() => parseBundle(bundle)).toThrow(BundleFormatError)
  expect(() => parseBundle(bundle)).toThrow(because)
}

describe('parseBundle', () => {
  it('accepts the bundle the pipeline produces', () => {
    const bundle = parseBundle(readFixture())
    expect(bundle.book.id).toBe('anonimo-los-del-cerro')
    expect(bundle.chapters).toHaveLength(3)
    expect(bundle.book.uniqueLemmas).toBe(Object.keys(bundle.lexicon).length)
  })

  it('parses from text', () => {
    expect(parseBundleText(readFixtureText()).book.language).toBe('es')
  })

  describe('schemaVersion', () => {
    it('reports the version rather than the first odd field it meets', () => {
      const bundle = readFixture()
      bundle.schemaVersion = 2
      delete bundle.lexicon // a second, unrelated fault

      const error = (() => {
        try {
          parseBundle(bundle)
        } catch (caught) {
          return caught
        }
        return null
      })()

      expect(error).toBeInstanceOf(UnsupportedSchemaVersionError)
      expect((error as UnsupportedSchemaVersionError).found).toBe(2)
      expect((error as UnsupportedSchemaVersionError).supported).toBe(1)
    })

    it('rejects a missing version', () => {
      const bundle = readFixture()
      delete bundle.schemaVersion
      expect(() => parseBundle(bundle)).toThrow(UnsupportedSchemaVersionError)
    })

    it('rejects the version as a string', () => {
      const bundle = readFixture()
      bundle.schemaVersion = '1'
      expect(() => parseBundle(bundle)).toThrow(UnsupportedSchemaVersionError)
    })
  })

  describe('input that is not a bundle', () => {
    it('rejects text that is not JSON', () => {
      expect(() => parseBundleText('<html>404</html>')).toThrow(
        /file is not JSON/,
      )
    })

    it('rejects JSON truncated mid-file', () => {
      const half = readFixtureText().slice(0, 4000)
      expect(() => parseBundleText(half)).toThrow(BundleFormatError)
    })

    it('rejects an array, a string and null', () => {
      for (const value of [[], 'molcajete', null, 42]) {
        expect(() => parseBundle(value)).toThrow(/not an object/)
      }
    })
  })

  describe('referential integrity', () => {
    it("rejects a token pointing at a lexicon key that isn't there", () => {
      rejects((bundle) => {
        bundle.chapters[0].paragraphs[0].tokens.find((t: any) => t.t).t =
          'm9999'
      }, /unknown lexicon key/)
    })

    it('rejects a teachSet key that is not in the lexicon', () => {
      rejects((bundle) => {
        bundle.chapters[1].teachSet.push('m9999')
      }, /teachSet: unknown lexicon key/)
    })

    it('rejects a glossOnly key that is not in the lexicon', () => {
      rejects((bundle) => {
        bundle.chapters[0].glossOnly = ['nope']
      }, /glossOnly: unknown lexicon key/)
    })

    it('rejects uniqueLemmas disagreeing with the lexicon', () => {
      rejects((bundle) => {
        bundle.book.uniqueLemmas += 1
      }, /uniqueLemmas/)
    })

    it('rejects chapters renumbered out of order', () => {
      rejects((bundle) => {
        bundle.chapters[1].index = 7
      }, /index is 7, expected 1/)
    })

    it('rejects duplicate paragraph ids', () => {
      rejects((bundle) => {
        bundle.chapters[0].paragraphs[1].id =
          bundle.chapters[0].paragraphs[0].id
      }, /duplicate paragraph id/)
    })
  })

  describe('token shapes', () => {
    it('accepts the four shapes the pipeline actually emits', () => {
      const bundle = parseBundle(readFixture())
      const shapes = new Set<string>()
      for (const chapter of bundle.chapters) {
        for (const paragraph of chapter.paragraphs) {
          for (const token of paragraph.tokens) {
            shapes.add(Object.keys(token).sort().join(','))
          }
        }
      }
      // whitespace, punctuation, proper noun, content word
      expect([...shapes].sort()).toEqual(['l,p,s', 'l,p,s,t', 'p,s', 's,ws'])
    })

    it('rejects a whitespace token carrying a lemma', () => {
      rejects((bundle) => {
        const tokens = bundle.chapters[0].paragraphs[0].tokens
        tokens.find((t: any) => t.ws).l = 'espacio'
      }, /whitespace token carries 'l'/)
    })

    it("rejects a token with a 't' but no 'l'", () => {
      rejects((bundle) => {
        delete bundle.chapters[0].paragraphs[0].tokens.find((t: any) => t.t).l
      }, /must also carry 'l'/)
    })

    it('rejects a numeric lexicon key, which SPEC §4 seems to allow', () => {
      rejects((bundle) => {
        bundle.chapters[0].paragraphs[0].tokens.find((t: any) => t.t).t = 4012
      }, /'t' must be a string lexicon key/)
    })

    it('rejects a token with no surface form', () => {
      rejects((bundle) => {
        delete bundle.chapters[0].paragraphs[0].tokens[0].s
      }, /token 's'/)
    })
  })

  describe('lexicon entries', () => {
    it('rejects an empty gloss, which would render as a blank line', () => {
      rejects((bundle) => {
        bundle.lexicon.m0000.de = '   '
      }, /present but empty/)
    })

    it('rejects a mexicanism with no regionNote to explain it', () => {
      rejects((bundle) => {
        bundle.lexicon.m0000.mexicanism = true
      }, /no 'regionNote'/)
    })

    it('accepts a mexicanism that carries its regionNote', () => {
      const bundle = readFixture()
      bundle.lexicon.m0000.mexicanism = true
      bundle.lexicon.m0000.regionNote = 'MX, coloquial'
      expect(() => parseBundle(bundle)).not.toThrow()
    })

    it('rejects a missing required field', () => {
      rejects((bundle) => {
        delete bundle.lexicon.m0000.zipf
      }, /lexicon\["m0000"\]\.zipf/)
    })

    it('accepts an entry with no glosses at all', () => {
      // Phase 1 bundles have none, and a Phase 2 bundle has some lemmas the
      // provider refused. Neither is a broken file.
      const bundle = parseBundle(readFixture())
      expect(() => parseBundle(bundle)).not.toThrow()
    })
  })

  it('rejects a bundle with no chapters', () => {
    rejects((bundle) => {
      bundle.chapters = []
    }, /nothing to read/)
  })
})
