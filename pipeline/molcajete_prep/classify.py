"""The SPEC §5 vocabulary selection rules.

Pure. No spaCy, no ebooklib, no filesystem, no clock. This module is the Python
twin of `selectTeachSet()` from SPEC Appendix B, and it will be written a third
time in Swift. Its tests are the specification all three answer to — read them
before changing anything here.

Two readings of §5 are settled here rather than left to the caller:

**PROPN is checked first, not last.** §5's table lists `PROPN -> skip` below
`bookCount >= 3 -> teach`. Read top-down that teaches *Demetrio*, which appears
hundreds of times. CLAUDE.md is unambiguous — "PROPN is skipped entirely, no
card, no gloss" — so the skip is evaluated before the teach rules.

**A lemma is taught once, glossed everywhere.** Its card belongs to the first
chapter it appears in; that is what `firstChapter` is for, and re-teaching it in
chapter 7 would defeat the point of pre-teaching. A gloss-only lemma is a dotted
underline rather than a card, so it is listed in every chapter it occurs in —
otherwise the reader stops underlining a word you still don't know.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

LemmaKey = str


class Classification(str, Enum):
    TEACH = "teach"
    GLOSS_ONLY = "glossOnly"
    SKIPPED_PROPER_NOUN = "skippedProperNoun"
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

        gloss_only = sorted(
            key
            for key in keys
            if results[key].classification is Classification.GLOSS_ONLY
        )

        chapters.append(
            ChapterVocabulary(teach=tuple(teach), gloss_only=tuple(gloss_only))
        )

    return chapters
