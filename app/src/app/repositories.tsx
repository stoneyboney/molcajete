import { createContext, useContext, type ReactNode } from 'react'
import type { BookRepository } from '../domain/ports/BookRepository'
import type { ReadingPositionRepository } from '../domain/ports/ReadingPositionRepository'

export interface Repositories {
  books: BookRepository
  positions: ReadingPositionRepository
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
