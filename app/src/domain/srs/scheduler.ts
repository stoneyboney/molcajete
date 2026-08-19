/**
 * The scheduler. The only file in the app that imports `ts-fsrs`.
 *
 * SPEC §7 is unambiguous that FSRS does the scheduling and that we do not write
 * our own. This module is the seam that makes that instruction survive the Swift
 * port: everything above it speaks in `ReviewGrade` strings and `SrsCard`
 * records, and never sees `ts-fsrs`'s numeric `Rating`, its `State` enum or its
 * `FSRS` object. Porting means reimplementing this one file against whichever
 * FSRS package Swift has, and nothing else changes.
 *
 * `ts-fsrs` is pure computation with no dependencies and no DOM access, so
 * importing it here does not break CLAUDE.md rule 3.
 *
 * Two settings are pinned deliberately:
 *
 * - **`enable_fuzz: false`.** It is already the library default, but the default
 *   is not the point — fuzz randomises intervals, and rule 3 requires the domain
 *   layer to be deterministic. Turning it on would mean threading a seed through
 *   every call site to get repeatable tests, which is a large price for spacing
 *   out review load that a single-user app does not have.
 * - **`request_retention: 0.9`**, which is SPEC §7's stated target and also the
 *   library default. Written out rather than inherited, so that a change to the
 *   default in some future version is our decision and not an upgrade's.
 */

import {
  createEmptyCard,
  fsrs,
  generatorParameters,
  Rating,
  State,
  type Card as FsrsCard,
  type Grade,
} from 'ts-fsrs'
import type { LemmaId } from '../lemma'

/**
 * The four buttons of the recall phase, as the rest of the app names them.
 * German copy for these lives in `src/ui/format.ts` — `Nochmal / Schwer / Gut /
 * Leicht` — because the domain layer stays language-neutral.
 */
export type ReviewGrade = 'again' | 'hard' | 'good' | 'easy'

/** Grades that count as "answered `Gut` or better", which is what ends a session. */
export function isPassingGrade(grade: ReviewGrade): boolean {
  return grade === 'good' || grade === 'easy'
}

const RATINGS: Record<ReviewGrade, Grade> = {
  again: Rating.Again,
  hard: Rating.Hard,
  good: Rating.Good,
  easy: Rating.Easy,
}

/**
 * Everything needed to show a card, carried on the card itself.
 *
 * The review screen (SPEC §6.5) is cross-book, and a lemma due today may have
 * been learned in a book that has since been deleted — `CardRepository` is
 * book-agnostic on purpose and `deleteBook` deliberately leaves cards alone.
 * Resolving the gloss back through some book at review time would undo that:
 * the card would depend on a bundle still being imported.
 *
 * So the face is copied onto the card when it is created. It costs a few dozen
 * bytes and makes a card self-contained, which is what "cards are global" has
 * to mean if it means anything.
 *
 * Optional because cards created before this existed do not have one; the
 * review screen falls back to showing the lemma alone.
 */
export interface CardFace {
  pos: string
  de: string | null
  en: string | null
  example: string | null
  regionNote: string | null
  mexicanism: boolean
}

/**
 * A card as this app stores it: the global lemma it teaches, plus the *entire*
 * FSRS card object.
 *
 * Storing the whole thing is a hard requirement (CLAUDE.md: "Storing FSRS state
 * as anything other than the full card object. Partial state cannot be
 * rescheduled."). `fsrs` is deliberately an opaque blob to every other module —
 * read it here, store it in `infra`, and nowhere else.
 */
export interface SrsCard {
  lemmaId: LemmaId
  fsrs: FsrsCard
  createdAt: Date
  /** See `CardFace`. Absent on cards created before Phase 5. */
  face?: CardFace
}

/** SPEC §7: known once the card is in review and stable for more than 21 days. */
export interface KnownThresholds {
  minStabilityDays: number
}

export const DEFAULT_KNOWN_THRESHOLDS: KnownThresholds = {
  minStabilityDays: 21,
}

const parameters = generatorParameters({
  request_retention: 0.9,
  enable_fuzz: false,
})

const scheduler = fsrs(parameters)

export function newCard(lemmaId: LemmaId, now: Date, face?: CardFace): SrsCard {
  return {
    lemmaId,
    fsrs: createEmptyCard(now),
    createdAt: now,
    ...(face ? { face } : {}),
  }
}

export function gradeCard(
  card: SrsCard,
  grade: ReviewGrade,
  now: Date,
): SrsCard {
  const { card: next } = scheduler.next(card.fsrs, now, RATINGS[grade])
  return { ...card, fsrs: next }
}

/**
 * Whether this card's lemma now counts as known.
 *
 * Note what is *not* here: a card that exists but has not matured is not known.
 * It is excluded from future teach sets because it already has a card, which is
 * a different test and lives in `teachSet.ts`. Conflating the two would either
 * re-teach every word every session or count a word learned this morning as
 * covered when computing whether a chapter is readable.
 */
export function isKnown(
  card: SrsCard,
  thresholds: KnownThresholds = DEFAULT_KNOWN_THRESHOLDS,
): boolean {
  return (
    card.fsrs.state === State.Review &&
    card.fsrs.stability > thresholds.minStabilityDays
  )
}

/** Whether this card is due at `now`. The review screen's whole selection rule. */
export function isDue(card: SrsCard, now: Date): boolean {
  return card.fsrs.due.getTime() <= now.getTime()
}

/** When this card next wants to be seen. The review screen reads it. */
export function dueAt(card: SrsCard): Date {
  return card.fsrs.due
}
