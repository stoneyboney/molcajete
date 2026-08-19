"""Tests for the SPEC §8 Anki seed.

The seed's job is to stop the app teaching you words you already know. Getting
the wrong column silently seeds German, which would be worse than no seed at
all: a lemma marked known is never taught *and* counts as covered, so the app
would quietly skip words you actually need.
"""

from __future__ import annotations

import json

import pytest

from molcajete_prep.seed import (
    choose_field,
    clean_field,
    dumps,
    lemmas_from_values,
    merge,
    read_rows,
    score_fields,
    seed_from_text,
)


class TestCleanField:
    def test_strips_html(self):
        assert clean_field("<b>el gato</b>") == "el gato"

    def test_keeps_the_answer_of_a_cloze(self):
        # The word the note is about is the one inside the deletion.
        assert clean_field("{{c1::hablar}}") == "hablar"
        assert clean_field("{{c1::hablar::verbo}}") == "hablar"

    def test_drops_sound_tags(self):
        assert clean_field("la sierra[sound:sierra.mp3]") == "la sierra"

    def test_unescapes_entities(self):
        assert clean_field("die H&auml;user") == "die Häuser"

    def test_collapses_whitespace_including_nbsp(self):
        assert clean_field("el  perro\n") == "el perro"


class TestReadRows:
    def test_drops_ankis_header_lines(self, anki_export):
        rows = read_rows(anki_export)

        assert all(not row[0].startswith("#") for row in rows)
        assert len(rows) == 10

    def test_splits_on_tabs(self, anki_export):
        rows = read_rows(anki_export)

        assert rows[0] == ["der Hund", "el perro", "A1"]


class TestFieldChoice:
    """Which column is the Spanish is a question answered by looking."""

    def test_finds_the_spanish_column_even_when_it_is_not_first(self, anki_export):
        rows = read_rows(anki_export)

        assert choose_field(score_fields(rows)) == 1

    def test_the_german_column_scores_far_below_the_spanish_one(self, anki_export):
        # Not merely below: the test is comparative, so the separation is wide.
        # "Has Spanish seen this word" would say yes to Hund (zipf 1.67).
        scores = score_fields(read_rows(anki_export))

        assert scores[1].ratio > 0.9
        assert scores[0].ratio < 0.2

    def test_a_column_of_deck_tags_cannot_win(self, anki_export):
        # "A1" is one letter after the digits are stripped, and `a` is a very
        # common Spanish word. Without a length floor the tags score 100%.
        scores = score_fields(read_rows(anki_export))

        assert scores[2].sampled == 0
        assert choose_field(scores) == 1

    def test_an_empty_export_is_an_error_rather_than_an_empty_seed(self):
        with pytest.raises(ValueError):
            choose_field(score_fields([]))


class TestLemmas:
    def test_lemmatizes_inflected_forms(self, nlp):
        lemmas = lemmas_from_values(["las casas", "dijo"], nlp=nlp)

        assert "casa" in lemmas
        assert "decir" in lemmas

    def test_drops_proper_nouns(self, nlp):
        # §5 never teaches one, so seeding it would record a fact nothing reads.
        lemmas = lemmas_from_values(["México"], nlp=nlp)

        assert "méxico" not in lemmas

    def test_splits_multi_value_fields(self, nlp):
        lemmas = lemmas_from_values(["las ganas; el deseo"], nlp=nlp)

        assert "gana" in lemmas or "ganas" in lemmas
        assert "deseo" in lemmas

    def test_keeps_apocopated_and_regional_forms(self, nlp):
        # `nomás` is exactly what a Mexican deck is worth having in it.
        lemmas = lemmas_from_values(["nomás"], nlp=nlp)

        assert lemmas

    def test_everything_is_lowercase(self, nlp):
        lemmas = lemmas_from_values(["El Perro", "CORRER"], nlp=nlp)

        assert all(lemma == lemma.lower() for lemma in lemmas)


class TestSeedFromText:
    def test_reads_the_export_end_to_end(self, anki_export, nlp):
        lemmas, chosen, _scores = seed_from_text(anki_export, nlp=nlp)

        assert chosen == 1
        assert "perro" in lemmas
        assert "correr" in lemmas
        assert "sierra" in lemmas

    def test_does_not_seed_the_german(self, anki_export, nlp):
        lemmas, _chosen, _scores = seed_from_text(anki_export, nlp=nlp)

        for german in ("hund", "katze", "laufen", "sprechen"):
            assert german not in lemmas

    def test_field_overrides_the_guess(self, anki_export, nlp):
        lemmas, chosen, _scores = seed_from_text(anki_export, field=0, nlp=nlp)

        assert chosen == 0
        assert "perro" not in lemmas

    def test_a_field_out_of_range_is_an_error(self, anki_export, nlp):
        with pytest.raises(ValueError, match="columns"):
            seed_from_text(anki_export, field=9, nlp=nlp)

    def test_an_export_with_no_notes_is_an_error(self, nlp):
        with pytest.raises(ValueError, match="no notes"):
            seed_from_text("#separator:tab\n#html:true\n", nlp=nlp)


class TestMergeAndFormat:
    def test_merging_unions_rather_than_replaces(self):
        # SPEC §8: re-runnable at any time, as the deck grows.
        assert merge(["perro", "gato"], ["gato", "casa"]) == ["casa", "gato", "perro"]

    def test_merging_is_case_insensitive(self):
        assert merge(["Perro"], ["perro"]) == ["perro"]

    def test_the_output_is_the_flat_array_the_pipeline_already_reads(self):
        # `cli.load_known_lemmas` and `classify.classify_all` both predate this
        # module and both expect exactly this shape.
        parsed = json.loads(dumps(["gato", "perro", "gato"]))

        assert parsed == ["gato", "perro"]

    def test_the_output_is_sorted_so_a_re_run_diffs_cleanly(self):
        assert json.loads(dumps(["perro", "casa"])) == ["casa", "perro"]


class TestRoundTripIntoTheClassifier:
    def test_a_seeded_lemma_is_no_longer_taught(self, anki_export, nlp):
        """The whole point, end to end."""
        from molcajete_prep.classify import Classification, LexiconEntry, classify_all

        lemmas, _chosen, _scores = seed_from_text(anki_export, nlp=nlp)
        entries = {
            "m1": LexiconEntry(
                lemma="perro", pos="NOUN", zipf=4.5, book_count=9, first_chapter=0
            ),
            "m2": LexiconEntry(
                lemma="fusil", pos="NOUN", zipf=2.1, book_count=9, first_chapter=0
            ),
        }

        results = classify_all(entries, frozenset(lemmas))

        assert results["m1"].classification is Classification.ALREADY_KNOWN
        assert results["m2"].is_teach


class TestTheShippedTestDeck:
    """`make_test_deck.py` exists so the seed path can be exercised without a
    real Anki export. If it stops round-tripping, the first thing anyone tries
    after reading the README stops working."""

    def _deck(self):
        import sys

        sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
        from make_test_deck import export_text, load_deck

        return load_deck(), export_text

    def test_the_list_has_no_duplicate_words(self):
        deck, _ = self._deck()
        spanish = [word for word, _german in deck]

        assert len(set(spanish)) == len(spanish)

    def test_it_holds_a_thousand_words(self):
        deck, _ = self._deck()

        assert len(deck) == 1000

    def test_every_entry_has_both_halves(self):
        deck, _ = self._deck()

        assert all(spanish and german for spanish, german in deck)

    def test_no_gloss_is_long_enough_to_be_a_definition(self):
        # The cache-sourced tail is unreviewed, so this is the one guard on it.
        deck, _ = self._deck()

        assert max(len(german) for _spanish, german in deck) <= 32

    def test_the_spanish_column_is_second_so_detection_has_to_work(self):
        # Column 0 being the target language would let a broken reader pass.
        _deck, export_text = self._deck()
        rows = read_rows(export_text(20))

        assert choose_field(score_fields(rows)) == 1

    def test_the_german_column_is_unmistakably_not_spanish(self):
        _deck, export_text = self._deck()
        scores = score_fields(read_rows(export_text(1000)))

        assert scores[0].ratio < 0.2
        assert scores[1].ratio > 0.9

    def test_it_seeds_the_words_it_claims_to(self, nlp):
        _deck, export_text = self._deck()
        lemmas, chosen, _scores = seed_from_text(export_text(200), nlp=nlp)

        assert chosen == 1
        # Nouns are written with their article; the seed has to reduce them.
        assert "casa" in lemmas
        assert "hombre" in lemmas
        # Verbs are already infinitives.
        assert "hablar" in lemmas
        # And no German leaked in.
        assert "haus" not in lemmas
        assert "der" not in lemmas

    def test_asking_for_more_than_it_holds_is_an_error(self):
        _deck, export_text = self._deck()

        with pytest.raises(SystemExit):
            export_text(10_000)

    def test_a_thousand_words_seeds_far_more_than_two_hundred(self, nlp):
        _deck, export_text = self._deck()
        small, _c, _s = seed_from_text(export_text(200), nlp=nlp)
        large, _c, _s = seed_from_text(export_text(1000), nlp=nlp)

        assert len(small) >= 190
        assert len(large) >= 950
        assert small <= large
