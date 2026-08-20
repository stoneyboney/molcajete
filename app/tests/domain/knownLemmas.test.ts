import { describe, expect, it } from 'vitest'
import { buildKnownState, countKnownByProvenance } from '../../src/domain/knownLemmas'
import type { KnownLemmaSource } from '../../src/domain/ports/KnownLemmaRepository'
import { dueAt, gradeCard, newCard, type SrsCard } from '../../src/domain/srs/scheduler'
import { fixedClock } from '../clock'

const START = new Date('2026-01-01T09:00:00Z')

/** A card matured by studying it on schedule, as `scheduler.test.ts` does. */
function maturedCard(lemmaId: string): SrsCard {
  const clock = fixedClock(START)
  let card = newCard(lemmaId, clock.now())
  for (let i = 0; i < 6; i++) {
    clock.set(dueAt(card))
    card = gradeCard(card, 'good', clock.now())
  }
  return card
}

function freshCard(lemmaId: string): SrsCard {
  return gradeCard(newCard(lemmaId, START), 'good', START)
}

describe('buildKnownState', () => {
  it('counts a hand-marked lemma as known', () => {
    const { known, carded } = buildKnownState([], ['jacal'])
    expect(known.has('jacal')).toBe(true)
    // "Ich kenne das" creates no card, so nothing is being learned.
    expect(carded.size).toBe(0)
  })

  it('counts a matured card as known', () => {
    const { known } = buildKnownState([maturedCard('sierra')], [])
    expect(known.has('sierra')).toBe(true)
  })

  it('separates a card being learned from a card that is known', () => {
    // The distinction the whole design rests on. A word studied this morning
    // must not be taught again — so it is carded — but must not count towards
    // coverage either — so it is not known.
    const { known, carded } = buildKnownState([freshCard('fusil')], [])
    expect(carded.has('fusil')).toBe(true)
    expect(known.has('fusil')).toBe(false)
  })

  it('unions the two routes without double-counting', () => {
    const { known, carded } = buildKnownState(
      [maturedCard('sierra'), freshCard('fusil')],
      ['jacal', 'sierra'],
    )
    expect(known).toEqual(new Set(['jacal', 'sierra']))
    expect(carded).toEqual(new Set(['sierra', 'fusil']))
  })

  it('honours a raised threshold', () => {
    const cards = [maturedCard('sierra')]
    expect(buildKnownState(cards, [], { minStabilityDays: 21 }).known.size).toBe(1)
    expect(buildKnownState(cards, [], { minStabilityDays: 3650 }).known.size).toBe(0)
  })
})

describe('countKnownByProvenance', () => {
  it('buckets by source, and a matured card with no row is maturedOnly', () => {
    const sources = new Map<string, KnownLemmaSource | undefined>([
      ['jacal', 'seed'],
      ['machete', 'manual'],
      ['zacate', undefined], // a knownLemmas row from before `source` existed
    ])
    const cards = [maturedCard('sierra')] // matured, but never marked by hand or seed

    const provenance = countKnownByProvenance(cards, sources)

    expect(provenance).toEqual({
      seed: 1,
      manual: 1,
      legacy: 1,
      maturedOnly: 1,
      total: 4,
    })
  })

  it('counts a card that is both marked and matured once, under its stored source', () => {
    const sources = new Map<string, KnownLemmaSource | undefined>([['sierra', 'seed']])
    const provenance = countKnownByProvenance([maturedCard('sierra')], sources)
    expect(provenance).toEqual({ seed: 1, manual: 0, legacy: 0, maturedOnly: 0, total: 1 })
  })

  it('excludes a carded-but-unmatured lemma entirely', () => {
    const provenance = countKnownByProvenance([freshCard('fusil')], new Map())
    expect(provenance.total).toBe(0)
  })

  it('agrees with buildKnownState on the total', () => {
    const cards = [maturedCard('sierra'), freshCard('fusil')]
    const sources = new Map<string, KnownLemmaSource | undefined>([
      ['jacal', 'seed'],
      ['zacate', 'manual'],
    ])
    const markedKnown = [...sources.keys()]

    const provenance = countKnownByProvenance(cards, sources)
    const { known } = buildKnownState(cards, markedKnown)

    expect(provenance.total).toBe(known.size)
  })
})
