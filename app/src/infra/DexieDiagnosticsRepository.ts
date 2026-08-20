import type { Table } from 'dexie'
import type {
  DiagnosticsRepository,
  ErrorLogEntry,
  ImportLogEntry,
  ImportLogOutcome,
} from '../domain/ports/DiagnosticsRepository'
import { db, type ErrorLogRow, type ImportLogRow, type MolcajeteDatabase } from './db'

const ERROR_LOG_CAP = 50
const IMPORT_LOG_CAP = 10

/**
 * Two append-only ring buffers. Each write is one `rw` transaction — add,
 * then delete whatever is past the cap by primary-key order — so a crash
 * mid-write can never leave a buffer over cap or lose the row just written.
 *
 * Rows are never edited, so the auto-increment `id` is already chronological;
 * `orderBy(':id').reverse()` gives newest-first for free, with no separate
 * timestamp index needed for a table this small.
 */
export class DexieDiagnosticsRepository implements DiagnosticsRepository {
  constructor(private readonly database: MolcajeteDatabase = db) {}

  async listErrors(): Promise<ErrorLogEntry[]> {
    const rows = await this.database.errorLog.orderBy(':id').reverse().toArray()
    return rows.map((row) => ({ id: row.id!, at: row.at, message: row.message, context: row.context }))
  }

  async recordError(entry: { at: Date; message: string; context: string }): Promise<void> {
    await this.appendCapped(this.database.errorLog, entry, ERROR_LOG_CAP)
  }

  async listImports(): Promise<ImportLogEntry[]> {
    const rows = await this.database.importLog.orderBy(':id').reverse().toArray()
    return rows.map((row) => ({ id: row.id!, at: row.at, outcome: row.outcome }))
  }

  async recordImport(entry: { at: Date; outcome: ImportLogOutcome }): Promise<void> {
    await this.appendCapped(this.database.importLog, entry, IMPORT_LOG_CAP)
  }

  private async appendCapped<T extends ErrorLogRow | ImportLogRow>(
    table: Table<T, number>,
    row: T,
    cap: number,
  ): Promise<void> {
    await this.database.transaction('rw', table, async () => {
      await table.add(row)
      const overflow = (await table.count()) - cap
      if (overflow > 0) {
        const stale = await table.orderBy(':id').limit(overflow).primaryKeys()
        await table.bulkDelete(stale)
      }
    })
  }
}
