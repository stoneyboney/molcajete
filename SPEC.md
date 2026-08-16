# Molcajete — Technical Specification v1.0

**A pre-teaching Spanish reader for iPhone and iPad**

Personal tool. Single user. Offline-first. Spanish (Mexican) as target language, German and English as native languages.

### On the name

A *molcajete* is the basalt mortar and pestle of Mexican kitchens, from Nahuatl *molcaxitl*. You grind things down before you consume them — which is exactly what this app does with a chapter's vocabulary. The word carries no negative slang, is unmistakably Mexican rather than merely Spanish, and in Monterrey it is also a restaurant dish, so it lands warmly with native speakers.

Home-screen label: `Molcajete` (10 characters, fits without truncation).
Bundle extension: `.molcajete.json`.

---

## 1. The core idea

Every existing reader app is *reactive*: you read, you hit a wall, you tap the word, you review it later. Molcajete is *proactive*: before you are allowed into a chapter, the app teaches you the vocabulary that chapter actually requires, using spaced-repetition flashcards. You then read the chapter with ~98% word coverage, which is the threshold at which reading becomes pleasant rather than effortful.

**The one-sentence spec:** *EPUB in → chapter-scoped flashcard sessions → comfortable reading, offline, on the sofa and on the train.*

---

## 2. Scope

### In scope for v1
- Import a prepared book bundle
- Pre-chapter vocabulary teaching with FSRS scheduling
- Distraction-free reader with tap-to-gloss
- Full offline operation after import
- Seeding "known words" from an existing Anki collection
- ES / DE / EN on every card

### Explicitly out of scope for v1
- Audio and read-along
- Any account system, server, or sync
- Any network call at runtime
- Grammar explanation features
- Multiple users, multiple target languages
- App Store distribution

### Non-goals, permanently
- Gamification, streaks, leaderboards
- Replacing Anki for non-reading vocabulary

---

## 3. Architecture

The single most important design decision: **split the system in two.**

```
┌─────────────────────────────────────┐
│  PREP PIPELINE (Python, desktop)    │
│  Run once per book. Network OK.     │
│                                     │
│  EPUB ──▶ chapters ──▶ lemmas       │
│       ──▶ frequency ──▶ glosses     │
│       ──▶ book.molcajete.json          │
└──────────────┬──────────────────────┘
               │  (AirDrop / iCloud Drive / file picker)
               ▼
┌─────────────────────────────────────┐
│  READER PWA (TypeScript, on device) │
│  Zero network. IndexedDB.           │
│                                     │
│  import ──▶ teach ──▶ read ──▶ SRS  │
└─────────────────────────────────────┘
```

**Why this split matters:**

1. All the hard linguistic work (lemmatization, dictionary lookup, frequency ranking) happens where the mature Python libraries live, on a machine with a keyboard and no battery anxiety.
2. The app becomes almost trivially simple — it renders pre-computed JSON. No EPUB parser on device, no NLP on device, no network.
3. The bundle format is the stable contract. **If you later rewrite the app natively in Swift, the prep pipeline is untouched and the bundles still work.** This is the migration insurance.

---

## 4. Bundle format (`*.molcajete.json`)

This is the contract between the two halves. Version it from day one.

```jsonc
{
  "schemaVersion": 1,
  "book": {
    "id": "villalobos-fiesta-madriguera",
    "title": "Fiesta en la madriguera",
    "author": "Juan Pablo Villalobos",
    "language": "es",
    "variant": "es-MX",
    "totalTokens": 21430,
    "uniqueLemmas": 3120
  },
  "chapters": [
    {
      "index": 0,
      "title": "Capítulo 1",
      "tokenCount": 3200,
      "paragraphs": [
        {
          "id": "c0p0",
          "tokens": [
            { "s": "Algunas", "l": "alguno", "p": "DET", "t": 4012 },
            { "s": " ", "ws": true },
            { "s": "personas", "l": "persona", "p": "NOUN", "t": 118 }
          ]
        }
      ],
      "teachSet": ["m0031", "m0044", "m0102"],
      "glossOnly": ["m0777", "m0778"]
    }
  ],
  "lexicon": {
    "m0031": {
      "lemma": "madriguera",
      "pos": "NOUN",
      "de": "Bau, Höhle",
      "en": "burrow, den",
      "zipf": 2.9,
      "bookCount": 14,
      "firstChapter": 0,
      "mexicanism": false,
      "example": {
        "es": "Mi papá dice que somos gente de la madriguera.",
        "de": "Mein Vater sagt, wir sind Leute des Baus.",
        "chapterIndex": 0
      }
    },
    "m0102": {
      "lemma": "chido",
      "pos": "ADJ",
      "de": "cool, super",
      "en": "cool, great",
      "zipf": 2.1,
      "bookCount": 6,
      "mexicanism": true,
      "regionNote": "MX, coloquial"
    }
  }
}
```

**Token fields** are deliberately terse because they dominate file size:
`s` = surface form, `l` = lemma id or lemma string, `p` = POS tag, `t` = lexicon key, `ws` = whitespace-only token.

**Size expectation:** a 70-page novel lands around 1.5–4 MB uncompressed. Gzip the file; IndexedDB stores the parsed object. Well within iOS limits.

---

## 5. The vocabulary selection algorithm

This is the heart of the app and the part most worth getting right. Naively teaching every unknown word in a chapter produces 200-card sessions and abandonment.

### Step 1 — Determine the unknown set
```
unknown(chapter) = lemmas(chapter) − knownLemmas(user)
```
`knownLemmas` is seeded from Anki (see §8) and grows as cards mature.

### Step 2 — Classify each unknown lemma

| Condition | Action |
|---|---|
| `bookCount >= 3` | **Teach** — you will meet it repeatedly, a card pays for itself |
| `zipf >= 3.5` (roughly top 5000 words) | **Teach** — high general utility |
| `mexicanism == true` and `bookCount >= 2` | **Teach** — this is why you're here |
| Proper noun (`p == "PROPN"`) | **Skip entirely** — no card, no gloss needed |
| Everything else | **Gloss only** — tap-to-reveal inline, no card |

### Step 3 — Cap and split
- Hard cap: **18 new cards per teaching session**
- If `teachSet(chapter) > 18`, split the chapter into 2+ reading segments with their own sessions
- Sort the teach set by `bookCount` descending — most useful words first, so a partial session still helps

### Step 4 — Coverage gate (optional, configurable)
Before unlocking a chapter, compute projected coverage:
```
coverage = (tokens whose lemma ∈ known ∪ justTaught) / totalTokens
```
Default target: **0.98**. If below target after the teach set, warn but allow entry — never hard-block. This is a personal tool; you are an adult.

---

## 6. Screen flow

Five screens. That's the whole app.

### 6.1 Library
Grid of imported books. Each shows: cover colour block, title, `Chapter 4 of 12`, and a small progress ring. Primary action button: **Import book** (file picker, accepts `.molcajete.json`).

Empty state doubles as the Anki-seed prompt.

### 6.2 Chapter list
Vertical list of chapters. Each row: title, token count, and a status chip:
- `Ready to learn` — teach set computed, not yet studied
- `18 cards to learn` — session pending
- `Read` — completed
- `Due: 12` — review cards from this chapter are due

Tapping a locked chapter opens the teaching session; tapping an unlocked one opens the reader.

### 6.3 Teaching session
One card at a time, full screen.

**Introduction phase** (first exposure to a card):
```
        madriguera
        ─────────────
        DE   der Bau, die Höhle
        EN   burrow, den
        
        „Mi papá dice que somos
         gente de la madriguera."
        
        [ Ich kenne das ]  [ Weiter ]
```
"Ich kenne das" marks it known immediately and removes it from the session — this is essential, it's how you burn through the 40% of words you already have.

**Recall phase** (after all introductions):
Spanish front → tap to reveal → four FSRS buttons (`Nochmal / Schwer / Gut / Leicht`).

Session ends when every card in the teach set has been answered `Gut` or better once. Typical duration: 6–10 minutes.

### 6.4 Reader
Serif type, generous line height, warm off-white background, no chrome except a thin progress bar. Paragraph-level rendering from the token array.

- Words in `glossOnly` for this chapter: subtle dotted underline
- Tap any word → bottom sheet with lemma, DE, EN, and `Add card` button
- Long-press → select phrase, no translation, just a note-to-self bookmark
- End of chapter → `Chapter complete` → returns to chapter list, unlocks next

### 6.5 Review
Daily due cards across all books. Same FSRS interface as the recall phase. This screen is what makes it a real SRS rather than a cramming tool.

---

## 7. Spaced repetition

Use **FSRS** via the `ts-fsrs` npm package. Do not write your own scheduler.

- Card states: `New → Learning → Review → Relearning`
- Store the full FSRS card object (`due`, `stability`, `difficulty`, `elapsed_days`, `scheduled_days`, `reps`, `lapses`, `state`, `last_review`)
- A lemma is considered **known** when `state == Review && stability > 21` days, or when manually marked via "Ich kenne das"
- Retention target: 0.90 (the FSRS default)

**Card direction:** ES → DE/EN only (recognition). Reading is a recognition task; production cards double your workload for no reading benefit. Keep production practice in your existing Anki decks.

---

## 8. Anki seeding

Without this, chapter one tries to teach you *correr*, *ganas* and *chido* and the app feels stupid.

1. In Anki: `File → Export → Notes in Plain Text (.txt)`, include your `Spanisch::` decks
2. Prep script `seed_known.py` reads the file, takes the Spanish field, lemmatizes each entry with spaCy, emits `known.json` — a flat array of lemma strings
3. App imports `known.json` on first launch; those lemmas are pre-marked known and never enter a teach set

Re-runnable at any time; merges rather than replaces.

---

## 9. Tech stack

### Prep pipeline (Python 3.11+)
| Concern | Library |
|---|---|
| EPUB parsing | `ebooklib` + `BeautifulSoup` |
| Tokenize + lemmatize | `spaCy` with `es_core_news_sm` |
| Frequency data | `wordfreq` (`zipf_frequency(word, 'es')`) |
| DE/EN glosses | Wiktionary extracts from kaikki.org (`kaikki.org/dictionary/Spanish`) |
| Gloss fallback + Mexican flagging | Claude API, batched (see §11) |

### Reader PWA
| Concern | Choice |
|---|---|
| Framework | React 18 + TypeScript + Vite |
| Storage | IndexedDB via `Dexie.js` |
| Offline shell | `vite-plugin-pwa` (Workbox) |
| SRS | `ts-fsrs` |
| Styling | Tailwind |
| Install | Safari → Share → Add to Home Screen |

### Hosting
GitHub Pages or Netlify free tier. The PWA is static files; it needs a URL once, to install. After that it runs from the home screen offline.

---

## 10. Designing now for a native rewrite later

You asked to keep the native door open. Four rules make that migration cheap rather than a rewrite:

1. **Keep the bundle format app-agnostic.** It is plain JSON with no web assumptions. A Swift decoder is an afternoon's work.
2. **Isolate domain logic in pure TypeScript.** Put `selectTeachSet()`, `computeCoverage()`, `scheduleCard()` in `src/domain/` with zero React and zero DOM imports. These are the algorithms worth preserving; they port to Swift almost line-by-line.
3. **Put all storage behind one interface.** Define `BookRepository` and `CardRepository` as TypeScript interfaces, with a Dexie implementation behind them. In Swift the same interfaces get a SwiftData implementation.
4. **Never let view code compute anything.** Components receive fully-prepared view models. This keeps the porting surface to "rebuild the screens", which is exactly the part you'd *want* to rebuild natively.

If you follow these, the native version reuses the prep pipeline entirely, translates ~600 lines of domain logic, and rebuilds five screens in SwiftUI.

---

## 11. Which Claude model and settings to use

Two distinct uses. Don't conflate them.

### 11.1 Building the app

**Tool: Claude Code**, not the chat interface. This is a multi-file project with a build step; an agentic coding tool that reads and writes your repo directly is a different category of useful.

**Model: Claude Opus 5** (`claude-opus-5`). The official docs recommend starting with Opus 5 for complex agentic coding. It has a 1M-token context window and a May 2026 knowledge cutoff — the most recent of any current model, which matters for library APIs.

**Settings:**
- The `effort` parameter defaults to `high` on Opus 5 in both the Claude API and Claude Code. Leave it there for architecture and initial scaffolding; drop it for mechanical edits.
- Drop to **Claude Sonnet 5** (`claude-sonnet-5`) for iteration once the architecture is settled — same 1M context, roughly half the cost, faster.

**Working method that suits "spec it and have it generated":**
1. Put this document in the repo as `SPEC.md`
2. Add a `CLAUDE.md` with the four native-migration rules from §10 as hard constraints
3. Build in the phase order from §12, one phase per session, committing between
4. Ask for tests on `src/domain/` — that's the code you'll port later, so it's the code worth pinning down

### 11.2 Inside the prep pipeline

Only if Wiktionary coverage disappoints. Use it for two jobs: filling gloss gaps, and flagging Mexican regional usage.

- **Model: Claude Sonnet 5** — glossing is not a hard reasoning task, and you'll send thousands of lemmas
- **Use the Message Batches API** — 50% discount, and you have no latency requirement on a script you run once per book
- **Use prompt caching** — the system prompt and instructions are identical across every call
- Consider **Claude Haiku 4.5** (`claude-haiku-4-5`) if volume gets large and quality holds; test on 200 lemmas first

### 11.3 Current model reference (August 2026)

| Model | API ID | Price /MTok in-out | Context |
|---|---|---|---|
| Claude Fable 5 | `claude-fable-5` | $10 / $50 | 1M |
| Claude Opus 5 | `claude-opus-5` | $5 / $25 | 1M |
| Claude Sonnet 5 | `claude-sonnet-5` | $2 / $10 | 1M |
| Claude Haiku 4.5 | `claude-haiku-4-5` | $1 / $5 | 200k |

Fable 5 is overkill here — it's built for long-running agentic work, and this project doesn't need it.

Verify before you budget: https://platform.claude.com/docs/en/about-claude/pricing

---

## 12. Build phases

Each phase should end with something you can actually use.

**Phase 1 — Prep pipeline skeleton**
EPUB → chapters → tokens → lemmas → JSON, with frequency from `wordfreq` and no glosses yet. Success: a valid bundle for one book.

**Phase 2 — Glosses**
Wire in Wiktionary extracts, DE and EN. Add Claude batch fallback. Success: >95% of teach-set lemmas have a German gloss.

**Phase 3 — Reader shell**
React app, import a bundle, render chapters, tap-to-gloss. No SRS yet. Success: you read chapter one on your iPad, offline.

**Phase 4 — Teaching loop**
Teach-set selection, introduction phase, FSRS recall phase, chapter gating. Success: you learn 18 words then read the chapter and notice the difference.

**Phase 5 — Anki seed + review screen**
Import `known.json`, add cross-book daily review. Success: the app stops teaching you words you already know.

**Phase 6 — Polish**
Coverage display, reading statistics, export mined words back to Anki as TSV.

---

## 13. Settled decisions

1. **Glosses: German primary, English secondary.** Both are stored in the lexicon. German renders large; English renders small beneath it. English comes free with the kaikki.org extract (which derives from English Wiktionary), so storing it costs nothing; German is produced by the Claude batch pass either way. English earns its place as a disambiguator when the German gloss is too broad.

2. **Coverage is a diagnostic, never a gate.** Compute and display it; warn below 0.90; always allow entry. Its real job is to tell you whether the *book* is right for your level, not whether the chapter is ready. If a chapter needs five sessions to clear 90%, switch books — that signal is worth more than a lock screen.

3. **No inline translation in the reader.** Every gloss is tap-to-reveal. Build one exception: a **"reveal all glosses"** toggle intended for a second pass through an already-read chapter. It must be off by default and must not persist across chapters.

4. **First text: `Los de abajo` by Mariano Azuela (1915, public domain).** Available from Project Gutenberg, genuinely Mexican, and dense with revolutionary-era regional vocabulary — it stress-tests the `mexicanism` flagging immediately. Use it for all pipeline development. `Fiesta en la madriguera` becomes the first real read once a DRM-free EPUB is in hand.

### Note on source files

The pipeline accepts **DRM-free EPUB only**. It must not contain, reference, or attempt any DRM circumvention — that is legally fraught under §95a UrhG in Germany and is out of scope for this project. Where a book is unavailable DRM-free, the answer is to read it on paper, not to work around the protection.

---

## Appendix A — Prep script pseudocode

```python
def build_bundle(epub_path, known_lemmas, out_path):
    chapters_html = extract_chapters(epub_path)          # ebooklib
    nlp = spacy.load("es_core_news_sm")

    lexicon, chapters = {}, []

    for idx, html in enumerate(chapters_html):
        text = clean(html)                                # strip markup, keep ¶ breaks
        doc = nlp(text)

        paragraphs, chapter_lemmas = [], Counter()
        for para in split_paragraphs(doc):
            tokens = []
            for tok in para:
                if tok.is_space:
                    tokens.append({"s": tok.text, "ws": True})
                    continue
                lemma = tok.lemma_.lower()
                key = lemma_key(lemma, tok.pos_)
                tokens.append({"s": tok.text, "l": lemma,
                               "p": tok.pos_, "t": key})
                if tok.is_alpha and tok.pos_ != "PUNCT":
                    chapter_lemmas[key] += 1
                    lexicon.setdefault(key, new_entry(lemma, tok.pos_))
            paragraphs.append({"id": f"c{idx}p{len(paragraphs)}",
                               "tokens": tokens})

        chapters.append({"index": idx, "paragraphs": paragraphs,
                         "_counts": chapter_lemmas})

    # Global pass — needs the whole book
    for key, entry in lexicon.items():
        entry["bookCount"] = sum(c["_counts"][key] for c in chapters)
        entry["zipf"] = wordfreq.zipf_frequency(entry["lemma"], "es")
        entry["de"], entry["en"], entry["mexicanism"] = lookup(entry["lemma"])
        entry["example"] = first_sentence_containing(key, chapters)

    fill_gaps_with_claude(lexicon)                        # batch API

    for chap in chapters:
        teach, gloss = classify(chap["_counts"], lexicon, known_lemmas)
        chap["teachSet"], chap["glossOnly"] = teach, gloss
        del chap["_counts"]

    write_json(out_path, schemaVersion=1,
               book=metadata(epub_path), chapters=chapters, lexicon=lexicon)
```

---

## Appendix B — Domain function signatures to implement first

```typescript
// src/domain/teachSet.ts — pure, tested, portable to Swift
export function selectTeachSet(
  chapterCounts: Map<LemmaKey, number>,
  lexicon: Lexicon,
  known: Set<LemmaKey>,
  opts: { maxCards: number; zipfThreshold: number }
): { teach: LemmaKey[]; glossOnly: LemmaKey[] };

export function computeCoverage(
  chapter: Chapter,
  known: Set<LemmaKey>
): number;

export function splitChapterIfNeeded(
  chapter: Chapter,
  teachSet: LemmaKey[],
  maxCards: number
): ReadingSegment[];
```

These three functions are the app. Everything else is presentation.
