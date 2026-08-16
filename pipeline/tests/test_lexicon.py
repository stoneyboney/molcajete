from __future__ import annotations

from molcajete_prep.epub import extract_chapters
from molcajete_prep.lexicon import build_lexicon, example_sentence
from molcajete_prep.nlp import Token, tokenize_paragraphs


def word(lemma: str, pos: str = "NOUN", surface: str | None = None, sentence: int = 0):
    return Token(
        surface=surface or lemma,
        lemma=lemma,
        pos=pos,
        is_whitespace=False,
        sentence=sentence,
    )


def space():
    return Token(surface=" ", lemma=None, pos=None, is_whitespace=True, sentence=0)


class TestKeyAssignment:
    def test_keys_follow_the_spec_format(self):
        lexicon = build_lexicon([[[word("caballo")]]])

        assert list(lexicon.records) == ["m0000"]

    def test_keys_are_assigned_alphabetically_not_in_encounter_order(self):
        """Encounter order would make a key depend on where a word first appears,
        so an edit to chapter 1 would renumber the whole lexicon."""
        lexicon = build_lexicon([[[word("zapato"), word("agua"), word("mesa")]]])

        assert [r.lemma for r in lexicon.records.values()] == ["agua", "mesa", "zapato"]

    def test_key_assignment_is_independent_of_chapter_order(self):
        forwards = build_lexicon([[[word("agua")]], [[word("zapato")]]])
        backwards = build_lexicon([[[word("zapato")]], [[word("agua")]]])

        assert {r.key: r.lemma for r in forwards.records.values()} == {
            r.key: r.lemma for r in backwards.records.values()
        }

    def test_keys_widen_past_four_digits_for_a_large_lexicon(self):
        tokens = [word(f"palabra{i:05d}") for i in range(10_001)]

        lexicon = build_lexicon([[tokens]])

        assert lexicon.records["m00000"].lemma == "palabra00000"

    def test_building_twice_produces_identical_keys(self):
        chapters = [[[word("agua"), word("mesa"), word("zapato")]]]

        first = build_lexicon(chapters)
        second = build_lexicon(chapters)

        assert first.records == second.records


class TestIdentity:
    def test_the_same_lemma_under_two_parts_of_speech_gets_two_entries(self):
        """'bajo' is a preposition and an adjective. One entry would mean one
        German gloss for two unrelated words."""
        lexicon = build_lexicon([[[word("bajo", pos="ADP"), word("bajo", pos="ADJ")]]])

        assert len(lexicon.records) == 2
        assert {r.pos for r in lexicon.records.values()} == {"ADP", "ADJ"}

    def test_the_same_lemma_under_one_part_of_speech_is_one_entry(self):
        lexicon = build_lexicon([[[word("fusil")], [word("fusil")]]])

        assert len(lexicon.records) == 1


class TestCounts:
    def test_book_count_sums_across_the_whole_book(self):
        chapters = [
            [[word("sierra"), word("sierra")]],
            [[word("sierra")]],
        ]

        lexicon = build_lexicon(chapters)

        assert lexicon.records["m0000"].book_count == 3

    def test_first_chapter_is_the_earliest_chapter_of_occurrence(self):
        chapters = [[[word("agua")]], [[word("sierra")]], [[word("sierra")]]]

        lexicon = build_lexicon(chapters)

        sierra = next(r for r in lexicon.records.values() if r.lemma == "sierra")
        assert sierra.first_chapter == 1

    def test_chapters_records_every_chapter_of_occurrence(self):
        chapters = [[[word("sierra")]], [[word("agua")]], [[word("sierra")]]]

        lexicon = build_lexicon(chapters)

        sierra = next(r for r in lexicon.records.values() if r.lemma == "sierra")
        assert sierra.chapters == frozenset({0, 2})

    def test_chapter_keys_list_what_occurs_in_each_chapter(self):
        chapters = [[[word("sierra")]], [[word("agua")]]]

        lexicon = build_lexicon(chapters)

        assert len(lexicon.chapter_keys) == 2
        assert lexicon.chapter_keys[0] != lexicon.chapter_keys[1]


class TestExclusions:
    def test_proper_nouns_get_no_lexicon_entry(self):
        lexicon = build_lexicon(
            [[[word("demetrio", pos="PROPN", surface="Demetrio"), word("fusil")]]]
        )

        assert [r.lemma for r in lexicon.records.values()] == ["fusil"]

    def test_proper_nouns_are_still_counted_for_the_report(self):
        lexicon = build_lexicon(
            [
                [
                    [
                        word("demetrio", pos="PROPN", surface="Demetrio"),
                        word("macías", pos="PROPN", surface="Macías"),
                    ]
                ]
            ]
        )

        assert lexicon.proper_noun_lemmas == frozenset({"demetrio", "macías"})

    def test_whitespace_and_punctuation_get_no_entry(self):
        tokens = [word("fusil"), space(), word(".", pos="PUNCT", surface=".")]

        lexicon = build_lexicon([[tokens]])

        assert len(lexicon.records) == 1

    def test_key_for_returns_none_for_tokens_that_reference_nothing(self):
        lexicon = build_lexicon(
            [[[word("fusil"), word("demetrio", pos="PROPN", surface="Demetrio")]]]
        )

        assert lexicon.key_for(space()) is None
        assert lexicon.key_for(word("demetrio", pos="PROPN", surface="Demetrio")) is None
        assert lexicon.key_for(word("fusil")) == "m0000"


class TestProperNounResolution:
    """`es_core_news_sm` reaches for PROPN far too readily.

    Because a PROPN lemma is dropped from the bundle outright, an over-eager tag
    deletes real vocabulary silently. The decision is therefore made per lemma
    over the whole book, not per token.
    """

    def test_a_lowercase_lemma_tagged_propn_is_rescued(self):
        # spaCy really does tag 'fusil' as PROPN in a bare sentence.
        lexicon = build_lexicon([[[word("fusil", pos="PROPN", surface="fusil")]]])

        assert lexicon.proper_noun_lemmas == frozenset()
        assert lexicon.records["m0000"].lemma == "fusil"

    def test_a_rescued_lemma_with_no_other_tag_becomes_a_noun(self):
        lexicon = build_lexicon([[[word("fusil", pos="PROPN", surface="fusil")]]])

        assert lexicon.records["m0000"].pos == "NOUN"

    def test_a_rescued_lemma_takes_its_commonest_other_tag(self):
        tokens = [
            word("sierra", pos="PROPN", surface="Sierra"),
            word("sierra", pos="NOUN", surface="sierra"),
            word("sierra", pos="NOUN", surface="sierra"),
        ]

        lexicon = build_lexicon([[tokens]])

        assert len(lexicon.records) == 1
        assert lexicon.records["m0000"].pos == "NOUN"

    def test_a_sentence_initial_common_noun_merges_with_its_lowercase_uses(self):
        """'Sierra' at the start of a sentence must not become a second entry."""
        tokens = [
            word("sierra", pos="PROPN", surface="Sierra"),
            word("sierra", pos="NOUN", surface="sierra"),
        ]

        lexicon = build_lexicon([[tokens]])

        assert len(lexicon.records) == 1
        assert lexicon.records["m0000"].book_count == 2

    def test_a_consistently_capitalized_propn_is_kept_as_a_name(self):
        tokens = [
            word("demetrio", pos="PROPN", surface="Demetrio"),
            word("demetrio", pos="PROPN", surface="Demetrio"),
        ]

        lexicon = build_lexicon([[tokens]])

        assert lexicon.proper_noun_lemmas == frozenset({"demetrio"})
        assert lexicon.records == {}

    def test_one_lowercase_sighting_is_enough_to_rescue_a_lemma(self):
        tokens = [
            word("norte", pos="PROPN", surface="Norte"),
            word("norte", pos="PROPN", surface="Norte"),
            word("norte", pos="PROPN", surface="norte"),
        ]

        lexicon = build_lexicon([[tokens]])

        assert lexicon.proper_noun_lemmas == frozenset()
        assert lexicon.records["m0000"].book_count == 3


class TestFrequency:
    def test_zipf_comes_from_wordfreq(self):
        lexicon = build_lexicon([[[word("agua")]]])

        # 'agua' is a very common Spanish word; the exact value can drift with
        # the wordfreq data, so assert the band rather than the number.
        assert 4.5 < lexicon.records["m0000"].zipf < 6.5

    def test_an_unknown_lemma_scores_zero(self):
        lexicon = build_lexicon([[[word("qwertzuiop")]]])

        assert lexicon.records["m0000"].zipf == 0.0


class TestExampleSentences:
    def test_example_is_the_first_sentence_containing_the_lemma(self, nlp):
        paragraphs = tokenize_paragraphs(
            nlp, ["Llegó el caballo. Se fue el caballo."]
        )
        chapters = [paragraphs]

        lexicon = build_lexicon(chapters)
        caballo = next(r for r in lexicon.records.values() if r.lemma == "caballo")

        assert example_sentence(caballo, chapters) == ("Llegó el caballo.", 0)

    def test_example_reports_the_chapter_it_came_from(self, nlp):
        chapters = [
            tokenize_paragraphs(nlp, ["Nada aquí."]),
            tokenize_paragraphs(nlp, ["Brilla el fusil."]),
        ]

        lexicon = build_lexicon(chapters)
        fusil = next(r for r in lexicon.records.values() if r.lemma == "fusil")

        assert example_sentence(fusil, chapters) == ("Brilla el fusil.", 1)


class TestAgainstTheFixture:
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
