"""Tests for the SPEC §5 rules.

These are the specification, not just a regression net. The same behaviour has
to appear in `src/domain/teachSet.ts` and later in Swift, so each test names the
rule it pins rather than the implementation detail.
"""

from __future__ import annotations

import pytest

from molcajete_prep.classify import (
    CLOSED_CLASS_POS,
    ChapterVocabulary,
    Classification,
    ClassificationOptions,
    LexiconEntry,
    TeachReason,
    assign_to_chapters,
    classify_all,
    classify_lemma,
    exceeds_cap,
)

OPTIONS = ClassificationOptions()


def entry(
    lemma: str = "fusil",
    pos: str = "NOUN",
    zipf: float = 2.0,
    book_count: int = 1,
    first_chapter: int = 0,
    mexicanism: bool = False,
) -> LexiconEntry:
    return LexiconEntry(
        lemma=lemma,
        pos=pos,
        zipf=zipf,
        book_count=book_count,
        first_chapter=first_chapter,
        mexicanism=mexicanism,
    )


class TestStep2Rules:
    """One test per row of the §5 Step 2 table."""

    def test_a_lemma_met_three_times_is_taught(self):
        result = classify_lemma(entry(book_count=3), is_known=False)

        assert result.classification is Classification.TEACH
        assert result.reason is TeachReason.BOOK_COUNT

    def test_a_common_lemma_is_taught_even_if_met_once(self):
        result = classify_lemma(entry(book_count=1, zipf=4.2), is_known=False)

        assert result.classification is Classification.TEACH
        assert result.reason is TeachReason.ZIPF

    def test_a_mexicanism_met_twice_is_taught(self):
        result = classify_lemma(
            entry(lemma="chido", book_count=2, zipf=2.1, mexicanism=True),
            is_known=False,
        )

        assert result.classification is Classification.TEACH
        assert result.reason is TeachReason.MEXICANISM

    def test_a_mexicanism_met_once_is_not_taught(self):
        result = classify_lemma(
            entry(lemma="chido", book_count=1, zipf=2.1, mexicanism=True),
            is_known=False,
        )

        assert result.classification is Classification.GLOSS_ONLY

    def test_a_proper_noun_is_skipped(self):
        result = classify_lemma(entry(lemma="demetrio", pos="PROPN"), is_known=False)

        assert result.classification is Classification.SKIPPED_PROPER_NOUN

    def test_everything_else_is_gloss_only(self):
        result = classify_lemma(entry(book_count=1, zipf=1.4), is_known=False)

        assert result.classification is Classification.GLOSS_ONLY
        assert result.reason is None


class TestClosedClass:
    """Function words are never taught, however common they are.

    Not in SPEC §5. Without it the top of every teach set is `el`, `de`, `y`,
    `que` — 16 of the first 18 cards of a real book — because `zipf >= 3.5`
    catches every function word and `bookCount` sorts them first. The same list
    is in `app/src/domain/teachSet.ts`; the two must not drift.
    """

    @pytest.mark.parametrize(
        ("lemma", "pos"),
        [
            ("el", "DET"),
            ("de", "ADP"),
            ("él", "PRON"),
            ("y", "CCONJ"),
            ("que", "SCONJ"),
            ("ser", "AUX"),
            ("dos", "NUM"),
        ],
    )
    def test_a_function_word_is_never_taught(self, lemma, pos):
        # Given every reason to teach it: met thousands of times, and among the
        # most common words in the language.
        result = classify_lemma(
            entry(lemma=lemma, pos=pos, zipf=7.4, book_count=8691), is_known=False
        )

        assert result.classification is Classification.SKIPPED_CLOSED_CLASS
        assert not result.is_teach

    def test_an_interjection_is_still_taught(self):
        # `¡órale!` is exactly the vocabulary this project exists for.
        assert "INTJ" not in CLOSED_CLASS_POS
        result = classify_lemma(
            entry(lemma="órale", pos="INTJ", book_count=4), is_known=False
        )

        assert result.is_teach

    def test_a_function_word_is_still_glossed(self):
        # The rule is about cards, not about the reader. `el` keeps its lexicon
        # entry and its dotted underline.
        chapters = assign_to_chapters(
            {"m1": entry(lemma="el", pos="DET", zipf=7.45, book_count=8691)},
            [frozenset({"m1"})],
        )

        assert chapters[0].teach == ()
        assert chapters[0].gloss_only == ("m1",)

    def test_the_rule_is_configurable(self):
        options = ClassificationOptions(closed_class_pos=frozenset())

        result = classify_lemma(
            entry(lemma="el", pos="DET", zipf=7.45, book_count=8691),
            is_known=False,
            options=options,
        )

        assert result.is_teach


class TestRuleOrdering:
    def test_proper_nouns_beat_the_book_count_rule(self):
        """The reason PROPN is checked first.

        Demetrio Macías appears on nearly every page of Los de abajo. Read
        top-down, §5's table would hand you a flashcard for the protagonist's
        name. CLAUDE.md forbids it outright.
        """
        result = classify_lemma(
            entry(lemma="demetrio", pos="PROPN", book_count=400, zipf=4.0),
            is_known=False,
        )

        assert result.classification is Classification.SKIPPED_PROPER_NOUN

    def test_proper_nouns_are_skipped_whether_or_not_they_are_known(self):
        result = classify_lemma(entry(pos="PROPN"), is_known=True)

        assert result.classification is Classification.SKIPPED_PROPER_NOUN

    def test_closed_class_beats_the_book_count_rule(self):
        # Same trap as PROPN: read §5 top-down and `el` is taught 8,691 times
        # over before anything gets a chance to skip it.
        result = classify_lemma(
            entry(lemma="el", pos="DET", zipf=7.45, book_count=8691), is_known=False
        )

        assert result.classification is Classification.SKIPPED_CLOSED_CLASS
        assert result.reason is None

    def test_proper_nouns_are_checked_before_closed_class(self):
        # Only observable if a tagger ever emits both; pinned so the two skips
        # keep a defined order across the three implementations.
        result = classify_lemma(entry(lemma="él", pos="PROPN"), is_known=False)

        assert result.classification is Classification.SKIPPED_PROPER_NOUN

    def test_known_lemmas_are_neither_taught_nor_glossed(self):
        result = classify_lemma(entry(book_count=99, zipf=5.0), is_known=True)

        assert result.classification is Classification.ALREADY_KNOWN

    def test_book_count_is_reported_ahead_of_zipf_when_both_apply(self):
        result = classify_lemma(entry(book_count=10, zipf=5.0), is_known=False)

        assert result.reason is TeachReason.BOOK_COUNT


class TestThresholdBoundaries:
    @pytest.mark.parametrize(
        ("book_count", "expected"),
        [(2, Classification.GLOSS_ONLY), (3, Classification.TEACH)],
    )
    def test_book_count_threshold_is_inclusive_at_three(self, book_count, expected):
        result = classify_lemma(entry(book_count=book_count), is_known=False)

        assert result.classification is expected

    @pytest.mark.parametrize(
        ("zipf", "expected"),
        [(3.49, Classification.GLOSS_ONLY), (3.5, Classification.TEACH)],
    )
    def test_zipf_threshold_is_inclusive_at_three_point_five(self, zipf, expected):
        result = classify_lemma(entry(zipf=zipf), is_known=False)

        assert result.classification is expected

    def test_thresholds_are_configurable(self):
        options = ClassificationOptions(min_book_count=2, zipf_threshold=9.0)

        result = classify_lemma(entry(book_count=2), is_known=False, options=options)

        assert result.classification is Classification.TEACH


class TestClassifyAll:
    def test_known_lemmas_are_matched_by_lemma_string_not_key(self):
        entries = {
            "m0001": entry(lemma="caballo", book_count=5),
            "m0002": entry(lemma="fusil", book_count=5),
        }

        results = classify_all(entries, frozenset({"caballo"}))

        assert results["m0001"].classification is Classification.ALREADY_KNOWN
        assert results["m0002"].classification is Classification.TEACH

    def test_every_lemma_is_classified_exactly_once(self):
        entries = {f"m{i:04d}": entry(lemma=f"l{i}") for i in range(50)}

        assert len(classify_all(entries)) == 50


class TestChapterAssignment:
    def test_a_lemma_is_taught_only_in_its_first_chapter(self):
        entries = {"m0001": entry(lemma="sierra", book_count=9, first_chapter=1)}
        occurrences = [frozenset(), frozenset({"m0001"}), frozenset({"m0001"})]

        chapters = assign_to_chapters(entries, occurrences)

        assert chapters[0].teach == ()
        assert chapters[1].teach == ("m0001",)
        assert chapters[2].teach == ()

    def test_a_taught_lemma_is_not_glossed_in_later_chapters(self):
        entries = {"m0001": entry(lemma="sierra", book_count=9, first_chapter=0)}
        occurrences = [frozenset({"m0001"}), frozenset({"m0001"})]

        chapters = assign_to_chapters(entries, occurrences)

        assert chapters[1].teach == ()
        assert chapters[1].gloss_only == ()

    def test_a_gloss_only_lemma_is_underlined_in_every_chapter_it_appears_in(self):
        """Unlike a card, a dotted underline is worth repeating.

        The word never gets taught, so the reader still needs it flagged the
        second time it turns up.
        """
        entries = {"m0001": entry(lemma="huizache", book_count=2, zipf=1.1)}
        occurrences = [frozenset({"m0001"}), frozenset({"m0001"})]

        chapters = assign_to_chapters(entries, occurrences)

        assert chapters[0].gloss_only == ("m0001",)
        assert chapters[1].gloss_only == ("m0001",)

    def test_proper_nouns_appear_in_neither_list(self):
        entries = {"m0001": entry(lemma="demetrio", pos="PROPN", book_count=99)}
        occurrences = [frozenset({"m0001"})]

        chapters = assign_to_chapters(entries, occurrences)

        assert chapters[0] == ChapterVocabulary(teach=(), gloss_only=())

    def test_known_lemmas_appear_in_neither_list(self):
        entries = {"m0001": entry(lemma="caballo", book_count=99)}
        occurrences = [frozenset({"m0001"})]

        chapters = assign_to_chapters(entries, occurrences, frozenset({"caballo"}))

        assert chapters[0] == ChapterVocabulary(teach=(), gloss_only=())

    def test_teach_sets_are_ordered_by_book_count_descending(self):
        """§5 Step 3: a partially finished session should still have taught the
        words that pay off most."""
        entries = {
            "m0001": entry(lemma="raro", book_count=3),
            "m0002": entry(lemma="frecuente", book_count=40),
            "m0003": entry(lemma="medio", book_count=12),
        }
        occurrences = [frozenset(entries)]

        chapters = assign_to_chapters(entries, occurrences)

        assert chapters[0].teach == ("m0002", "m0003", "m0001")

    def test_equal_book_counts_break_ties_on_key_for_reproducibility(self):
        entries = {
            "m0002": entry(lemma="b", book_count=5),
            "m0001": entry(lemma="a", book_count=5),
        }
        occurrences = [frozenset(entries)]

        chapters = assign_to_chapters(entries, occurrences)

        assert chapters[0].teach == ("m0001", "m0002")


class TestSessionCap:
    def test_a_chapter_within_the_cap_does_not_exceed_it(self):
        vocabulary = ChapterVocabulary(
            teach=tuple(f"m{i:04d}" for i in range(18)), gloss_only=()
        )

        assert not exceeds_cap(vocabulary, OPTIONS)

    def test_nineteen_cards_exceeds_the_cap(self):
        vocabulary = ChapterVocabulary(
            teach=tuple(f"m{i:04d}" for i in range(19)), gloss_only=()
        )

        assert exceeds_cap(vocabulary, OPTIONS)


def test_module_imports_nothing_that_would_not_port_to_swift():
    """The port target must stay free of spaCy, ebooklib and I/O."""
    import ast
    import pathlib

    import molcajete_prep.classify as module

    tree = ast.parse(pathlib.Path(module.__file__).read_text())
    imported = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert imported <= {"__future__", "collections", "dataclasses", "enum"}
