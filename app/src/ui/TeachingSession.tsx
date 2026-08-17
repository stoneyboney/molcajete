import { useCallback, useEffect, useState } from 'react'
import { loadSession, type SessionContext } from '../app/loadSession'
import { useRepositories } from '../app/repositories'
import { useAsync } from '../app/useAsync'
import { navigate } from '../app/useRoute'
import type { ReviewGrade } from '../domain/srs/scheduler'
import {
  grade as applyGrade,
  introduce as applyIntroduce,
  type IntroductionAction,
  type TeachingSession as Session,
} from '../domain/session/session'
import { buildSessionView } from '../domain/view/sessionView'
import { GRADE_LABELS, sessionProgress } from './format'
import { CardAnswer, CardFront } from './SessionCard'
import { Screen } from './Screen'

const GRADES: ReviewGrade[] = ['again', 'hard', 'good', 'easy']

/**
 * SPEC §6.3, one card at a time, full screen.
 *
 * Two things this screen is careful about.
 *
 * **Every answer is persisted before the next card appears.** `commit` is
 * awaited and the buttons are disabled while it runs, so there is no window in
 * which a card has been answered on screen but not in storage. This is a phone;
 * the tab gets suspended mid-session and has to come back on the same card.
 *
 * **It computes nothing** (rule 5). Phase, current card, progress and the
 * German copy all arrive ready-made.
 */
export function TeachingSession({
  bookId,
  chapterIndex,
}: {
  bookId: string
  chapterIndex: number
}) {
  const { books, cards, known, sessions, clock } = useRepositories()

  const loaded = useAsync<SessionContext | null>(
    () =>
      loadSession(bookId, chapterIndex, { books, cards, known, sessions }, clock.now()),
    [books, cards, known, sessions, clock, bookId, chapterIndex],
  )

  const [session, setSession] = useState<Session | null>(null)
  const [revealed, setRevealed] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (loaded.status === 'ready' && loaded.value) setSession(loaded.value.session)
  }, [loaded])

  const toChapters = useCallback(
    () => navigate({ name: 'chapters', bookId }),
    [bookId],
  )
  const toReader = useCallback(
    () => navigate({ name: 'reader', bookId, chapterIndex }),
    [bookId, chapterIndex],
  )

  const commit = useCallback(
    async (next: Session, effects: Parameters<typeof sessions.commit>[1]) => {
      setBusy(true)
      try {
        await sessions.commit(next, effects)
        setSession(next)
        setRevealed(false)
      } finally {
        setBusy(false)
      }
    },
    [sessions],
  )

  const onIntroduce = useCallback(
    (action: IntroductionAction) => {
      if (!session || busy) return
      const step = applyIntroduce(session, action, clock.now())
      void commit(step.session, step.effects)
    },
    [session, busy, clock, commit],
  )

  const onGrade = useCallback(
    async (reviewGrade: ReviewGrade) => {
      if (!session || busy) return
      const card = session.queue[0]
      if (!card) return
      // The word may already have a schedule from an earlier chapter or book.
      const existing = await cards.get(card.lemmaId)
      const step = applyGrade(session, reviewGrade, clock.now(), existing)
      void commit(step.session, step.effects)
    },
    [session, busy, cards, clock, commit],
  )

  if (loaded.status !== 'ready' || !session) {
    return <Screen title="Lernen" back={{ label: 'Kapitel', onClick: toChapters }}>{null}</Screen>
  }

  if (!loaded.value) {
    return (
      <Screen title="Nicht gefunden" back={{ label: 'Kapitel', onClick: toChapters }}>
        <p className="text-ink-muted text-sm">Dieses Kapitel ist nicht mehr da.</p>
      </Screen>
    )
  }

  const view = buildSessionView(session, loaded.value.lexicon)

  if (view.phase === 'complete') {
    return (
      <Screen title="Fertig" back={{ label: 'Kapitel', onClick: toChapters }}>
        <p className="text-lg">
          {view.total === 0
            ? 'Für dieses Kapitel gibt es nichts mehr zu lernen.'
            : `${sessionProgress(view.passed + view.dismissed, view.total)} Karten erledigt.`}
        </p>
        {view.dismissed > 0 && (
          <p className="text-ink-muted mt-2 text-sm">
            {view.dismissed} davon kanntest du schon.
          </p>
        )}
        <button
          type="button"
          onClick={toReader}
          className="bg-accent mt-8 w-full rounded-xl px-4 py-3.5 text-base text-white"
        >
          Kapitel lesen
        </button>
      </Screen>
    )
  }

  const card = view.card!

  return (
    <Screen title="Lernen" back={{ label: 'Kapitel', onClick: toChapters }}>
      <div className="flex items-center gap-3">
        <span className="bg-rule h-1 flex-1 overflow-hidden rounded-full">
          <span
            className="bg-accent block h-full transition-[width] duration-200"
            style={{ width: `${view.fraction * 100}%` }}
          />
        </span>
        <span className="text-ink-faint shrink-0 text-xs tabular-nums">
          {sessionProgress(view.answered, view.total)}
        </span>
      </div>

      {view.phase === 'introduction' ? (
        <div className="mt-10">
          <CardFront view={card} />
          <CardAnswer view={card} />

          <div className="mt-10 flex gap-3">
            <button
              type="button"
              disabled={busy}
              onClick={() => onIntroduce('ichKenneDas')}
              className="border-rule flex-1 rounded-xl border px-4 py-3.5 text-base disabled:opacity-50"
            >
              Ich kenne das
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => onIntroduce('weiter')}
              className="bg-accent flex-1 rounded-xl px-4 py-3.5 text-base text-white disabled:opacity-50"
            >
              Weiter
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-10">
          <CardFront view={card} />

          {revealed ? (
            <>
              <CardAnswer view={card} />
              <div className="mt-10 grid grid-cols-4 gap-2">
                {GRADES.map((reviewGrade) => (
                  <button
                    key={reviewGrade}
                    type="button"
                    disabled={busy}
                    onClick={() => void onGrade(reviewGrade)}
                    className="border-rule rounded-xl border px-2 py-3.5 text-sm disabled:opacity-50"
                  >
                    {GRADE_LABELS[reviewGrade]}
                  </button>
                ))}
              </div>
            </>
          ) : (
            <button
              type="button"
              onClick={() => setRevealed(true)}
              className="border-rule text-ink-muted mt-10 w-full rounded-xl border border-dashed px-4 py-6 text-sm"
            >
              Antippen zum Aufdecken
            </button>
          )}
        </div>
      )}
    </Screen>
  )
}
