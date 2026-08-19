"""The SPEC §5 vocabulary selection rules.

Pure. No spaCy, no ebooklib, no filesystem, no clock. This module is the Python
twin of `selectTeachSet()` from SPEC Appendix B, and it will be written a third
time in Swift. Its tests are the specification all three answer to — read them
before changing anything here.

Three readings of §5 are settled here rather than left to the caller:

**PROPN is checked first, not last.** §5's table lists `PROPN -> skip` below
`bookCount >= 3 -> teach`. Read top-down that teaches *Demetrio*, which appears
hundreds of times. CLAUDE.md is unambiguous — "PROPN is skipped entirely, no
card, no gloss" — so the skip is evaluated before the teach rules.

**A lemma is taught once, glossed everywhere.** Its card belongs to the first
chapter it appears in; that is what `firstChapter` is for, and re-teaching it in
chapter 7 would defeat the point of pre-teaching. A gloss-only lemma is a dotted
underline rather than a card, so it is listed in every chapter it occurs in —
otherwise the reader stops underlining a word you still don't know.

**Closed-class parts of speech are never taught.** §5 does not say so and should:
unmodified it makes 16 of the first 18 cards of a real book function words. See
`CLOSED_CLASS_POS` below. This is a pure rule over `pos`, so all three
implementations carry it.

## Where the TypeScript deliberately differs

One divergence is essential rather than accidental, and porting it here is not
possible. `app/src/domain/teachSet.ts` teaches a lemma **where it occurs**, not
at its `firstChapter`, because the app can ask a card store whether the word is
already being learned and this module cannot. The effect is that opening chapter
3 without having read chapter 0 teaches the chapter-0 vocabulary it reuses,
instead of leaving it merely underlined.

So the two answers differ by design, and the app never reads the `teachSet` this
module bakes into the bundle — it recomputes against the live known-set. What
the baked set is for is the report, and reports that disagree with the app are
worse than no report.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

LemmaKey = str

# Parts of speech that never earn a card, however common they are.
#
# Not in SPEC §5, which produces a first session of `el`, `de`, `y`, `él`, `a`
# — 16 of the first 18 cards of a real book were function words, because
# `zipf >= 3.5` catches every one of them and `bookCount` sorts them to the top.
# A flashcard does not teach `de`; that is grammar, and it arrives from reading.
# They are still glossed, so the reader is unchanged.
#
# `INTJ` is deliberately absent. An interjection is exactly the vocabulary this
# project exists for — `¡órale!` is worth a card in a way that `de` is not.
#
# This list is duplicated in `app/src/domain/teachSet.ts` and must stay in step
# with it. The two are the same rule written twice on purpose (CLAUDE.md), and
# Swift will be the third.
CLOSED_CLASS_POS = frozenset(
    {"ADP", "AUX", "CCONJ", "DET", "NUM", "PART", "PRON", "PUNCT", "SCONJ", "SYM", "X"}
)


class Classification(str, Enum):
    TEACH = "teach"
    GLOSS_ONLY = "glossOnly"
    SKIPPED_PROPER_NOUN = "skippedProperNoun"
    SKIPPED_CLOSED_CLASS = "skippedClosedClass"
    ALREADY_KNOWN = "alreadyKnown"


class TeachReason(str, Enum):
    """Which §5 rule fired. Reported, so we can see the mix."""

    BOOK_COUNT = "bookCount"
    ZIPF = "zipf"
    MEXICANISM = "mexicanism"


@dataclass(frozen=True)
class LexiconEntry:
    """The subset of a lexicon entry the rules actually read."""

    lemma: str
    pos: str
    zipf: float
    book_count: int
    first_chapter: int
    mexicanism: bool = False


@dataclass(frozen=True)
class ClassificationOptions:
    """§5's thresholds, named so they can be tuned from the CLI rather than edited."""

    min_book_count: int = 3
    zipf_threshold: float = 3.5
    mexicanism_min_book_count: int = 2
    max_cards_per_session: int = 18
    closed_class_pos: frozenset[str] = CLOSED_CLASS_POS


@dataclass(frozen=True)
class ClassificationResult:
    classification: Classification
    reason: TeachReason | None = None

    @property
    def is_teach(self) -> bool:
        return self.classification is Classification.TEACH


@dataclass(frozen=True)
class ChapterVocabulary:
    """What one chapter teaches and what it merely underlines."""

    teach: tuple[LemmaKey, ...]
    gloss_only: tuple[LemmaKey, ...]


def exceeds_cap(vocabulary: ChapterVocabulary, options: ClassificationOptions) -> bool:
    """Whether this chapter's teach set is too big for one session (§5 Step 3).

    Phase 1 only reports this. Splitting a chapter into reading segments is
    Phase 4's job.
    """
    return len(vocabulary.teach) > options.max_cards_per_session


def classify_lemma(
    entry: LexiconEntry,
    *,
    is_known: bool,
    options: ClassificationOptions = ClassificationOptions(),
) -> ClassificationResult:
    """Apply §5 Step 2 to a single lemma. First matching rule wins."""
    if entry.pos == "PROPN":
        return ClassificationResult(Classification.SKIPPED_PROPER_NOUN)

    # Before the teach rules, for the same reason PROPN is: `el` clears
    # `bookCount >= 3` several thousand times over.
    if entry.pos in options.closed_class_pos:
        return ClassificationResult(Classification.SKIPPED_CLOSED_CLASS)

    if is_known:
        return ClassificationResult(Classification.ALREADY_KNOWN)

    if entry.book_count >= options.min_book_count:
        return ClassificationResult(Classification.TEACH, TeachReason.BOOK_COUNT)

    if entry.zipf >= options.zipf_threshold:
        return ClassificationResult(Classification.TEACH, TeachReason.ZIPF)

    if entry.mexicanism and entry.book_count >= options.mexicanism_min_book_count:
        return ClassificationResult(Classification.TEACH, TeachReason.MEXICANISM)

    return ClassificationResult(Classification.GLOSS_ONLY)


def classify_all(
    entries: Mapping[LemmaKey, LexiconEntry],
    known_lemmas: frozenset[str] = frozenset(),
    options: ClassificationOptions = ClassificationOptions(),
) -> dict[LemmaKey, ClassificationResult]:
    """Classify every lemma in the lexicon exactly once.

    `known_lemmas` holds lemma *strings*, matching the flat array `seed_known.py`
    produces in Phase 5, not lexicon keys.
    """
    return {
        key: classify_lemma(entry, is_known=entry.lemma in known_lemmas, options=options)
        for key, entry in entries.items()
    }


def assign_to_chapters(
    entries: Mapping[LemmaKey, LexiconEntry],
    chapter_lemma_keys: Sequence[frozenset[LemmaKey]],
    known_lemmas: frozenset[str] = frozenset(),
    options: ClassificationOptions = ClassificationOptions(),
) -> list[ChapterVocabulary]:
    """Distribute classified lemmas across chapters.

    `chapter_lemma_keys[i]` is the set of lexicon keys occurring in chapter `i`.

    Teach sets are sorted by `bookCount` descending, per §5 Step 3, so that an
    abandoned session still taught the most useful words. Ties break on the key
    to keep rebuilds byte-identical.
    """
    results = classify_all(entries, known_lemmas, options)

    chapters: list[ChapterVocabulary] = []
    for index, keys in enumerate(chapter_lemma_keys):
        teach = [
            key
            for key, result in results.items()
            if result.is_teach and entries[key].first_chapter == index
        ]
        teach.sort(key=lambda key: (-entries[key].book_count, key))

        # Closed-class lemmas are underlined like any other unknown word: the
        # rule is about cards, not about the reader, and `teachSet.ts` puts
        # everything it declines to teach into glossOnly for the same reason.
        # Proper nouns stay out — §5 gives them no gloss at all.
        gloss_only = sorted(
            key
            for key in keys
            if results[key].classification
            in (Classification.GLOSS_ONLY, Classification.SKIPPED_CLOSED_CLASS)
        )

        chapters.append(
            ChapterVocabulary(teach=tuple(teach), gloss_only=tuple(gloss_only))
        )

    return chapters
