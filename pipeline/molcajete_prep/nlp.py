"""Tokenization and lemmatization.

The one place spaCy is allowed to appear. Downstream modules see `Token`, which
is plain data.

A note on whitespace, because SPEC Appendix A is misleading here. The pseudocode
branches on `tok.is_space` and appends a `{"s": ..., "ws": true}` token, implying
spaCy emits whitespace as tokens. It does not: the tokenizer attaches trailing
whitespace to the *preceding* token as `tok.whitespace_` and produces no space
tokens at all. The bundle's whitespace tokens are therefore synthesized here.
The round-trip test — joining every surface reproduces the source paragraph
exactly — is what keeps that honest.
"""

from __future__ import annotations

from dataclasses import dataclass

import spacy
from spacy.language import Language

MODEL = "es_core_news_sm"

# Named entity recognition costs time and tells us nothing: proper nouns are
# identified by the PROPN part-of-speech tag, which the morphologizer provides.
_EXCLUDED_COMPONENTS = ("ner",)

# Parts of speech that are never vocabulary, whatever characters they contain.
_NON_WORD_POS = frozenset({"PUNCT", "SYM", "SPACE"})


@dataclass(frozen=True)
class Token:
    """One token, before lexicon keys exist.

    `lemma` and `pos` are None on whitespace tokens. `sentence` is the index of
    the sentence within the paragraph, used later to pull an example sentence
    for a card.
    """

    surface: str
    lemma: str | None
    pos: str | None
    is_whitespace: bool
    sentence: int

    @property
    def is_word(self) -> bool:
        """Whether this token counts as vocabulary.

        Appendix A uses `tok.is_alpha`, which drops apocopated and elided forms
        that matter a great deal in this book — `pa'`, `'onde`, `nomás`. The rule
        here is "has at least one letter and isn't punctuation", which keeps
        those and still excludes numerals, symbols and whitespace.
        """
        if self.is_whitespace or self.pos in _NON_WORD_POS:
            return False
        return any(character.isalpha() for character in self.surface)

    @property
    def is_proper_noun(self) -> bool:
        return self.pos == "PROPN"


def load_pipeline(model: str = MODEL) -> Language:
    """Load the Spanish pipeline.

    Deterministic: the same text always yields the same tokens, lemmas and tags,
    which is what lets a rebuild of a bundle be byte-identical.
    """
    return spacy.load(model, exclude=list(_EXCLUDED_COMPONENTS))


def _tokens_from_doc(doc) -> list[Token]:
    sentence_of: dict[int, int] = {}
    for index, sentence in enumerate(doc.sents):
        for token in sentence:
            sentence_of[token.i] = index

    tokens: list[Token] = []
    for token in doc:
        sentence = sentence_of.get(token.i, 0)
        tokens.append(
            Token(
                surface=token.text,
                lemma=token.lemma_.lower() or None,
                pos=token.pos_,
                is_whitespace=False,
                sentence=sentence,
            )
        )
        if token.whitespace_:
            tokens.append(
                Token(
                    surface=token.whitespace_,
                    lemma=None,
                    pos=None,
                    is_whitespace=True,
                    sentence=sentence,
                )
            )
    return tokens


def tokenize(nlp: Language, paragraph: str) -> list[Token]:
    """Tokenize one paragraph."""
    return _tokens_from_doc(nlp(paragraph))


def tokenize_paragraphs(nlp: Language, paragraphs: list[str]) -> list[list[Token]]:
    """Tokenize many paragraphs, batched. Order is preserved."""
    return [_tokens_from_doc(doc) for doc in nlp.pipe(paragraphs, batch_size=64)]


def sentence_text(tokens: list[Token], sentence: int) -> str:
    """Reconstruct one sentence's text from a paragraph's tokens."""
    return "".join(t.surface for t in tokens if t.sentence == sentence).strip()
