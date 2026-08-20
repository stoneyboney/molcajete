/**
 * Reads about the browser environment, for `#/diagnose` only.
 *
 * Plain async functions, not behind a port: there is no second implementation
 * this would ever need — no Swift port will implement "read
 * `navigator.storage.estimate()`" — so wrapping it in DI would be ceremony
 * without payoff. This mirrors `importFile.ts` already sitting outside
 * `domain/` as unwrapped app-layer orchestration.
 *
 * Importing `db` directly here is not a layering violation: this file is app
 * wiring, exactly like `main.tsx`, which already imports the Dexie
 * repositories directly. The rule that matters is "no *component* and no
 * *domain* function imports Dexie" — neither is true here.
 */

import { db, EXPECTED_SCHEMA_VERSION } from '../infra/db'

export function readSchemaVersions(): { live: number; expected: number } {
  return { live: db.verno, expected: EXPECTED_SCHEMA_VERSION }
}

export async function readStorageEstimate(): Promise<{
  usageBytes: number | undefined
  quotaBytes: number | undefined
  supported: boolean
}> {
  if (typeof navigator === 'undefined' || !navigator.storage?.estimate) {
    return { usageBytes: undefined, quotaBytes: undefined, supported: false }
  }
  try {
    const { usage, quota } = await navigator.storage.estimate()
    return { usageBytes: usage, quotaBytes: quota, supported: true }
  } catch {
    return { usageBytes: undefined, quotaBytes: undefined, supported: true }
  }
}

export async function readServiceWorkerStatus(): Promise<{
  supported: boolean
  registered: boolean
  waiting: boolean
}> {
  if (typeof navigator === 'undefined' || !navigator.serviceWorker) {
    return { supported: false, registered: false, waiting: false }
  }
  try {
    const registration = await navigator.serviceWorker.getRegistration()
    return {
      supported: true,
      registered: registration?.active != null,
      waiting: registration?.waiting != null,
    }
  } catch {
    return { supported: true, registered: false, waiting: false }
  }
}

/**
 * "The build hash controlling the page." Workbox names its precache cache
 * with a `-precache-` segment and stores each cached entry's revision as a
 * `__WB_REVISION__` query parameter on the cache key — a content hash of
 * `index.html`, whose own contents include that build's hashed JS/CSS
 * filenames, so it changes every build. This is an undocumented Workbox
 * convention, not a public API — read defensively; a future Workbox upgrade
 * changing the internal key format should make this field go blank, not
 * break the screen.
 */
export async function readBuildFingerprint(): Promise<{
  cacheNames: string[]
  precacheRevision: string | undefined
}> {
  if (typeof caches === 'undefined') {
    return { cacheNames: [], precacheRevision: undefined }
  }
  try {
    const cacheNames = await caches.keys()
    const precacheName = cacheNames.find((name) => name.includes('precache'))
    if (!precacheName) return { cacheNames, precacheRevision: undefined }

    const cache = await caches.open(precacheName)
    const requests = await cache.keys()
    const indexEntry = requests.find((request) =>
      new URL(request.url).pathname.endsWith('index.html'),
    )
    const precacheRevision =
      indexEntry === undefined
        ? undefined
        : (new URL(indexEntry.url).searchParams.get('__WB_REVISION__') ?? undefined)

    return { cacheNames, precacheRevision }
  } catch {
    return { cacheNames: [], precacheRevision: undefined }
  }
}
