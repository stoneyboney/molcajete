import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

/**
 * The bundle the pipeline's own test suite produces, read from `bundles/`
 * rather than copied here. One file, one source of truth: if the pipeline
 * changes what it emits, these tests see it on the next run instead of
 * agreeing with a stale copy.
 */
const FIXTURE_PATH = fileURLToPath(
  new URL('../../bundles/anonimo-los-del-cerro.molcajete.json', import.meta.url),
)

export function readFixtureText(): string {
  return readFileSync(FIXTURE_PATH, 'utf8')
}

/** A fresh mutable copy, so a test that edits it cannot affect its neighbours. */
export function readFixture(): Record<string, any> {
  return JSON.parse(readFixtureText())
}
