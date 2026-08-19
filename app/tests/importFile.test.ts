/**
 * The import path dispatches on the file's *shape*, not its name.
 *
 * `ImportButton` cannot narrow its `accept` past `.json` — iOS matches it
 * against the system's idea of a file type and a double extension is not one —
 * so the extension was never available as a discriminator, and AirDrop renaming
 * a file has to stay harmless.
 */

import { describe, expect, it } from 'vitest'
import {
  importFile,
  UnrecognisedFileError,
  type ImportTargets,
} from '../src/app/importFile'
import { KnownFormatError } from '../src/domain/bundle/parseKnown'
import { UnsupportedSchemaVersionError } from '../src/domain/bundle/parseBundle'
import { FakeBookRepository, FakeKnownLemmaRepository } from './fakes'
import { readFixture, readFixtureText } from './fixture'

function targets(): ImportTargets & { known: FakeKnownLemmaRepository } {
  return { books: new FakeBookRepository(), known: new FakeKnownLemmaRepository() }
}

/** A `File` without a DOM: only `.text()` is ever called. */
function file(contents: string, name = 'whatever.json'): File {
  return { name, text: async () => contents } as unknown as File
}

describe('importing a bundle', () => {
  it('stores the book and reports what it did', async () => {
    const t = targets()
    const outcome = await importFile(file(readFixtureText()), t)

    expect(outcome.kind).toBe('book')
    if (outcome.kind !== 'book') return
    expect(outcome.bookId).toBe('anonimo-los-del-cerro')
    expect(outcome.chapterCount).toBe(3)
    expect(outcome.replaced).toBe(false)
    expect(await t.books.getBook('anonimo-los-del-cerro')).toBeDefined()
  })

  it('reports a re-import as a replacement', async () => {
    const t = targets()
    await importFile(file(readFixtureText()), t)
    const again = await importFile(file(readFixtureText()), t)

    expect(again.kind === 'book' && again.replaced).toBe(true)
  })

  it('does not care what the file is called', async () => {
    const t = targets()
    const outcome = await importFile(file(readFixtureText(), 'Unbenannt-3.json'), t)

    expect(outcome.kind).toBe('book')
  })

  it('names the schema version when it cannot read one', async () => {
    const stale = readFixture()
    stale.schemaVersion = 99
    await expect(
      importFile(file(JSON.stringify(stale)), targets()),
    ).rejects.toThrow(UnsupportedSchemaVersionError)
  })

  it('writes nothing when the bundle is rejected', async () => {
    const t = targets()
    const broken = readFixture()
    delete broken.chapters
    await expect(importFile(file(JSON.stringify(broken)), t)).rejects.toThrow()

    expect(await t.books.listBooks()).toEqual([])
  })
})

describe('importing a known.json', () => {
  it('marks the lemmas known and counts what was new', async () => {
    const t = targets()
    const outcome = await importFile(file('["perro","casa","correr"]'), t)

    expect(outcome.kind).toBe('known')
    if (outcome.kind !== 'known') return
    expect(outcome.inFile).toBe(3)
    expect(outcome.added).toBe(3)
    expect(outcome.total).toBe(3)
    expect(await t.known.listAll()).toEqual(new Set(['casa', 'correr', 'perro']))
  })

  it('reports nothing new on a second import of the same seed', async () => {
    // §8 says the seed is re-runnable. It should say "0 new" rather than
    // claiming to have learned everything again.
    const t = targets()
    await importFile(file('["perro","casa"]'), t)
    const again = await importFile(file('["perro","casa"]'), t)

    expect(again.kind === 'known' && again.added).toBe(0)
    expect(again.kind === 'known' && again.inFile).toBe(2)
  })

  it('counts only the genuinely new lemmas when the deck has grown', async () => {
    const t = targets()
    await importFile(file('["perro"]'), t)
    const grown = await importFile(file('["perro","casa","sierra"]'), t)

    expect(grown.kind === 'known' && grown.added).toBe(2)
    expect(grown.kind === 'known' && grown.total).toBe(3)
  })

  it('rejects an array that is not lemma strings', async () => {
    await expect(importFile(file('[1,2,3]'), targets())).rejects.toThrow(
      KnownFormatError,
    )
  })
})

describe('anything else', () => {
  it('is refused by shape rather than guessed at', async () => {
    for (const contents of ['not json at all', '"a string"', '42', 'null']) {
      await expect(importFile(file(contents), targets())).rejects.toThrow(
        UnrecognisedFileError,
      )
    }
  })
})
