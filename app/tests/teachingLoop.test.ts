/**
 * Phase 4 end to end, against the real fixture.
 *
 * This is the only test above `tests/domain/` and it is here because the
 * claims it checks are claims about the *flow* — recompute, teach, commit,
 * recompute — rather than about any one function. SPEC §12's success condition
 * for this phase is "you learn 18 words, then read the chapter and notice the
 * difference", and the difference is what this file measures.
 */

import { describe, expect, it } from 'vitest'
import { loadChapterTeaching, loadSession } from '../src/app/loadSession'
import { parseBundle } from '../src/domain/bundle/parseBundle'
import { computeCoverage } from '../src/domain/coverage'
import {
  grade,
  introduce,
  isComplete,
  type TeachingSession,
} from '../src/domain/session/session'
import { CLOSED_CLASS_POS } from '../src/domain/teachSet'
import { buildSessionView } from '../src/domain/view/sessionView'
import {
  FakeBookRepository,
  FakeCardRepository,
  FakeKnownLemmaRepository,
  FakeSessionRepository,
} from './fakes'
import { readFixture } from './fixture'
import { fixedClock } from './clock'

const BOOK = 'anonimo-los-del-cerro'
const START = new Date('2026-01-01T09:00:00Z')

async function freshApp() {
  const books = new FakeBookRepository()
  const cards = new FakeCardRepository()
  const known = new FakeKnownLemmaRepository()
  const sessions = new FakeSessionRepository(cards, known)
  await books.saveBundle(parseBundle(readFixture()))
  return { books, cards, known, sessions }
}

type App = Awaited<ReturnType<typeof freshApp>>

/** Run a whole session the way the screen does: answer, commit, repeat. */
async function runSession(
  app: App,
  chapterIndex: number,
  answer: (session: TeachingSession) => 'weiter' | 'ichKenneDas' | 'good' | 'again',
  clock = fixedClock(START),
): Promise<TeachingSession> {
  const context = await loadSession(BOOK, chapterIndex, app, clock.now())
  if (!context) throw new Error('no chapter')

  let session = context.session
  let guard = 0
  while (!isComplete(session) && guard++ < 500) {
    const action = answer(session)
    const step =
      action === 'weiter' || action === 'ichKenneDas'
        ? introduce(session, action, clock.now())
        : grade(
            session,
            action,
            clock.now(),
            await app.cards.get(session.queue[0]!.lemmaId),
          )
    await app.sessions.commit(step.session, step.effects)
    session = step.session
  }
  return session
}

const alwaysGood = (session: TeachingSession) =>
  session.phase === 'introduction' ? ('weiter' as const) : ('good' as const)

describe('the first session', () => {
  it('teaches 18 words — the SPEC §12 success condition', async () => {
    const app = await freshApp()
    const context = await loadSession(BOOK, 0, app, START)

    expect(context?.session.total).toBe(18)
    expect(context?.resumed).toBe(false)
  })

  it('ignores the teachSet the bundle baked in', async () => {
    const app = await freshApp()
    const bundle = parseBundle(readFixture())
    const context = await loadSession(BOOK, 0, app, START)

    expect(bundle.chapters[0]!.teachSet).toHaveLength(25)
    expect(context?.session.total).toBe(18)
  })

  it('shows a German gloss and a book sentence on the first card', async () => {
    const app = await freshApp()
    const context = (await loadSession(BOOK, 0, app, START))!
    const view = buildSessionView(context.session, context.lexicon)

    expect(view.phase).toBe('introduction')
    expect(view.card?.de).toBeTruthy()
    expect(view.card?.example).toBeTruthy()
  })

  it('writes a card for every word it taught', async () => {
    const app = await freshApp()
    const session = await runSession(app, 0, alwaysGood)

    expect(isComplete(session)).toBe(true)
    expect(app.cards.rows.size).toBe(18)
    expect(app.known.rows.size).toBe(0)
  })
})

describe('after studying chapter 1', () => {
  it('has fewer cards left in chapter 2 — the shared words now have cards', async () => {
    // Chapter 2 reuses sierra, caballo, jacal and fusil from chapter 1. This is
    // the "taught where it occurs, not where it debuts" rule paying off.
    const app = await freshApp()
    const before = await loadChapterTeaching(BOOK, app)
    await runSession(app, 0, alwaysGood)
    const after = await loadChapterTeaching(BOOK, app)

    expect(before.teaching.get(1)!.teach).toHaveLength(22)
    expect(after.teaching.get(1)!.teach.length).toBeLessThan(22)
    expect(after.teaching.get(0)!.teach).toHaveLength(0)
  })

  it('leaves chapter 1 with nothing to learn but does not call it known', async () => {
    // Cards exist, so it is not taught again. They have not matured, so the
    // words do not count towards coverage yet. Both at once.
    const app = await freshApp()
    await runSession(app, 0, alwaysGood)
    const { teaching, lexicon, state } = await loadChapterTeaching(BOOK, app)

    expect(teaching.get(0)!.teach).toHaveLength(0)
    expect(state.carded.size).toBe(18)
    expect(state.known.size).toBe(0)

    const coverage = computeCoverage(
      teaching.get(0)!.vocabulary,
      lexicon,
      state.known,
    )
    expect(coverage).toBeLessThan(0.2)
  })

  it('raises coverage once those cards mature', async () => {
    const app = await freshApp()
    const clock = fixedClock(START)

    // Study chapter 1 repeatedly, each time when the cards fall due, until
    // they pass SPEC §7's 21-day stability threshold. No real time passes.
    await runSession(app, 0, alwaysGood, clock)
    for (let round = 0; round < 6; round++) {
      clock.advanceDays(30)
      for (const card of [...app.cards.rows.values()]) {
        const { gradeCard } = await import('../src/domain/srs/scheduler')
        await app.cards.put(gradeCard(card, 'good', clock.now()))
      }
    }

    const { teaching, lexicon, state } = await loadChapterTeaching(BOOK, app)
    expect(state.known.size).toBe(18)

    const coverage = computeCoverage(
      teaching.get(0)!.vocabulary,
      lexicon,
      state.known,
    )
    expect(coverage).toBeCloseTo(20 / 35)
  })

  it('caps below 90% however much you study, until function words are seeded', async () => {
    // Worth pinning, because it looks like a bug and is not. Learning every
    // word chapter 1 will ever teach reaches 20 of its 35 word tokens. The
    // other 15 are el×7, su×2, de, y, por, entre, desde — closed-class words
    // the teach set deliberately never contains — plus `huizach`, a genuine
    // gloss-only rarity.
    //
    // Coverage therefore understates readability by design until SPEC §8's
    // Anki seed lands in Phase 5 and marks the function words known. Until
    // then the 0.90 warning fires on every book, and it is the warning that is
    // premature, not the arithmetic. Do not "fix" this by teaching `el`.
    const app = await freshApp()
    const { teaching, lexicon } = await loadChapterTeaching(BOOK, app)
    const { vocabulary, teach } = teaching.get(0)!

    const everythingTeachable = new Set(
      teach.map((key) => lexicon.get(key)!.lemma),
    )
    const ceiling = computeCoverage(vocabulary, lexicon, everythingTeachable)

    expect(ceiling).toBeCloseTo(20 / 35)
    expect(ceiling).toBeLessThan(0.9)

    // And the remainder really is closed class, not something we forgot.
    const uncovered = [...vocabulary.counts.keys()]
      .map((key) => lexicon.get(key)!)
      .filter((entry) => !everythingTeachable.has(entry.lemma))
    expect(uncovered.filter((e) => CLOSED_CLASS_POS.has(e.pos)).length).toBe(
      uncovered.length - 1, // `huizach`, the one open-class gloss-only word
    )
  })
})

describe('"Ich kenne das"', () => {
  it('removes the word from every future teach set in the book', async () => {
    const app = await freshApp()
    const context = (await loadSession(BOOK, 0, app, START))!
    const first = context.session.queue[0]!

    const step = introduce(context.session, 'ichKenneDas', START)
    await app.sessions.commit(step.session, step.effects)

    expect(app.known.rows.has(first.lemmaId)).toBe(true)
    // And no card was created — it is not a review.
    expect(app.cards.rows.size).toBe(0)

    const { teaching, lexicon } = await loadChapterTeaching(BOOK, app)
    for (const { teach } of teaching.values()) {
      const lemmas = teach.map((key) => lexicon.get(key)!.lemma)
      expect(lemmas).not.toContain(first.lemmaId)
    }
  })

  it('counts towards coverage immediately, unlike a fresh card', async () => {
    const app = await freshApp()
    let session = (await loadSession(BOOK, 0, app, START))!.session
    for (let i = 0; i < 5; i++) {
      const step = introduce(session, 'ichKenneDas', START)
      await app.sessions.commit(step.session, step.effects)
      session = step.session
    }

    const { teaching, lexicon, state } = await loadChapterTeaching(BOOK, app)
    expect(state.known.size).toBe(5)
    expect(
      computeCoverage(teaching.get(0)!.vocabulary, lexicon, state.known),
    ).toBeGreaterThan(0.1)
  })
})

describe('an interrupted session', () => {
  it('resumes on the same card rather than starting over', async () => {
    const app = await freshApp()
    let session = (await loadSession(BOOK, 0, app, START))!.session

    // Get into the recall phase, then answer a few.
    for (let i = 0; i < 18; i++) {
      const step = introduce(session, 'weiter', START)
      await app.sessions.commit(step.session, step.effects)
      session = step.session
    }
    for (let i = 0; i < 3; i++) {
      const step = grade(session, 'good', START)
      await app.sessions.commit(step.session, step.effects)
      session = step.session
    }

    // The tab dies here. Everything below comes back from storage only.
    const resumed = await loadSession(BOOK, 0, app, START)

    expect(resumed?.resumed).toBe(true)
    expect(resumed?.session.phase).toBe('recall')
    expect(resumed?.session.passed).toHaveLength(3)
    expect(resumed?.session.queue[0]?.key).toBe(session.queue[0]?.key)
    expect(resumed?.session.total).toBe(18)
  })

  it('does not recompute a session in progress', async () => {
    // Re-selecting on resume would change the contents of a running session:
    // the three cards already graded now have cards and would drop out.
    const app = await freshApp()
    let session = (await loadSession(BOOK, 0, app, START))!.session
    for (let i = 0; i < 18; i++) {
      const step = introduce(session, 'weiter', START)
      await app.sessions.commit(step.session, step.effects)
      session = step.session
    }
    const step = grade(session, 'good', START)
    await app.sessions.commit(step.session, step.effects)

    const resumed = await loadSession(BOOK, 0, app, START)
    expect(resumed?.session.total).toBe(18)
    expect(resumed?.session.queue).toHaveLength(17)
  })

  it('starts a fresh session once the last one completed', async () => {
    const app = await freshApp()
    await runSession(app, 0, alwaysGood)

    const next = await loadSession(BOOK, 0, app, START)
    expect(next?.resumed).toBe(false)
    expect(next?.session.total).toBe(0)
    expect(isComplete(next!.session)).toBe(true)
  })
})

describe('a chapter that needs two sessions', () => {
  it('teaches the rest on the second run', async () => {
    const app = await freshApp()

    const first = await loadSession(BOOK, 1, app, START)
    expect(first?.session.total).toBe(15) // its three paragraphs debut 8, 7, 7

    await runSession(app, 1, alwaysGood)

    const second = await loadSession(BOOK, 1, app, START)
    expect(second?.session.total).toBe(7)
    expect(second?.resumed).toBe(false)

    await runSession(app, 1, alwaysGood)
    const third = await loadSession(BOOK, 1, app, START)
    expect(third?.session.total).toBe(0)
  })
})

describe('cards are global', () => {
  it('does not re-teach a word in a second book', async () => {
    const app = await freshApp()
    await runSession(app, 0, alwaysGood)

    // The same text imported under a different id — a stand-in for a second
    // book sharing vocabulary. Its lexicon keys are the same strings, but that
    // is irrelevant: matching happens on the lemma.
    const other = parseBundle(readFixture())
    other.book.id = 'otro-libro'
    await app.books.saveBundle(other)

    const context = await loadSession('otro-libro', 0, app, START)
    expect(context?.session.total).toBe(0)
  })
})
