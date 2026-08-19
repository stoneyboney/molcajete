"""Where molcajete-prep's glossing meets this repo's bundle.

Everything here exercises package code *through* the book half, which is why it
lives in this repo rather than in molcajete-prep's own suite: the EPUB reader
and the §4 schema are the parts the package deliberately does not have.

The property being pinned is ordering. `mexicanism` is one of the three SPEC §5
teach rules, so glossing has to finish before classification starts. Getting it
backwards produces a bundle that looks perfectly valid and quietly never teaches
a mexicanism.

`extracts` — two tiny stand-ins for the Wiktionary dumps — comes from
molcajete-prep's pytest plugin, along with the guards that stop these tests
touching the real 22.9 GB extracts or the developer's gloss cache.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from molcajete_book.bundle import build_bundle
from molcajete_book.epub import extract_chapters
from molcajete_book.schema import BundleValidationError, validate_bundle
from molcajete_prep.classify import Classification
from molcajete_prep.glossing.cache import GlossCache
from molcajete_prep.glossing.pipeline import GlossingOptions, gloss_lexicon
from molcajete_prep.lexicon import build_lexicon
from molcajete_prep.nlp import Token, tokenize, tokenize_paragraphs

NOW = datetime(2026, 8, 17, 9, 0, 0)


def word(lemma, pos="NOUN", surface=None, sentence=0):
    return Token(
        surface=surface or lemma,
        lemma=lemma,
        pos=pos,
        is_whitespace=False,
        sentence=sentence,
    )


@pytest.fixture
def cache():
    with GlossCache.in_memory() as store:
        yield store


class TestTokenizationAgainstTheFixture:
    """The load-bearing assertion of `molcajete_prep.nlp`, run over real EPUB
    prose rather than hand-written strings. If the whitespace synthesis is wrong
    the reader silently renders words glued together, and this is what catches
    it at book scale."""

    def test_surfaces_rejoin_for_every_paragraph_of_the_fixture(
        self, nlp, fixture_epub
    ):
        for chapter in extract_chapters(str(fixture_epub)):
            for paragraph in chapter.paragraphs:
                tokens = tokenize(nlp, paragraph)

                assert "".join(t.surface for t in tokens) == paragraph


class TestLexiconAgainstTheFixture:
    def test_the_fixture_lexicon_has_the_expected_shape(self, nlp, fixture_epub):
        chapters = [
            tokenize_paragraphs(nlp, list(chapter.paragraphs))
            for chapter in extract_chapters(str(fixture_epub))
        ]

        lexicon = build_lexicon(chapters)
        by_lemma = {r.lemma: r for r in lexicon.records.values()}

        # Planted in all three chapters.
        for lemma in ("sierra", "fusil", "caballo", "jacal"):
            assert by_lemma[lemma].book_count >= 3, lemma
            assert by_lemma[lemma].first_chapter == 0, lemma

        # Planted once, deep in the book.
        assert by_lemma["chaparral"].book_count == 1
        assert by_lemma["chaparral"].first_chapter == 1

        # Names never reach the lexicon.
        assert "demetrio" not in by_lemma
        assert "demetrio" in lexicon.proper_noun_lemmas


class TestBundleIntegration:
    """Glossing runs before classification. These pin that, because getting it
    backwards yields a valid-looking bundle that never teaches a mexicanism."""

    def _tokens(self):
        # bookCount 2 so only the mexicanism rule can teach it: below
        # min_book_count (3), and `chido` has a low enough zipf to miss that rule.
        return [[[word("chido", "ADJ"), word("chido", "ADJ")]]]

    def test_a_mexicanism_reaches_the_teach_set(self, extracts, cache, monkeypatch):
        tokens = self._tokens()
        lexicon = build_lexicon(tokens)

        result = gloss_lexicon(
            lexicon,
            tokens,
            book_id="test",
            options=GlossingOptions(use_model=False, extract_dir=extracts),
            cache=cache,
            now=NOW,
        )

        entries = lexicon.entries_for_classification(result.mexicanism_by_key())
        key = next(iter(lexicon.records))
        assert entries[key].mexicanism is True

    def test_glosses_reach_the_lexicon_json(self, fixture_epub, extracts, monkeypatch):
        monkeypatch.setenv("MOLCAJETE_TEST", "1")
        built = build_bundle(
            fixture_epub,
            gloss=True,
            gloss_options=GlossingOptions(use_model=False, extract_dir=extracts),
        )

        glossed = [e for e in built.bundle["lexicon"].values() if "en" in e]
        assert glossed, "no lemma in the fixture book picked up a gloss"
        assert all(isinstance(e["en"], str) and e["en"] for e in glossed)

    def test_a_no_gloss_build_is_still_a_valid_bundle(self, fixture_epub):
        built = build_bundle(fixture_epub, gloss=False)

        assert built.glossed is False
        assert all(
            entry["mexicanism"] is False
            for entry in built.bundle["lexicon"].values()
        )
        assert all("de" not in entry for entry in built.bundle["lexicon"].values())

    def test_a_no_gloss_build_teaches_nothing_by_the_mexicanism_rule(self, fixture_epub):
        """Worth stating out loud: --no-gloss does not merely omit glosses, it
        changes which lemmas are taught."""
        built = build_bundle(fixture_epub, gloss=False)

        reasons = {r.reason for r in built.classifications.values() if r.reason}
        assert all(reason.value != "mexicanism" for reason in reasons)

    def test_the_bundle_carries_no_lemmatizer_diagnostics(self, fixture_epub, extracts):
        """`not_spanish` and `corrected_lemma` are notes about spaCy, not about
        vocabulary. The reader has no use for a field saying the word it is
        about to render is not a word."""
        built = build_bundle(
            fixture_epub,
            gloss=True,
            gloss_options=GlossingOptions(use_model=False, extract_dir=extracts),
        )

        for entry in built.bundle["lexicon"].values():
            assert "not_spanish" not in entry
            assert "corrected_lemma" not in entry


class TestSchemaGuards:
    def test_a_mexicanism_without_a_region_note_is_rejected(self):
        """A card that claims Mexican usage without saying what kind is a claim
        the reader cannot act on."""
        bundle = {
            "schemaVersion": 1,
            "book": {
                "id": "x", "title": "x", "author": "x", "language": "es",
                "variant": "es-MX", "totalTokens": 1, "uniqueLemmas": 1,
            },
            "chapters": [],
            "lexicon": {
                "m0000": {
                    "lemma": "chido", "pos": "ADJ", "zipf": 2.1,
                    "bookCount": 6, "firstChapter": 0, "mexicanism": True,
                    "de": "cool",
                }
            },
        }

        with pytest.raises(BundleValidationError, match="regionNote"):
            validate_bundle(bundle)

    def test_an_empty_gloss_string_is_rejected(self):
        """An absent `de` means "no gloss". An empty one means the same thing
        while rendering as a blank line on a card."""
        bundle = {
            "schemaVersion": 1,
            "book": {
                "id": "x", "title": "x", "author": "x", "language": "es",
                "variant": "es-MX", "totalTokens": 1, "uniqueLemmas": 1,
            },
            "chapters": [],
            "lexicon": {
                "m0000": {
                    "lemma": "libro", "pos": "NOUN", "zipf": 4.0,
                    "bookCount": 3, "firstChapter": 0, "mexicanism": False,
                    "de": "",
                }
            },
        }

        with pytest.raises(BundleValidationError, match="empty"):
            validate_bundle(bundle)


