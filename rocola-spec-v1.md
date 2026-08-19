# Rocola — Spec v1

**A Spanish song-lyrics reader, forked from Molcajete.**

Status: draft, pre-implementation
Companion documents: `molcajete-spec-v1.md`, `rocola-CLAUDE.md`
Date: 2026-08

---

## 1. Purpose and scope

Rocola applies the Molcajete model — **pre-teach the vocabulary, then unlock the text** — to Spanish song lyrics. It is a *reading* app. Content selection is driven by the user's actual listening history via last.fm.

### 1.1 In scope

- Pan-Hispanic Spanish lyrics (not limited to Mexican music)
- Lyric text acquisition via LRCLIB, plain lyrics only
- Song selection driven by last.fm scrobble history
- Dialect-aware glossing with a configured home dialect (`es-MX`)
- Stanza-aware reader with tap-to-reveal glosses
- FSRS-scheduled flashcards, inherited unchanged from Molcajete

### 1.2 Explicit non-goals

These are **out of scope for v1** and should not be built speculatively:

- Time-synced lyrics, LRC parsing, karaoke display
- Audio playback of any kind; no embedded player
- Listening exercises, cloze, dictation ("de oído" mode — deferred)
- Forced alignment / Whisper / word-level timing
- Spotify Web Playback SDK, Apple MusicKit
- Any redistribution or bundling of lyric text (see §12)

### 1.3 Relationship to Molcajete

Rocola is a **fork at the app layer** and a **shared dependency at the prep layer**. See §5. The two apps may be merged later; nothing in this spec should make that merge harder.

---

## 2. Inherited from Molcajete, unchanged

Do not re-litigate these. They are settled.

| Concern | Decision |
|---|---|
| Platform | PWA first, with the four Swift-portability rules from `molcajete-spec-v1.md` §2 |
| Scheduling | FSRS via `ts-fsrs` |
| Card backs | German primary, English secondary |
| Session cap | 18 cards |
| Reader interaction | Tap-to-reveal only, plus a "reveal all glosses" toggle for second passes |
| Coverage display | Diagnostic with soft warning, **never a gate** |
| Gloss generation | `GlossProvider` interface; Ollama implementation is the default |
| Storage | Local-first; no server-side user data |

---

## 3. Removed from the Molcajete inheritance

Delete these code paths in the fork rather than leaving them dormant.

- **EPUB ingest.** No `epub` parsing, no DRM detection, no spine walking.
- **Chapter splitting.** A song's teach set is 12–20 lemmas, comfortably under the 18-card cap. **One song = one session.** The splitter is dead code.
- **Paragraph-based reader layout.** Replaced by the stanza model in §6.3.
- **Book-level progress tracking.** Replaced by per-track state.

---

## 4. New in Rocola

1. last.fm client and selection heuristic (§7.1)
2. Scrobble → LRCLIB matcher (§8) — *the highest-risk component*
3. Language filter (§7.3)
4. Variety (dialect) tagging and home-dialect rendering (§9)
5. Chorus-deduplicated teach-set builder (§7.4)
6. Stanza-aware reader (§10)
7. Deep-link out to a streaming app (§10.4)

---

## 5. Repository and package structure

### 5.1 The shared prep package

Extract the Molcajete prep pipeline into a standalone, locally pip-installable package **before** forking the app. Both projects depend on it by pinned version.

```
molcajete-prep/              # NEW shared package
  pyproject.toml
  src/molcajete_prep/
    __init__.py
    gloss/
      base.py                # GlossProvider ABC
      ollama.py
      claude_batch.py
    lexicon/
      wiktionary.py          # kaikki.org dump reader
      frequency.py           # wordfreq wrapper
    nlp/
      pipeline.py            # spaCy setup, lemmatisation
      normalise.py           # elision, orthographic variants
    teachset/
      builder.py             # frequency ranking, known-word filtering
      coverage.py
  tests/                     # the existing 333 tests move here

molcajete/                   # existing app repo
  depends on molcajete-prep==X.Y.Z

rocola/                      # NEW fork
  depends on molcajete-prep==X.Y.Z
  src/rocola_prep/
    lastfm/
    lrclib/
    matcher/
    langfilter/
    variety/
  app/                       # PWA
```

**Rationale.** Every gloss-quality improvement made in one repo would otherwise silently fail to land in the other. Divergence is invisible until the glosses in one app are noticeably worse. This extraction is an afternoon of work now and prevents a miserable reconciliation later.

### 5.2 What stays forked

The PWA app layer, the reader UI, and the session shell are genuinely different enough to fork. Do not attempt to share React components between the two apps in v1.

---

## 6. Data model

### 6.1 Track

```ts
interface Track {
  id: string;                  // internal UUID
  title: string;               // display form, from last.fm
  artist: string;              // display form, from last.fm
  album?: string;
  durationSec?: number;

  // normalised forms used for matching (see §8.1)
  titleNorm: string;
  artistNorm: string;

  // external identifiers
  mbid?: string;               // MusicBrainz, when last.fm supplies it
  spotifyTrackId?: string;     // for the deep link only
  lrclibId?: number;

  // selection metadata
  playcount30d: number;
  lastPlayedAt: string;        // ISO 8601

  language?: string;           // ISO 639-1, from the classifier
  languageConfidence?: number; // 0..1

  state: TrackState;
}

type TrackState =
  | 'candidate'      // selected from scrobbles, not yet matched
  | 'no_lyrics'      // matcher exhausted; retry monthly
  | 'not_spanish'    // classifier rejected
  | 'ready'          // lyrics + teach set built, not yet studied
  | 'teaching'       // flashcard session in progress
  | 'unlocked'       // reader available
  | 'archived';      // user dismissed
```

### 6.2 LyricDocument

Lyrics are stored as an ordered list of stanzas, each an ordered list of lines. Blank lines in the LRCLIB plain text are the stanza delimiter.

```ts
interface LyricDocument {
  trackId: string;
  source: 'lrclib' | 'manual';
  fetchedAt: string;
  stanzas: Stanza[];
  lineNotes: LineNote[];       // cultural / idiomatic annotations
}

interface Stanza {
  index: number;
  lines: Line[];
  repeatOf?: number;           // set when this stanza duplicates an earlier one
}

interface Line {
  index: number;               // global line index within the document
  text: string;                // raw, as fetched
  tokens: Token[];
}

interface Token {
  surface: string;             // as written, e.g. "pa'"
  normalised: string;          // e.g. "para"
  lemma: string;
  pos: string;
  senseId?: string;            // null for words the user already knows
  isElided: boolean;
}
```

### 6.3 Sense — the variety extension

This is the significant schema change from Molcajete.

```ts
type Variety =
  | 'general'   // pan-Hispanic, no regional marking
  | 'es-MX' | 'es-AR' | 'es-ES' | 'es-CO' | 'es-CL'
  | 'es-PE' | 'es-VE' | 'es-PR' | 'es-DO' | 'es-CU'
  | 'es-UY' | 'es-EC' | 'es-GT' | 'es-BO' | 'es-PY'
  | 'es-CR' | 'es-PA' | 'es-HN' | 'es-SV' | 'es-NI';

type Register =
  | 'neutral' | 'coloquial' | 'vulgar' | 'poetic' | 'arcaic' | 'albur';

interface Sense {
  id: string;
  lemma: string;
  pos: string;

  glossDe: string;             // primary card back
  glossEn: string;             // secondary card back

  variety: Variety;
  register: Register;

  // Populated only when variety !== 'general' && variety !== homeDialect.
  // The equivalent term in the user's home dialect, if one exists.
  homeEquivalent?: string;
  homeEquivalentNote?: string;

  // Recognition-only morphology (voseo, vosotros). See §9.3.
  morphNote?: string;

  provider: 'wiktionary-en' | 'wiktionary-de' | 'ollama' | 'manual';
  confidence?: number;
}
```

### 6.4 Configuration

```ts
interface RocolaConfig {
  homeDialect: Variety;          // default: 'es-MX'
  l1: 'de';
  l2: 'en';

  // selection
  minPlaycount: number;          // default 3
  selectionWindowDays: number;   // default 30

  // coverage
  coverageWarnThreshold: number; // default 0.95 — NOT 0.90, see §11.2

  // language filter
  minLanguageConfidence: number; // default 0.80
}
```

---

## 7. Pipeline

Six stages. Each is independently runnable and idempotent.

### 7.1 Stage 1 — Selection (last.fm)

**Heuristic:** a track becomes a `candidate` when it has been played **≥ `minPlaycount` times within `selectionWindowDays`**.

Endpoints:

- `user.getRecentTracks` — paginated, for the rolling window. Page size 200. Walk back until `lastPlayedAt < now - selectionWindowDays`, then stop.
- `user.getTopTracks` with `period=1month` / `3month` — for stable favourites that may fall below the recent-window threshold but are clearly part of the rotation.

Notes:

- last.fm read endpoints need only an API key; no OAuth flow. Keep the key in local config, never in the repo.
- Pace requests politely; do not parallelise aggressively.
- `user.getRecentTracks` may include a currently-playing track with a `nowplaying` attribute and no timestamp. **Skip it** — it will reappear as a normal scrobble.
- Deduplicate by `mbid` when present, else by `(artistNorm, titleNorm)`.

### 7.2 Stage 2 — Matching (LRCLIB)

See §8 for the full algorithm. Output: `plainLyrics` string, or state `no_lyrics`.

**Only `plainLyrics` is requested and stored.** `syncedLyrics` is explicitly discarded even when returned, per §1.2.

### 7.3 Stage 3 — Language filter

Run **after** lyric fetch, on the lyric text itself. Do not filter on last.fm artist tags — they are noisy and mishandle bilingual artists.

- Library: `lingua-py` (preferred — better on short texts) or `fasttext`. Both local.
- Restrict the candidate language set to `{es, en, pt, ca, gl, it, fr}` to sharpen discrimination.
- Accept when `language == 'es' && confidence >= minLanguageConfidence`.
- Spanglish tracks resolve naturally by confidence score. A track at 0.6 Spanish is genuinely mixed; surface it to the user as a manual-review item rather than auto-rejecting.

### 7.4 Stage 4 — Teach-set build

Inherited from `molcajete_prep.teachset.builder`, with **one Rocola-specific change**:

> **Chorus deduplication.** Count word types against the set of *unique lines*, not raw token stream.

Algorithm:

1. Hash each line on its normalised, accent-folded, punctuation-stripped text.
2. Build `uniqueLines` = first occurrence of each hash, in document order.
3. Mark subsequent occurrences with `repeatOf` at the stanza level where a whole stanza repeats.
4. Run frequency ranking and known-word filtering **over `uniqueLines` only**.

**Why this matters.** A chorus sung five times inflates its vocabulary fivefold in the raw token stream. Without this, the builder teaches the hook and skips the verses — which is precisely backwards, since the hook is the part repetition will teach you for free.

### 7.5 Stage 5 — Gloss and variety tagging

Provider order: English Wiktionary → German Wiktionary → Ollama fallback.

Wiktionary provides `glossEn` and often regional labels, but its labelling is inconsistent. **The Ollama provider is authoritative for `variety`, `register`, and `homeEquivalent`.** Run it for every sense, even when Wiktionary supplied a gloss, if the Wiktionary entry carries any regional label at all.

Ollama response schema (strict JSON, no prose, no markdown fences):

```json
{
  "lemma": "pibe",
  "pos": "NOUN",
  "glossDe": "Junge, Kerl",
  "glossEn": "kid, guy",
  "variety": "es-AR",
  "register": "coloquial",
  "homeEquivalent": "chavo",
  "homeEquivalentNote": "In Mexiko sagt man 'chavo' oder 'morro' (Norden).",
  "morphNote": null,
  "confidence": 0.9
}
```

Prompt requirements:

- State the home dialect explicitly in the system prompt.
- Instruct: if the term is pan-Hispanic, `variety` **must** be `general` and `homeEquivalent` **must** be null. Over-tagging is the expected failure mode; guard against it.
- Instruct: `homeEquivalent` is the term a speaker in the home dialect would actually use, or null if the home dialect uses the same word.
- Require `glossDe` first — the model produces better German when it is not translating from its own English output.

### 7.6 Stage 6 — Coverage diagnostic

Unchanged mechanism, changed threshold. See §11.2.

---

## 8. The matcher

The highest-risk component. last.fm scrobbles are user-submitted and inconsistent; LRCLIB's `/api/get` matches strictly.

### 8.1 Normalisation

Applied to both title and artist. **Preserve the original for display** — normalisation is for matching only.

Ordered rules:

1. Unicode NFKC, then lowercase.
2. Strip trailing parenthetical and bracketed qualifiers matching a stop-list: `remaster(ed)?`, `\d{4} remaster`, `single version`, `album version`, `radio edit`, `live`, `demo`, `bonus track`, `deluxe`, `explicit`, `clean`, `mono`, `stereo`, `en vivo`, `versión .*`, `remix`.
   - **Do not** strip parentheticals that are part of the actual title. Only strip when the parenthetical content matches the stop-list.
3. Strip `feat.` / `ft.` / `con ` clauses from the **title**; retain the primary artist only in `artist`.
4. Normalise dash variants (`–`, `—`, `‑`) to `-`, then strip trailing ` - <stop-list term>` suffixes.
5. Collapse whitespace.
6. Accent-fold for the comparison key **only** (`á→a`, `ñ→n`). Keep the accented form in `titleNorm` for display fallback; store a separate `titleKey` for fuzzy comparison.

### 8.2 Lookup ladder

```
1. GET /api/get
     ?track_name=&artist_name=&album_name=&duration=
   → exact match, all fields. Highest precision.

2. GET /api/get  (omit album, omit duration)
   → many scrobbles carry no album; duration is often absent or wrong.

3. GET /api/search?track_name=&artist_name=
   → returns candidate list. Score each candidate:
       titleKey similarity   (weight 0.5)  — token-set ratio
       artistKey similarity  (weight 0.35)
       duration proximity    (weight 0.15) — only if both known;
                                             full credit within ±3s
     Accept the top candidate at score ≥ 0.85.
     Between 0.70 and 0.85 → queue for manual confirmation.
     Below 0.70 → reject.

4. GET /api/search?q=<artist + title>
   → last resort, same scoring.

5. → state = 'no_lyrics'
```

### 8.3 Caching

- Cache **hits and misses** in local storage, keyed on `(artistKey, titleKey)`.
- A miss is expensive to rediscover — do not re-run the full ladder on every pipeline pass.
- **Re-check misses monthly.** LRCLIB is crowdsourced and grows; a track with no lyrics today may have them in six weeks.
- Cache the resolved `lrclibId` and prefer `/api/get-by-id` on subsequent fetches.

### 8.4 Client requirements

- Send a `User-Agent` header identifying the application, name and version, per LRCLIB's request. It costs nothing and it is asked for.
- Handle `instrumental: true` → state `no_lyrics`, do not retry.
- Treat the API as best-effort. Missing fields are normal; never assume a field is present.

### 8.5 Manual fallback

The user can paste lyric text for any track, producing `source: 'manual'`. This is the escape hatch for regional and independent music with thin LRCLIB coverage, and it is the only path guaranteed to work for any track.

---

## 9. Dialect handling

### 9.1 The problem being solved

Molcajete could assume every gloss was Mexican. Rocola cannot. A pan-Hispanic rotation pulls in `vosotros` from Spanish rock, `voseo` from Argentine rock nacional, Caribbean vocabulary from Puerto Rican and Dominican tracks. Untagged, these enter the FSRS queue with the same weight as Monterrey vocabulary — and the user produces the wrong regional term in a Monterrey family setting.

**Rocola must let the user read anything while only reinforcing what they need to produce.**

### 9.2 Card back rendering

Given `homeDialect = 'es-MX'`:

| Sense variety | Rendering |
|---|---|
| `general` | German gloss / English gloss. No marker. |
| `es-MX` (= home) | German gloss / English gloss. No marker. |
| Any other | German gloss / English gloss · **variety badge** · `MX: <homeEquivalent>` when present |

Example card back for `pibe`:

```
Junge, Kerl
kid, guy
🇦🇷 AR · coloquial
MX: chavo, morro
```

The badge is visually subordinate to the gloss — it is context, not the answer.

### 9.3 Recognition-only morphology

Verb forms from `voseo` (`sos`, `tenés`, `querés`, `vení`) and `vosotros` (`sois`, `tenéis`, `venid`) must be **recognisable but never drilled for production**.

- Tag these senses with `morphNote` explaining the form and giving the home-dialect equivalent.
- Mark the card as **recognition-only**: the card is shown Spanish-front only. Never generate a German-front → Spanish-back card for a non-home-dialect form.
- This flag lives on the card, not the sense, and is set at card-generation time from `variety`.

### 9.4 A note on `wordfreq`

`wordfreq`'s `es` corpus is pan-Hispanic. Under Molcajete this was a mild compromise. Under Rocola it is correct — no change needed, but do not "fix" it later by filtering to Mexican sources.

---

## 10. Reader

### 10.1 Layout

Stanza-aware. Blank-line-separated blocks, generous vertical rhythm, line breaks preserved exactly as fetched. Lyrics are not prose and must not be reflowed into paragraphs.

Repeated stanzas (`repeatOf` set) render normally but are visually de-emphasised — a subtle left rule or reduced opacity — signalling "you have seen this".

### 10.2 Interaction

Inherited unchanged: **tap-to-reveal only**, plus a "reveal all glosses" toggle for second passes.

Tapping a token with a `senseId` reveals an inline gloss chip below the line. Elided tokens (`isElided`) additionally show the written form: `pa'` → `para`.

### 10.3 Line notes

New surface. A stanza or line may carry a `LineNote` for content that is not a vocabulary item — idiom, double meaning, cultural reference, historical allusion.

- Rendered as a discreet marginal marker, expanded on tap.
- v1: **manually authored only.** Do not auto-generate these. An LLM-generated cultural note that is confidently wrong is worse than no note.
- The `Genius` annotation API is a legitimate future source (it exposes annotations, not lyric text) — noted for v2, not built now.

### 10.4 Streaming deep link

Store `spotifyTrackId` where the scrobble supplies it. Render a single "escuchar" link that opens the track in the user's streaming app.

No embedded player, no SDK, no OAuth beyond what selection already requires. Zero integration cost; lets the user play the song in whatever app they are already using while reading.

---

## 11. Sessions and progression

### 11.1 One song, one session

A song's teach set is 12–20 lemmas. The 18-card cap is retained but will rarely bind. If a track exceeds 18 unknown lemmas, **do not split the song** — instead surface it as "dense" and let the user choose to study it across two sessions or skip it. Splitting a song mid-verse is incoherent in a way that splitting a chapter is not.

### 11.2 Coverage threshold

**Default `coverageWarnThreshold` = 0.95**, up from Molcajete's 0.90.

Rationale: 0.90 was calibrated on prose, where surrounding context carries the reader through unknown words. Songs are far more elliptical — sparse syntax, ellipsis, deliberate ambiguity. 0.90 coverage in a song feels materially worse than 0.90 in a chapter.

This remains a **diagnostic with a soft warning, never a gate.** Revisit after roughly a dozen songs and tune against felt experience.

---

## 12. Legal and storage posture

Mirrors the Molcajete "DRM-free EPUB only" rule.

> **Rocola never bundles, ships, or redistributes lyric text.** Lyrics are fetched at runtime from LRCLIB or supplied by the user, and stored only in local user storage on the user's own device.

Consequences, binding on implementation:

- No lyric text in the repository, in fixtures, in test data, or in this or any other spec document. **Tests use synthetic Spanish text.**
- No server-side lyric cache. No sync of lyric content between devices.
- No export path that emits lyric text in bulk.
- Anki export contains **vocabulary cards only** — lemma, glosses, variety, register. A single illustrative line of context per card is acceptable; whole stanzas are not.

---

## 13. Anki export

Retains the established conventions.

- Deck: `Spanisch::Rocola::[Artist]`
- Tags: shared category tag `rocola` plus a per-track tag
- Note type: `Basic`, HTML formatting on the back
- Back layout: German gloss, English gloss, variety badge, home equivalent, one context line
- Format: tab-separated `.txt` with header directives (the reliable path from the claude.ai web interface); AnkiConnect via `addNotes` when running locally from Claude Desktop or Claude Code
- **Create the deck before calling `addNotes`** — adding to a non-existent deck fails silently

---

## 14. Build phases

**Phase 0 — Extraction.** Pull `molcajete-prep` out as a shared package. Move the existing tests. Repoint Molcajete at the pinned version. Confirm all 333 tests still pass. *Nothing else starts until this is green.*

**Phase 1 — Coverage probe.** Before building anything: pull ~50 Spanish tracks from real last.fm history, run them through the normaliser and the lookup ladder, and count hits. This number determines whether the LRCLIB path is viable or whether manual paste is the primary route. **It is cheap and it changes the plan.**

**Phase 2 — Pipeline.** last.fm client → matcher → language filter → teach-set builder → gloss + variety tagging. CLI only, no UI. Output: JSON per track, plus the Anki `.txt`.

**Phase 3 — App.** Fork the PWA. Strip EPUB and chapter splitting. Build the stanza reader and the variety-aware card back. Wire FSRS.

**Phase 4 — Polish.** Line notes, manual paste UI, dense-track handling, deep links.

---

## 15. Open questions

1. **Coverage probe result.** Unknown until Phase 1. If LRCLIB hit rate on the real rotation is below ~50%, manual paste becomes the primary path and the matcher's priority drops sharply.
2. **Ollama over-tagging.** Expect the model to mark pan-Hispanic words as regional. Needs a held-out eval set of ~100 known-general lemmas to measure the false-positive rate before trusting `variety` in production.
3. **Cross-track sense identity.** When `corazón` appears in ten songs, it is one sense and one card. Molcajete's sense-keying is per-lemma-per-POS and should carry over — but confirm it does not silently key on document ID.
4. **Home-dialect switching.** Config allows it, but the `homeEquivalent` fields are generated against one home dialect at gloss time. Switching later requires a re-gloss pass. Acceptable for v1; document the limitation.
5. **Multi-artist tracks.** Collaborations scrobble inconsistently. The `feat.` stripping in §8.1 handles the common case; genuinely co-billed tracks (`A & B`) may need a fallback that tries each artist separately.
