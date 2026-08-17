import { createContext, useContext, type ReactNode } from 'react'
import type { BookRepository } from '../domain/ports/BookRepository'
import type { CardRepository } from '../domain/ports/CardRepository'
import type { Clock } from '../domain/ports/Clock'
import type { KnownLemmaRepository } from '../domain/ports/KnownLemmaRepository'
import type { ReadingPositionRepository } from '../domain/ports/ReadingPositionRepository'
import type { SessionRepository } from '../domain/ports/SessionRepository'

export interface Repositories {
  books: BookRepository
  positions: ReadingPositionRepository
  cards: CardRepository
  known: KnownLemmaRepository
  sessions: SessionRepository
  /** Not storage, but injected the same way and for the same reason. */
  clock: Clock
}

const RepositoryContext = createContext<Repositories | null>(null)

export function RepositoryProvider({
  repositories,
  children,
}: {
  repositories: Repositories
  children: ReactNode
}) {
  return (
    <RepositoryContext.Provider value={repositories}>
      {children}
    </RepositoryContext.Provider>
  )
}

/**
 * The single seam between the screens and storage. Components see the ports;
 * the Dexie implementations are injected once, in main.tsx.
 */
export function useRepositories(): Repositories {
  const value = useContext(RepositoryContext)
  if (!value) throw new Error('RepositoryProvider is missing')
  return value
}
