import { describe, expect, it } from 'vitest'
import { buildAnkiExport } from '../../src/domain/export/ankiExport'
import { newCard, type CardFace } from '../../src/domain/srs/scheduler'

const START = new Date('2026-01-01T09:00:00Z')

function face(over: Partial<CardFace> = {}): CardFace {
  return {
    pos: 'NOUN',
    de: 'der Bau, die Höhle',
    en: 'burrow, den',
    example: 'Mi papá dice que somos gente de la madriguera.',
    regionNote: null,
    mexicanism: false,
    ...over,
  }
}

describe('buildAnkiExport', () => {
  it('always writes the four Anki header lines first', () => {
    const output = buildAnkiExport([])
    expect(output).toBe(
      '#separator:tab\n#html:true\n#notetype:Basic\n#deck:Spanisch::Molcajete\n',
    )
  })

  it('combines the German gloss and example into one HTML Back field', () => {
    const card = newCard('madriguera', START, face())
    const output = buildAnkiExport([card])
    expect(output).toContain(
      'madriguera\tder Bau, die Höhle<br><i>Mi papá dice que somos gente de la madriguera.</i>\n',
    )
  })

  it('writes just the gloss when there is no example', () => {
    const card = newCard('chido', START, face({ de: 'cool, super', example: null }))
    const output = buildAnkiExport([card])
    expect(output).toContain('chido\tcool, super\n')
  })

  it('skips a card with no face at all', () => {
    const card = newCard('pre-phase-5', START)
    const output = buildAnkiExport([card])
    expect(output.split('\n')).toHaveLength(5) // 4 headers + trailing newline, no data row
  })

  it('skips a card whose gloss failed', () => {
    const card = newCard('sin-glosa', START, face({ de: null }))
    const output = buildAnkiExport([card])
    expect(output).not.toContain('sin-glosa')
  })

  it('escapes a literal tab or newline inside a field', () => {
    const card = newCard('mixto', START, face({ de: 'a\tb\nc' }))
    const output = buildAnkiExport([card])
    const dataLine = output.split('\n').find((line) => line.startsWith('mixto'))
    expect(dataLine).toBe('mixto\ta b c<br><i>Mi papá dice que somos gente de la madriguera.</i>')
  })

  it('writes one line per exportable card, in the order given', () => {
    const cards = [
      newCard('jacal', START, face({ de: 'die Hütte', example: null })),
      newCard('sierra', START, face({ de: 'die Bergkette', example: null })),
    ]
    const lines = buildAnkiExport(cards).trim().split('\n').slice(4)
    expect(lines).toEqual(['jacal\tdie Hütte', 'sierra\tdie Bergkette'])
  })
})
