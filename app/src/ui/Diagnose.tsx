import type { ReactNode } from 'react'
import { useRepositories } from '../app/repositories'
import { LIBRARY } from '../app/routes'
import { useAsync } from '../app/useAsync'
import { useGoBack } from '../app/useRoute'
import {
  readBuildFingerprint,
  readSchemaVersions,
  readServiceWorkerStatus,
  readStorageEstimate,
} from '../app/environment'
import { buildDiagnosticsView, type DiagnosticsView } from '../domain/view/diagnosticsView'
import {
  cards as cardsLabel,
  dateTime,
  describeImportLogOutcome,
  FSRS_STATE_LABELS,
  orUnknown,
  schemaStatus,
  serviceWorkerStatus,
  storageStatus,
} from './format'
import { Screen } from './Screen'

/**
 * SPEC's diagnostics screen for the device pass: read-only, no mutations
 * anywhere here. "What does the app actually think is true right now."
 *
 * One `useAsync` load gathers everything — every port plus the browser
 * environment reads — and hands it to `buildDiagnosticsView`, so this
 * component only renders (CLAUDE.md rule 5).
 */
export function Diagnose() {
  const { books, cards, known, sessions, diagnostics } = useRepositories()
  const goBack = useGoBack(LIBRARY)

  const state = useAsync<DiagnosticsView>(async () => {
    const [bookList, cardList, knownSources, sessionList, errors, imports, storage, serviceWorker, buildFingerprint] =
      await Promise.all([
        books.listBooks(),
        cards.listAll(),
        known.listAllWithSource(),
        sessions.listAll(),
        diagnostics.listErrors(),
        diagnostics.listImports(),
        readStorageEstimate(),
        readServiceWorkerStatus(),
        readBuildFingerprint(),
      ])

    const lexiconCounts = new Map(
      await Promise.all(
        bookList.map(async (book) => [book.id, await books.countLexiconEntries(book.id)] as const),
      ),
    )

    return buildDiagnosticsView({
      books: bookList,
      lexiconCounts,
      cards: cardList,
      knownLemmaSources: knownSources,
      sessions: sessionList,
      errors,
      imports,
      schemaVersion: readSchemaVersions(),
      storageEstimate: storage,
      serviceWorker,
      buildFingerprint,
    })
  }, [books, cards, known, sessions, diagnostics])

  const back = { label: 'Bibliothek', onClick: goBack }

  if (state.status === 'loading') {
    return <Screen title="Diagnose" back={back}>{null}</Screen>
  }
  if (state.status === 'failed') {
    return (
      <Screen title="Diagnose" back={back}>
        <p className="text-ink-muted mt-10 text-sm">Diagnose konnte nicht gelesen werden.</p>
      </Screen>
    )
  }

  const view = state.value

  return (
    <Screen title="Diagnose" back={back}>
      <Section title="Zustand">
        <Row label="Schema" value={schemaStatus(view.schema)} />
        <Row label="Service Worker" value={serviceWorkerStatus(view.serviceWorker)} />
        <Row label="Build-Hash" value={orUnknown(view.buildFingerprint.precacheRevision)} />
        <Row label="Speicher" value={storageStatus(view.storage)} />
      </Section>

      <Section title="Bücher">
        {view.books.length === 0 ? (
          <p className="text-ink-faint text-sm">Keine Bücher importiert.</p>
        ) : (
          view.books.map((book) => (
            <Row
              key={book.id}
              label={book.title}
              value={`${book.chapterCount} Kapitel · ${numbers(book.lexiconEntryCount)} Lexikoneinträge`}
              detail={book.id}
            />
          ))
        )}
      </Section>

      <Section title="Bekannte Lemmata">
        <Row label="Insgesamt" value={String(view.known.total)} />
        <Row label="Aus Ankisamen" value={String(view.known.seed)} />
        <Row label="Manuell / „Ich kenne das“" value={String(view.known.manual)} />
        <Row label="Nur durch gereifte Karte" value={String(view.known.maturedOnly)} />
        <Row label="Ohne bekannte Quelle (Altdaten)" value={String(view.known.legacy)} />
      </Section>

      <Section title="Karten">
        <Row label="Insgesamt" value={cardsLabel(view.cards.total)} />
        {(Object.keys(FSRS_STATE_LABELS) as (keyof typeof FSRS_STATE_LABELS)[]).map((state) => (
          <Row key={state} label={FSRS_STATE_LABELS[state]} value={String(view.cards.byState[state])} />
        ))}
        <Row
          label="Nächste Fälligkeit"
          value={view.cards.nextDueAt ? dateTime(view.cards.nextDueAt) : '—'}
        />
      </Section>

      <Section title="Laufende Sitzungen">
        {view.sessions.length === 0 ? (
          <p className="text-ink-faint text-sm">Keine.</p>
        ) : (
          view.sessions.map((session) => (
            <Row
              key={`${session.bookId}/${session.chapterIndex}`}
              label={`${session.bookTitle ?? session.bookId} · Kapitel ${session.chapterIndex + 1}`}
              value={`${session.phase} · ${session.passed}/${session.total} bestanden · ${session.remainingInQueue} in Warteschlange`}
              detail={dateTime(session.updatedAt)}
            />
          ))
        )}
      </Section>

      <Section title="Letzte Importe">
        {view.importHistory.length === 0 ? (
          <p className="text-ink-faint text-sm">Noch kein Import.</p>
        ) : (
          view.importHistory.map((entry) => (
            <Row
              key={entry.id}
              label={describeImportLogOutcome(entry.outcome)}
              value={dateTime(entry.at)}
            />
          ))
        )}
      </Section>

      <Section title="Fehler">
        {view.errors.length === 0 ? (
          <p className="text-ink-faint text-sm">Keine aufgezeichnet.</p>
        ) : (
          view.errors.map((entry) => (
            <Row
              key={entry.id}
              label={entry.message}
              value={entry.context}
              detail={dateTime(entry.at)}
            />
          ))
        )}
      </Section>
    </Screen>
  )
}

function numbers(value: number): string {
  return new Intl.NumberFormat('de-DE').format(value)
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-8 first:mt-0">
      <h2 className="text-ink-faint mb-2 text-xs tracking-wide uppercase">{title}</h2>
      <div className="divide-rule divide-y">{children}</div>
    </section>
  )
}

function Row({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-2 text-sm">
      <span className="min-w-0 truncate">{label}</span>
      <span className="text-ink-muted shrink-0 text-right font-mono text-xs">
        {value}
        {detail && <span className="text-ink-faint block">{detail}</span>}
      </span>
    </div>
  )
}
