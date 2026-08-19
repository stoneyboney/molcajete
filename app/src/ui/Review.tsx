import { useCallback, useEffect, useState } from 'react'
import { useRepositories } from '../app/repositories'
import { LIBRARY } from '../app/routes'
import { useAsync } from '../app/useAsync'
import { useGoBack } from '../app/useRoute'
import {
  grade as applyGrade,
  startReview,
  type ReviewSession,
} from '../domain/review/reviewSession'
import type { ReviewGrade } from '../domain/srs/scheduler'
import { buildReviewView } from '../domain/view/reviewView'
import { GRADE_LABELS, sessionProgress } from './format'
import { CardAnswer, CardFront } from './SessionCard'
import { Screen } from './Screen'

const GRADES: ReviewGrade[] = ['again', 'hard', 'good', 'easy']

/**
 * SPEC §6.5 — the screen that makes this an SRS rather than a cramming tool.
 *
 * Cross-book: it asks `CardRepository` what is due and never mentions a book.
 * A card renders from the face stored on it, so a lemma learned in a book you
 * have since deleted still comes back.
 *
 * The due list is taken once, on arrival. Re-reading it after every answer
 * would mean a card graded `Nochmal` — now due in a minute — reappearing
 * immediately and the sitting never ending.
 */
export function Review() {
  const { cards, clock } = useRepositories()
  const goBack = useGoBack(LIBRARY)

  const due = useAsync(() => cards.listDue(clock.now()), [cards, clock])

  const [session, setSession] = useState<ReviewSession | null>(null)
  const [revealed, setRevealed] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (due.status === 'ready') setSession(startReview(due.value, clock.now()))
  }, [due, clock])

  const onGrade = useCallback(
    async (reviewGrade: ReviewGrade) => {
      if (!session || busy) return
      setBusy(true)
      try {
        const step = applyGrade(session, reviewGrade, clock.now())
        // The card is the durable part; there is no session row to keep. An
        // interrupted review resumes by asking what is still due.
        if (step.card) await cards.put(step.card)
        setSession(step.session)
        setRevealed(false)
      } finally {
        setBusy(false)
      }
    },
    [session, busy, cards, clock],
  )

  const back = { label: 'Bibliothek', onClick: goBack }

  if (due.status !== 'ready' || !session) {
    return <Screen title="Wiederholen" back={back}>{null}</Screen>
  }

  const view = buildReviewView(session)

  if (view.done) {
    return (
      <Screen title="Wiederholen" back={back}>
        <p className="text-lg">
          {view.total === 0
            ? 'Heute ist nichts fällig.'
            : `${view.total} Karten wiederholt.`}
        </p>
        <p className="text-ink-muted mt-2 text-sm">
          {view.total === 0
            ? 'Die nächsten Karten melden sich, wenn sie dran sind.'
            : 'Bis morgen.'}
        </p>
      </Screen>
    )
  }

  const card = view.card!

  return (
    <Screen title="Wiederholen" back={back}>
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
    </Screen>
  )
}
