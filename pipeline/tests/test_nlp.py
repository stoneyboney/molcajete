from __future__ import annotations

import pytest

from molcajete_prep.epub import extract_chapters
from molcajete_prep.nlp import sentence_text, tokenize, tokenize_paragraphs


class TestRoundTrip:
    """The load-bearing test of this module.

    SPEC Appendix A implies spaCy emits whitespace tokens. It does not, so the
    `ws` tokens are synthesized from `token.whitespace_`. If that synthesis is
    wrong the reader silently renders text with words glued together, and these
    assertions are the only thing that would catch it.
    """

    def test_surfaces_rejoin_into_the_source_paragraph(self, nlp):
        paragraph = "Agarró su fusil, montó el caballo y no volvió la cabeza."

        tokens = tokenize(nlp, paragraph)

        assert "".join(t.surface for t in tokens) == paragraph

    @pytest.mark.parametrize(
        "paragraph",
        [
            "Uno.",
            "—¡Ora sí, compadre! —dijo Anastasio.",
            "Los soldados —federales, se entiende— venían por el camino.",
            "«Nomás pa' que veas», dijo, y se rió.",
            "Cien pesos; ni uno más, ni uno menos...",
            "¿Quién anda ahí? ¡Demetrio!",
        ],
    )
    def test_surfaces_rejoin_for_awkward_punctuation(self, nlp, paragraph):
        tokens = tokenize(nlp, paragraph)

        assert "".join(t.surface for t in tokens) == paragraph

    def test_surfaces_rejoin_for_every_paragraph_of_the_fixture(
        self, nlp, fixture_epub
    ):
        for chapter in extract_chapters(str(fixture_epub)):
            for paragraph in chapter.paragraphs:
                tokens = tokenize(nlp, paragraph)

                assert "".join(t.surface for t in tokens) == paragraph


class TestWordClassification:
    def test_lemmas_are_lowercased(self, nlp):
        tokens = tokenize(nlp, "Agarró el fusil.")

        assert [t.lemma for t in tokens if t.is_word] == ["agarrar", "el", "fusil"]

    def test_punctuation_is_not_a_word(self, nlp):
        tokens = tokenize(nlp, "sí, claro.")

        assert [t.surface for t in tokens if t.is_word] == ["sí", "claro"]

    def test_whitespace_is_not_a_word(self, nlp):
        tokens = tokenize(nlp, "el caballo")

        assert [t.surface for t in tokens if t.is_whitespace] == [" "]
        assert not any(t.is_word for t in tokens if t.is_whitespace)

    def test_numerals_are_not_words(self, nlp):
        tokens = tokenize(nlp, "En 1914 llegaron.")

        assert "1914" not in [t.surface for t in tokens if t.is_word]

    def test_elided_forms_are_words(self, nlp):
        # Appendix A's `is_alpha` rule would drop these; this book is full of them.
        tokens = tokenize(nlp, "Nomás pa' que veas.")

        surfaces = [t.surface for t in tokens if t.is_word]
        assert "pa'" in surfaces or "pa" in surfaces

    def test_proper_nouns_are_flagged(self, nlp):
        tokens = tokenize(nlp, "Demetrio Macías miró la sierra.")

        assert [t.surface for t in tokens if t.is_proper_noun] == ["Demetrio", "Macías"]


class TestSentences:
    def test_sentence_index_separates_sentences(self, nlp):
        tokens = tokenize(nlp, "Vino Demetrio. Se fue el caballo.")

        assert {t.sentence for t in tokens} == {0, 1}

    def test_sentence_text_reconstructs_a_sentence(self, nlp):
        tokens = tokenize(nlp, "Vino Demetrio. Se fue el caballo.")

        assert sentence_text(tokens, 0) == "Vino Demetrio."
        assert sentence_text(tokens, 1) == "Se fue el caballo."


class TestBatching:
    def test_batched_tokenization_matches_one_at_a_time(self, nlp):
        paragraphs = ["Vino Demetrio.", "Se fue el caballo.", "La sierra calló."]

        batched = tokenize_paragraphs(nlp, paragraphs)

        assert batched == [tokenize(nlp, p) for p in paragraphs]

    def test_tokenization_is_deterministic(self, nlp):
        paragraph = "Demetrio limpiaba su fusil todas las noches."

        assert tokenize(nlp, paragraph) == tokenize(nlp, paragraph)
