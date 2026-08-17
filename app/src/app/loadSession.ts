/**
 * Getting a session onto the screen, and the one place the "recompute, never
 * trust the bundle" rule is actually enforced.
 *
 * Two paths, in this order:
 *
 * 1. **A session is already stored for this chapter.** Resume it exactly.
 *    Nothing is recomputed — the queue is where you left it, and re-selecting
 *    would silently change the contents of a session in progress.
 * 2. **No stored session.** Recompute the teach set from the chapter's own
 *    lemma counts against the live known-set, split it, and start a session on
 *    the first segment.
 *
 * `Chapter.teachSet` is not read here or anywhere else in the app.
 */

import { countChapterVocabulary, type ChapterVocabulary } from '../domain/coverage'
import { buildKnownState, type KnownState } from '../domain/knownLemmas'
import { lemmaId } from '../domain/lemma'
import type { BookRepository } from '../domain/ports/BookRepository'
import type { CardRepository } from '../domain/ports/CardRepository'
import type { KnownLemmaRepository } from '../domain/ports/KnownLemmaRepository'
import type { SessionRepository } from '../domain/ports/SessionRepository'
import { MAX_CARDS_PER_SESSION, splitChapterIfNeeded } from '../domain/segments'
import { startSession, type TeachingSession } from '../domain/session/session'
import {
  DEFAULT_TEACH_SET_OPTIONS,
  selectTeachSet,
} from '../domain/teachSet'
import type { BookId, LemmaKey, LexiconEntry } from '../domain/types'

export interface SessionContext {
  session: TeachingSession
  lexicon: Map<LemmaKey, LexiconEntry>
  chapterTitle: string
  /** True when the session was picked up mid-flight rather than started fresh. */
  resumed: boolean
}

export interface SessionDependencies {
  books: BookRepository
  cards: CardRepository
  known: KnownLemmaRepository
  sessions: SessionRepository
}

export async function loadKnownState(
  cards: CardRepository,
  known: KnownLemmaRepository,
): Promise<KnownState> {
  const [carded, marked] = await Promise.all([
    cards.listCardedLemmas(),
    known.listAll(),
  ])
  // `listCardedLemmas` returns ids only, so the schedules have to be fetched to
  // find out which have matured. This is the one place that needs them.
  const full = await cards.getMany([...carded])
  return buildKnownState(full.values(), marked)
}

export async function loadSession(
  bookId: BookId,
  chapterIndex: number,
  deps: SessionDependencies,
  now: Date,
): Promise<SessionContext | null> {
  const [chapter, lexicon, stored] = await Promise.all([
    deps.books.getChapter(bookId, chapterIndex),
    deps.books.getLexicon(bookId),
    deps.sessions.load(bookId, chapterIndex),
  ])
  if (!chapter) return null

  if (stored) {
    return { session: stored, lexicon, chapterTitle: chapter.title, resumed: true }
  }

  const state = await loadKnownState(deps.cards, deps.known)
  const vocabulary = countChapterVocabulary(chapter)
  const { teach } = selectTeachSet(vocabulary.counts, lexicon, state.known, {
    ...DEFAULT_TEACH_SET_OPTIONS,
    carded: state.carded,
  })

  // Only ever the first segment. The rest is a forecast — finishing this one
  // removes its words from the next selection, so the chapter's next session
  // is again segment 0 of whatever is left.
  const [segment] = splitChapterIfNeeded(
    chapter,
    teach,
    MAX_CARDS_PER_SESSION,
    lexicon,
  )

  const cards = (segment?.teachSet ?? []).map((key) => ({
    key,
    lemmaId: lemmaId(lexicon.get(key)!),
  }))

  return {
    session: startSession(bookId, chapterIndex, cards, now),
    lexicon,
    chapterTitle: chapter.title,
    resumed: false,
  }
}

/** What the chapter list needs, without touching a single paragraph. */
export interface ChapterTeachingState {
  vocabulary: ChapterVocabulary
  cardsToLearn: number
}

export function teachingStateFor(
  vocabulary: ChapterVocabulary,
  lexicon: ReadonlyMap<LemmaKey, LexiconEntry>,
  state: KnownState,
): ChapterTeachingState {
  const { teach } = selectTeachSet(vocabulary.counts, lexicon, state.known, {
    ...DEFAULT_TEACH_SET_OPTIONS,
    carded: state.carded,
  })
  return { vocabulary, cardsToLearn: teach.length }
}
