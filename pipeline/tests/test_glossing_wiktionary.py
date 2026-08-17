"""Tests for the wiktextract readers.

Every fixture in this file is shaped after a record pulled from the live
kaikki.org dumps in August 2026 — `chido`, `popote`, `carro`, `ordenador`,
`banco`, `lunes`. The tag vocabulary (`Mexico`, `Latin-America`, `Spain`,
`Mexican Spanish`, `Peninsular Spanish`) is what the dumps actually emit, not
what seemed plausible.
"""

from __future__ import annotations

import gzip
import json

import pytest

from molcajete_prep.glossing.models import Gloss, GlossSource
from molcajete_prep.glossing.sources import iter_spanish_records, looks_spanish
from molcajete_prep.glossing.wiktionary import (
    gloss_from_record,
    index_records,
    read_extract,
    region_note,
    sense_is_mexican,
    usable_senses,
)

EN = GlossSource.EN_WIKTIONARY
DE = GlossSource.DE_WIKTIONARY


def record(word, pos, senses, *, lang_code="es", lang="Spanish"):
    return {"word": word, "pos": pos, "lang": lang, "lang_code": lang_code, "senses": senses}


def sense(*glosses, tags=None, categories=None, **extra):
    built = {"glosses": list(glosses)}
    if tags is not None:
        built["tags"] = tags
    if categories is not None:
        built["categories"] = categories
    built.update(extra)
    return built


CHIDO = record(
    "chido", "adj", [sense("cool, awesome", tags=["Mexico"], categories=["Mexican Spanish"])]
)

# Two senses: the general one and the Latin-American one. The entry carries no
# peninsular marker, which is what keeps `carro` off the mexicanism list.
CARRO = record(
    "carro",
    "noun",
    [
        sense("cart", tags=["masculine"]),
        sense(
            "car, automobile",
            tags=["Latin-America", "masculine"],
            categories=["Latin American Spanish"],
        ),
    ],
)

BANCO = record(
    "banco",
    "verb",
    [
        sense(
            "first-person singular present indicative of bancar",
            tags=["first-person", "form-of", "indicative", "present", "singular"],
            form_of=[{"word": "bancar"}],
        )
    ],
)


class TestSenseSelection:
    def test_the_most_specific_gloss_in_a_hierarchy_wins(self):
        """`glosses` is parent-then-subsense; the last element is the one that
        actually applies."""
        built = gloss_from_record(
            record("libre", "adj", [sense("Unconstrained.", "Free, unfettered.")]),
            source=EN,
        )

        assert built is not None
        assert built.gloss.en == "Free, unfettered"

    def test_form_of_senses_are_dropped_entirely(self):
        """'first-person singular present indicative of bancar' is true and
        useless — as a card it teaches the wrong thing."""
        assert usable_senses(BANCO) == []
        assert gloss_from_record(BANCO, source=EN) is None

    def test_a_sense_marked_only_by_form_of_is_still_dropped(self):
        untagged = record("cantado", "verb", [sense("past participle of cantar", form_of=[{"word": "cantar"}])])

        assert usable_senses(untagged) == []

    def test_archaic_senses_sort_last_but_are_not_discarded(self):
        """A word can be in a 1915 novel precisely because it is archaic, and a
        dated gloss beats no gloss."""
        entry = record(
            "fusil",
            "noun",
            [sense("flintlock", tags=["archaic"]), sense("rifle", tags=["masculine"])],
        )

        assert [s["glosses"][-1] for s in usable_senses(entry)] == ["rifle", "flintlock"]

    def test_an_entry_with_only_archaic_senses_still_yields_a_gloss(self):
        entry = record("acaecer", "verb", [sense("to befall", tags=["archaic"])])

        built = gloss_from_record(entry, source=EN)

        assert built is not None and built.gloss.en == "befall"

    def test_a_record_with_no_usable_sense_yields_nothing(self):
        assert gloss_from_record(record("x", "noun", []), source=EN) is None

    def test_a_record_without_a_word_yields_nothing(self):
        assert gloss_from_record(record("", "noun", [sense("something")]), source=EN) is None


class TestDefinitionsGoToClaude:
    """Both editions write definitions as readily as translations. A definition
    clipped to three words is worse than either — "Not imprisoned or" teaches
    nothing and looks deliberate — so long text becomes context for the Claude
    pass instead of card text."""

    def test_a_long_english_definition_is_not_used_as_a_gloss(self):
        built = gloss_from_record(
            record(
                "diccionario",
                "noun",
                [sense("A reference work listing words from one or more languages")],
            ),
            source=EN,
        )

        assert built is not None
        assert built.gloss.en is None
        assert built.gloss.en_source is None
        assert built.raw_en.startswith("A reference work")

    def test_a_short_german_definition_is_still_a_definition(self):
        """German Wiktionary glosses `lunes` as "der erste Wochentag", which is
        three words and therefore passes the size gate. This is the known limit
        of sizing alone: the card would read like a riddle. The trial run is
        what measures how often it happens."""
        built = gloss_from_record(
            record("lunes", "noun", [sense("der erste Wochentag")], lang="Spanisch"),
            source=DE,
        )

        assert built is not None
        assert built.gloss.de == "der erste Wochentag"

    def test_a_long_german_definition_goes_to_claude_with_its_text(self):
        built = gloss_from_record(
            record(
                "madriguera",
                "noun",
                [sense("unterirdischer Unterschlupf eines Tieres")],
                lang="Spanisch",
            ),
            source=DE,
        )

        assert built is not None
        assert built.gloss.de is None
        assert built.raw_de == "unterirdischer Unterschlupf eines Tieres"

    def test_wiktionary_text_is_kept_even_when_its_gloss_was_accepted(self):
        """The model should see what Wiktionary thought even where we took its
        answer, so it can correct a sense the example sentence contradicts."""
        built = gloss_from_record(CHIDO, source=EN)

        assert built.gloss.en == "cool, awesome"
        assert built.raw_en == "cool, awesome"

    def test_the_sense_labels_travel_along_as_a_hint(self):
        built = gloss_from_record(CHIDO, source=EN)

        assert built.region_hint == "Mexico"


class TestMexicanism:
    def test_an_explicit_mexico_tag_is_taken_at_face_value(self):
        assert sense_is_mexican(CHIDO["senses"][0], entry_is_peninsular_anywhere=False) is True

    def test_the_mexican_spanish_category_alone_is_enough(self):
        only_category = sense("drinking straw", categories=["Mexican Spanish"])

        assert sense_is_mexican(only_category, entry_is_peninsular_anywhere=False) is True

    def test_latin_american_alone_is_not_a_mexicanism(self):
        """A Latin-American label is the norm in a Mexican novel. Flagging it
        would teach half the book, since mexicanism && bookCount >= 2 teaches
        whatever it marks."""
        latin_american = CARRO["senses"][1]

        assert sense_is_mexican(latin_american, entry_is_peninsular_anywhere=False) is False

    def test_latin_american_counts_when_the_entry_also_has_a_peninsular_sense(self):
        """This is the 'where the peninsular sense differs' case: the contrast,
        not the region, is what makes the word worth a card."""
        latin_american = CARRO["senses"][1]

        assert sense_is_mexican(latin_american, entry_is_peninsular_anywhere=True) is True

    def test_an_unmarked_sense_is_not_a_mexicanism(self):
        assert sense_is_mexican(sense("bench"), entry_is_peninsular_anywhere=True) is False

    def test_the_flag_follows_the_glossed_sense_not_the_whole_entry(self):
        """`carro` glosses to 'cart', which is not regional. Marking that card
        Latin-American because a later sense is would put a false claim on it."""
        built = gloss_from_record(CARRO, source=EN)

        assert built is not None
        assert built.gloss.en == "cart"
        assert built.gloss.mexicanism is False
        assert built.gloss.region_note is None

    def test_a_mexican_entry_carries_both_the_flag_and_a_note(self):
        built = gloss_from_record(CHIDO, source=EN)

        assert built is not None
        assert built.gloss.mexicanism is True
        assert built.gloss.region_note == "Mexiko"


class TestRegionNote:
    def test_regions_are_written_in_german(self):
        """CLAUDE.md: every user-facing string in the app is German. The note
        renders on the card beside a German gloss."""
        assert region_note(sense("x", tags=["Mexico"])) == "Mexiko"
        assert region_note(sense("x", tags=["Latin-America"])) == "Lateinamerika"

    def test_region_comes_before_register(self):
        note = region_note(sense("x", tags=["colloquial", "Mexico"]))

        assert note == "Mexiko, umgangssprachlich"

    def test_grammatical_tags_are_not_regional_information(self):
        assert region_note(sense("x", tags=["masculine", "plural"])) is None

    def test_a_register_without_a_region_still_earns_a_note(self):
        assert region_note(sense("x", tags=["vulgar"])) == "vulgär"

    def test_synonymous_registers_are_not_repeated(self):
        assert region_note(sense("x", tags=["colloquial", "informal"])) == "umgangssprachlich"

    def test_a_note_stays_short_enough_to_be_a_chip(self):
        note = region_note(
            sense("x", tags=["Mexico", "Spain", "colloquial", "vulgar", "humorous"])
        )

        assert len(note.split(", ")) == 3

    def test_a_note_is_set_even_when_the_word_is_not_a_mexicanism(self):
        """`carro` for 'car' is worth marking Lateinamerika even though it does
        not earn a card of its own under the §5 rules."""
        built = gloss_from_record(
            record("jugo", "noun", [CARRO["senses"][1]]), source=EN
        )

        assert built is not None
        assert built.gloss.mexicanism is False
        assert built.gloss.region_note == "Lateinamerika"


class TestIndexing:
    def test_a_verb_is_indexed_under_both_verb_and_aux(self):
        """spaCy tags `ser` and `haber` AUX; Wiktionary calls them verbs. Without
        both, every auxiliary in the book loses its gloss."""
        index = index_records([record("ser", "verb", [sense("to be")])], source=EN)

        assert set(index) == {("ser", "VERB"), ("ser", "AUX")}
        assert index[("ser", "AUX")].gloss.en == "be"

    def test_the_english_edition_fills_english_and_leaves_german_empty(self):
        index = index_records([CHIDO], source=EN)

        gloss = index[("chido", "ADJ")].gloss
        assert gloss.en == "cool, awesome"
        assert gloss.en_source is EN
        assert gloss.de is None

    def test_the_german_edition_fills_german_and_leaves_english_empty(self):
        index = index_records(
            [record("amar", "verb", [sense("lieben, liebhaben, gernhaben")], lang="Spanisch")],
            source=DE,
        )

        gloss = index[("amar", "VERB")].gloss
        assert gloss.de == "lieben, liebhaben, gernhaben"
        assert gloss.de_source is DE
        assert gloss.en is None

    def test_lemmas_the_book_never_uses_are_dropped_as_they_stream_past(self):
        """The English edition holds three quarters of a million Spanish entries
        and a book needs nine thousand. Holding the rest would cost gigabytes."""
        index = index_records(
            [CHIDO, record("zutano", "noun", [sense("so-and-so")])],
            source=EN,
            wanted_lemmas={"chido"},
        )

        assert set(index) == {("chido", "ADJ")}

    def test_parts_of_speech_the_lexicon_never_holds_are_ignored(self):
        index = index_records(
            [record("Ciudad de México", "name", [sense("Mexico City")])], source=EN
        )

        assert index == {}

    def test_the_first_record_to_supply_a_gloss_wins(self):
        """Wiktionary splits a word across records when it has several
        etymologies."""
        index = index_records(
            [
                record("vino", "noun", [sense("wine")]),
                record("vino", "noun", [sense("something else")]),
            ],
            source=EN,
        )

        assert index[("vino", "NOUN")].gloss.en == "wine"

    def test_a_later_record_does_not_relabel_the_meaning_already_chosen(self):
        """A region label describes the sense it sits on. Carrying it across
        records attached it to a meaning it was never about — `mano` came out
        glossed "hand" and labelled "Mexiko, Slang" from the *bro* sense, and
        `coche` was labelled "Mexiko, Spanien" at once. Both were real."""
        index = index_records(
            [
                record("padre", "noun", [sense("father")]),
                record("padre", "noun", [sense("priest", tags=["Mexico"])]),
            ],
            source=EN,
        )

        assert index[("padre", "NOUN")].gloss.en == "father"
        assert index[("padre", "NOUN")].gloss.mexicanism is False
        assert index[("padre", "NOUN")].gloss.region_note is None

    def test_a_flag_is_kept_where_it_belongs_to_the_chosen_sense(self):
        """The other half of the same rule: `padre` the adjective *is* Mexican
        slang, and its own entry keeps the label."""
        index = index_records(
            [record("padre", "adj", [sense("great", tags=["Mexico"])])], source=EN
        )

        assert index[("padre", "ADJ")].gloss.mexicanism is True

    def test_a_second_record_may_still_supply_a_language_the_first_lacked(self):
        """Text merging is the whole point of running two editions."""
        index = index_records(
            [record("libro", "noun", [sense("book")])], source=EN
        )
        german = index_records(
            [record("libro", "noun", [sense("das Buch")], lang="Spanisch")], source=DE
        )
        merged = index[("libro", "NOUN")].gloss.text_filled_from(
            german[("libro", "NOUN")].gloss
        )

        assert (merged.en, merged.de) == ("book", "das Buch")

    def test_lemmas_are_lowercased_to_match_the_lexicon(self):
        index = index_records([record("Perro", "noun", [sense("dog")])], source=EN)

        assert ("perro", "NOUN") in index


class TestStreamingFromDisk:
    def test_only_spanish_records_come_out_of_a_mixed_dump(self, tmp_path):
        path = tmp_path / "extract.jsonl.gz"
        rows = [
            record("chido", "adj", [sense("cool")]),
            record("dog", "noun", [sense("perro")], lang_code="en", lang="English"),
            record("chien", "noun", [sense("dog")], lang_code="fr", lang="French"),
        ]
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")

        assert [r["word"] for r in iter_spanish_records(path)] == ["chido"]

    def test_an_english_entry_mentioning_spanish_is_filtered_out_after_parsing(self, tmp_path):
        """The byte pre-filter matches English entries whose translation lists
        name Spanish. Only the parsed top-level field settles it."""
        english_with_spanish_translation = {
            "word": "dictionary",
            "pos": "noun",
            "lang": "English",
            "lang_code": "en",
            "senses": [sense("a reference work")],
            "translations": [{"lang": "Spanish", "lang_code": "es", "word": "diccionario"}],
        }
        line = json.dumps(english_with_spanish_translation).encode()
        assert looks_spanish(line) is True

        path = tmp_path / "extract.jsonl.gz"
        with gzip.open(path, "wb") as handle:
            handle.write(line + b"\n")

        assert list(iter_spanish_records(path)) == []

    def test_a_malformed_line_does_not_cost_the_book_its_glosses(self, tmp_path):
        """Twenty million machine-generated lines from a wiki anyone can edit."""
        path = tmp_path / "extract.jsonl.gz"
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write('{"lang_code": "es", "word": "roto"')  # truncated
            handle.write("\n")
            handle.write(json.dumps(record("chido", "adj", [sense("cool")])) + "\n")

        assert [r["word"] for r in iter_spanish_records(path)] == ["chido"]

    def test_read_extract_streams_a_file_straight_into_an_index(self, tmp_path):
        path = tmp_path / "extract.jsonl.gz"
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write(json.dumps(CHIDO) + "\n")

        index = read_extract(path, source=EN, wanted_lemmas={"chido"})

        assert index[("chido", "ADJ")].gloss.en == "cool, awesome"

    @pytest.mark.parametrize(
        "line",
        [b'{"lang_code": "es"}', b'{"lang_code":"es"}'],
    )
    def test_the_pre_filter_survives_a_formatting_change(self, line):
        """A whitespace change in wiktextract's JSON writer would otherwise
        empty every gloss with no error."""
        assert looks_spanish(line) is True

    def test_the_pre_filter_rejects_lines_with_no_spanish_at_all(self):
        assert looks_spanish(b'{"lang_code": "fr", "word": "chien"}') is False


class TestMerging:
    def test_merging_keeps_what_is_already_filled(self):
        english = Gloss(lemma="chido", pos="ADJ", en="cool", en_source=EN)
        german = Gloss(lemma="chido", pos="ADJ", de="super", de_source=DE)

        merged = english.merged_with(german)

        assert (merged.en, merged.de) == ("cool", "super")
        assert (merged.en_source, merged.de_source) == (EN, DE)

    def test_merging_ors_the_flags_together(self):
        plain = Gloss(lemma="chido", pos="ADJ", en="cool")
        flagged = Gloss(lemma="chido", pos="ADJ", mexicanism=True, region_note="Mexiko")

        merged = plain.merged_with(flagged)

        assert merged.mexicanism is True
        assert merged.region_note == "Mexiko"


class TestRegionNoteFromCategories:
    """Wiktionary is inconsistent about tags versus categories. Reading only
    tags set `mexicanism` on category-only senses while leaving the note empty,
    which the bundle validator rejects — it surfaced on the first real book."""

    def test_a_category_only_mexicanism_still_gets_a_note(self):
        built = gloss_from_record(
            record(
                "popote",
                "noun",
                [sense("drinking straw", categories=["Mexican Spanish"])],
            ),
            source=EN,
        )

        assert built.gloss.mexicanism is True
        assert built.gloss.region_note == "Mexiko"

    def test_every_flagged_sense_carries_a_note(self):
        """The invariant the bundle validator enforces, checked at the source."""
        for categories in (["Mexican Spanish"], ["Latin American Spanish"]):
            for tags in ([], ["Mexico"], ["colloquial"]):
                built = gloss_from_record(
                    record("x", "noun", [sense("thing", tags=tags, categories=categories)]),
                    source=EN,
                )
                if built.gloss.mexicanism:
                    assert built.gloss.region_note, (tags, categories)

    def test_a_tag_and_its_category_are_not_repeated(self):
        built = gloss_from_record(
            record(
                "chido",
                "adj",
                [sense("cool", tags=["Mexico"], categories=["Mexican Spanish"])],
            ),
            source=EN,
        )

        assert built.gloss.region_note == "Mexiko"


class TestSensesUsedOnBothSidesOfTheAtlantic:
    """A sense labelled for Spain *and* Mexico is not a regional divergence.
    Real case: `coche` is "car" in both, and flagging it produced a card marked
    "Mexiko, Spanien" — a contradiction on its face."""

    def test_a_sense_marked_for_both_is_not_a_mexicanism(self):
        both = sense("car, automobile", tags=["Mexico", "Spain", "masculine"])

        assert sense_is_mexican(both, entry_is_peninsular_anywhere=True) is False

    def test_the_peninsular_category_settles_it_too(self):
        both = sense(
            "car", tags=["Mexico"], categories=["Mexican Spanish", "Peninsular Spanish"]
        )

        assert sense_is_mexican(both, entry_is_peninsular_anywhere=True) is False

    def test_a_mexico_only_sense_is_untouched(self):
        assert sense_is_mexican(
            sense("cool", tags=["Mexico"]), entry_is_peninsular_anywhere=True
        ) is True
