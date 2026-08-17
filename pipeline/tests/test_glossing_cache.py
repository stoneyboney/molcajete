from __future__ import annotations

from datetime import datetime

import pytest

from molcajete_prep.glossing.cache import GlossCache
from molcajete_prep.glossing.models import (
    Gloss,
    GlossSource,
    gloss_text,
    normalize_gloss,
    upos_candidates,
)

NOW = datetime(2026, 8, 16, 12, 0, 0)


@pytest.fixture
def cache():
    with GlossCache.in_memory() as store:
        yield store


def madriguera(**overrides) -> Gloss:
    fields = {
        "lemma": "madriguera",
        "pos": "NOUN",
        "de": "der Bau, die Höhle",
        "en": "burrow, den",
        "de_source": GlossSource.CLAUDE,
        "en_source": GlossSource.EN_WIKTIONARY,
    }
    return Gloss(**{**fields, **overrides})


class TestRoundTrip:
    def test_a_stored_gloss_comes_back_unchanged(self, cache):
        cache.put(madriguera(), now=NOW)

        assert cache.get("madriguera", "NOUN") == madriguera()

    def test_a_missing_gloss_is_none_rather_than_an_error(self, cache):
        assert cache.get("inexistente", "NOUN") is None

    def test_flags_and_notes_survive_the_round_trip(self, cache):
        chido = Gloss(
            lemma="chido",
            pos="ADJ",
            de="cool, super",
            en="cool, great",
            de_source=GlossSource.CLAUDE,
            en_source=GlossSource.CLAUDE,
            mexicanism=True,
            region_note="Mexiko, umgangssprachlich",
        )
        cache.put(chido, now=NOW)

        assert cache.get("chido", "ADJ") == chido

    def test_a_rejected_lemma_round_trips_with_its_correction(self, cache):
        """The lemmatizer's damage is worth storing: it costs an API call to
        discover that `abalanzar él` is not a word, and only once."""
        noise = Gloss(
            lemma="abalanzar él",
            pos="VERB",
            not_spanish=True,
            corrected_lemma="abalanzarse",
        )
        cache.put(noise, now=NOW)

        stored = cache.get("abalanzar él", "VERB")
        assert stored is not None
        assert stored.not_spanish is True
        assert stored.corrected_lemma == "abalanzarse"
        assert stored.de is None


class TestIdentity:
    def test_the_same_lemma_under_two_tags_is_two_entries(self):
        """`bajo` the adjective and `bajo` the preposition take different German
        glosses. A cache keyed on the lemma alone would give one book's card the
        other book's meaning."""
        with GlossCache.in_memory() as cache:
            cache.put(Gloss(lemma="bajo", pos="ADJ", de="niedrig"), now=NOW)
            cache.put(Gloss(lemma="bajo", pos="ADP", de="unter"), now=NOW)

            assert cache.get("bajo", "ADJ").de == "niedrig"
            assert cache.get("bajo", "ADP").de == "unter"
            assert cache.count() == 2

    def test_writing_the_same_identity_twice_replaces_rather_than_duplicates(self, cache):
        cache.put(madriguera(de="Bau"), now=NOW)
        cache.put(madriguera(de="der Bau, die Höhle"), now=NOW)

        assert cache.count() == 1
        assert cache.get("madriguera", "NOUN").de == "der Bau, die Höhle"


class TestBulkAccess:
    def test_get_many_returns_only_what_is_present(self, cache):
        cache.put_many(
            [madriguera(), Gloss(lemma="chido", pos="ADJ", de="cool")], now=NOW
        )

        found = cache.get_many(
            [("madriguera", "NOUN"), ("chido", "ADJ"), ("ausente", "NOUN")]
        )

        assert set(found) == {("madriguera", "NOUN"), ("chido", "ADJ")}

    def test_get_many_handles_more_identities_than_sqlite_takes_parameters(self, cache):
        """SQLite caps a statement at 999 host parameters and a book asks for
        thousands, so the lookup has to chunk."""
        glosses = [Gloss(lemma=f"palabra{i:04d}", pos="NOUN", de="x") for i in range(900)]
        cache.put_many(glosses, now=NOW)

        found = cache.get_many((g.lemma, g.pos) for g in glosses)

        assert len(found) == 900

    def test_forget_drops_rows_so_they_are_fetched_again(self, cache):
        cache.put_many([madriguera(), Gloss(lemma="chido", pos="ADJ")], now=NOW)

        removed = cache.forget([("madriguera", "NOUN")])

        assert removed == 1
        assert cache.get("madriguera", "NOUN") is None
        assert cache.get("chido", "ADJ") is not None


class TestProvenance:
    def test_the_disambiguating_sentence_and_book_are_recorded(self, cache):
        """A Claude gloss is only correct for the sense the book used, so the
        row has to say which book and which sentence produced it."""
        cache.put(
            madriguera(),
            now=NOW,
            model="claude-sonnet-5",
            prompt_version=1,
            example_es="Mi papá dice que somos gente de la madriguera.",
            book_id="villalobos-fiesta-madriguera",
        )

        row = cache._connection.execute(
            "SELECT * FROM glosses WHERE lemma = 'madriguera'"
        ).fetchone()
        assert row["model"] == "claude-sonnet-5"
        assert row["prompt_version"] == 1
        assert row["book_id"] == "villalobos-fiesta-madriguera"
        assert "madriguera" in row["example_es"]
        assert row["created_at"] == "2026-08-16T12:00:00"

    def test_a_fetched_extract_is_recorded_with_its_checksum(self, cache):
        cache.record_source(
            "en-wiktionary",
            url="https://kaikki.org/downloads/es/es-extract.jsonl.gz",
            sha256="abc123",
            entry_count=771_237,
            now=NOW,
        )

        row = cache.source("en-wiktionary")
        assert row["sha256"] == "abc123"
        assert row["entry_count"] == 771_237

    def test_an_unfetched_extract_is_none(self, cache):
        assert cache.source("de-wiktionary") is None


class TestPersistence:
    def test_a_cache_on_disk_survives_being_closed_and_reopened(self, tmp_path):
        """This is the whole point: the second book reads what the first wrote."""
        path = tmp_path / "glosses.sqlite3"
        with GlossCache(path) as first_book:
            first_book.put(madriguera(), now=NOW)

        with GlossCache(path) as second_book:
            assert second_book.get("madriguera", "NOUN") == madriguera()

    def test_opening_a_cache_creates_its_directory(self, tmp_path):
        path = tmp_path / "nested" / "glosses.sqlite3"
        with GlossCache(path):
            pass

        assert path.exists()

    def test_an_in_memory_cache_does_not_touch_the_shared_store(self, tmp_path):
        """The trial script runs at experimental settings; its output must not
        seed the store every later book reads from."""
        with GlossCache.in_memory() as trial:
            trial.put(madriguera(), now=NOW)
            assert trial.count() == 1

        with GlossCache.in_memory() as fresh:
            assert fresh.count() == 0


class TestGlossNormalization:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Buch", "Buch"),
            ("burrow, den", "burrow, den"),
            ("to burrow", "burrow"),
            ("To Burrow", "Burrow"),
            ("(Mexico) cool", "cool"),
            ("burrow [of an animal]", "burrow"),
            ("Bau; Höhle", "Bau, Höhle"),
            ("cool / great", "cool, great"),
            ("  spaced   out  ", "spaced out"),
            ("trailing.", "trailing"),
        ],
    )
    def test_dictionary_prose_becomes_card_text(self, raw, expected):
        assert gloss_text(raw) == expected

    def test_only_the_first_three_alternatives_survive(self):
        assert gloss_text("a, b, c, d, e") == "a, b, c"

    def test_duplicate_alternatives_are_dropped(self):
        assert gloss_text("Bau, Bau, Höhle") == "Bau, Höhle"

    @pytest.mark.parametrize("empty", [None, "", "   ", "()", "..."])
    def test_nothing_worth_showing_becomes_none(self, empty):
        assert gloss_text(empty) is None


class TestTranslationVersusDefinition:
    """The gate that decides whether Wiktionary's words are used as they stand
    or handed to Claude to condense."""

    @pytest.mark.parametrize(
        "text", ["Buch", "der Bau", "Bau, Höhle", "cool, super, klasse", "die kleine Hütte"]
    )
    def test_short_glosses_are_used_verbatim(self, text):
        assert normalize_gloss(text).is_translation is True

    @pytest.mark.parametrize(
        "text",
        [
            "burrow, den, sett, warren",
            "to take, catch, hold, to get, to seize",
            "Bau, Höhle, unterirdischer Unterschlupf eines Tieres",
            "have; forms the perfect aspect",
        ],
    )
    def test_a_surplus_of_short_alternatives_is_trimmed_and_still_usable(self, text):
        """Dropping the fourth synonym loses nothing a card needed."""
        result = normalize_gloss(text)

        assert result.is_translation is True
        assert result.trimmed is True
        assert result.clipped is False

    @pytest.mark.parametrize(
        "text",
        [
            "unterirdischer Unterschlupf eines Tieres",
            "A reference work listing words from one or more languages",
        ],
    )
    def test_a_lone_definition_is_clipped_and_therefore_rejected(self, text):
        """Cutting a definition to three words yields wreckage, not a gloss."""
        result = normalize_gloss(text)

        assert result.clipped is True
        assert result.is_translation is False

    @pytest.mark.parametrize("text", ["", None])
    def test_nothing_at_all_is_not_a_translation(self, text):
        assert normalize_gloss(text).is_translation is False

    def test_a_parenthetical_does_not_count_against_the_length(self):
        assert normalize_gloss("(Zoologie) Bau").is_translation is True

    def test_untouched_text_is_not_reported_as_shortened(self):
        assert normalize_gloss("der Bau").was_shortened is False


class TestPosMapping:
    def test_a_wiktionary_verb_answers_for_both_verb_and_aux(self):
        """spaCy tags `ser` and `haber` AUX; Wiktionary calls them verbs."""
        assert upos_candidates("verb") == ("VERB", "AUX")

    def test_a_wiktionary_conjunction_answers_for_both_conjunction_tags(self):
        assert upos_candidates("conj") == ("CCONJ", "SCONJ")

    def test_case_and_whitespace_do_not_matter(self):
        assert upos_candidates("  Noun ") == ("NOUN",)

    @pytest.mark.parametrize("pos", ["name", "phrase", "proverb", "suffix", "character"])
    def test_entries_that_are_not_single_word_vocabulary_are_ignored(self, pos):
        """`name` is a proper noun, which CLAUDE.md excludes entirely; the rest
        are not lemmas the lexicon ever holds."""
        assert upos_candidates(pos) == ()
