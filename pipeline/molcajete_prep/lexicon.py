"""Building the lexicon: keys, frequencies and example sentences.

Lexicon identity is `(lemma, pos)`, not the lemma alone. `bajo` the adjective and
`bajo` the preposition are separate entries because in Phase 2 they take
different German glosses, and a card that offers both is a card that teaches
neither.

Proper nouns get no entry at all. CLAUDE.md: "PROPN is skipped entirely — no
card, no gloss." A lexicon entry exists to be taught or tapped; a name is
neither, so it stays out of the file rather than sitting in it unreferenced.
They are still counted, for the report.

That makes a mis-tag expensive: a common noun wrongly tagged PROPN vanishes from
the book with no card, no gloss and nothing in the output to show it was ever
there. `es_core_news_sm` does exactly this — in isolation it tags both `Brilla`
and `fusil` as PROPN — and 1915 prose gives it plenty of chances. So the decision
is made per lemma over the whole book rather than per token: see
`_resolve_proper_nouns`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from wordfreq import zipf_frequency

from molcajete_prep.classify import LemmaKey, LexiconEntry
from molcajete_prep.nlp import Token, sentence_text

LANGUAGE = "es"

# SPEC §4 uses four-digit keys (m0031, m0777). Widened automatically for a book
# with more than 10,000 distinct lemmas.
_MIN_KEY_DIGITS = 4

Identity = tuple[str, str]

# chapter index, paragraph index within the chapter, sentence index within it
Location = tuple[int, int, int]


@dataclass(frozen=True)
class LexiconRecord:
    """One lexicon entry, with the bookkeeping the bundle writer needs."""

    key: LemmaKey
    lemma: str
    pos: str
    zipf: float
    book_count: int
    chapters: frozenset[int]
    first_location: Location

    @property
    def first_chapter(self) -> int:
        return self.first_location[0]

    def to_classification_entry(self, *, mexicanism: bool = False) -> LexiconEntry:
        """The view of this record that the §5 rules consume."""
        return LexiconEntry(
            lemma=self.lemma,
            pos=self.pos,
            zipf=self.zipf,
            book_count=self.book_count,
            first_chapter=self.first_chapter,
            mexicanism=mexicanism,
        )


@dataclass(frozen=True)
class Lexicon:
    records: dict[LemmaKey, LexiconRecord]
    keys_by_identity: dict[Identity, LemmaKey]
    chapter_keys: list[frozenset[LemmaKey]]
    proper_noun_lemmas: frozenset[str] = field(default=frozenset())
    rescued_pos: dict[str, str] = field(default_factory=dict)

    def key_for(self, token: Token) -> LemmaKey | None:
        """The lexicon key a token points at, or None if it references nothing.

        Whitespace, punctuation, numerals and genuine proper nouns all return
        None.
        """
        if not token.is_word or token.lemma is None:
            return None
        if token.lemma in self.proper_noun_lemmas:
            return None
        return self.keys_by_identity.get((token.lemma, self.effective_pos(token)))

    def effective_pos(self, token: Token) -> str:
        """The token's part of speech after PROPN mis-tags are resolved."""
        pos = token.pos or ""
        if pos != "PROPN":
            return pos
        return self.rescued_pos.get(token.lemma or "", "NOUN")

    def entries_for_classification(self) -> dict[LemmaKey, LexiconEntry]:
        return {
            key: record.to_classification_entry()
            for key, record in self.records.items()
        }


@dataclass
class _Draft:
    """Mutable accumulator, collapsed into a LexiconRecord once the book is read."""

    lemma: str
    pos: str
    count: int = 0
    chapters: set[int] = field(default_factory=set)
    first_location: Location | None = None


def _key_width(distinct_lemmas: int) -> int:
    return max(_MIN_KEY_DIGITS, len(str(max(distinct_lemmas - 1, 0))))


def _is_capitalized(surface: str) -> bool:
    """Whether the first letter of a surface form is upper case."""
    for character in surface:
        if character.isalpha():
            return character.isupper()
    return False


def _word_tokens(
    chapters: Sequence[Sequence[Sequence[Token]]],
) -> Iterable[Token]:
    for paragraphs in chapters:
        for tokens in paragraphs:
            for token in tokens:
                if token.is_word and token.lemma is not None:
                    yield token


def _resolve_proper_nouns(
    chapters: Sequence[Sequence[Sequence[Token]]],
) -> tuple[frozenset[str], dict[str, str]]:
    """Decide which lemmas are really names, using the whole book as evidence.

    A single PROPN tag proves nothing: `es_core_news_sm` reaches for PROPN
    whenever a word is capitalized or unfamiliar, and 1915 Mexican prose is full
    of both. Taking it at face value would delete ordinary vocabulary from the
    bundle without a trace.

    A lemma is treated as a name only when the book never contradicts it: every
    occurrence tagged PROPN *and* every occurrence capitalized. One lowercase
    sighting, or one occurrence tagged NOUN, is enough to rescue it.

    Returns the confirmed names, plus the part of speech to use for the PROPN
    occurrences of a rescued lemma — its commonest other tag, or NOUN when it has
    none.
    """
    tags: dict[str, Counter[str]] = {}
    always_capitalized: dict[str, bool] = {}

    for token in _word_tokens(chapters):
        lemma = token.lemma or ""
        tags.setdefault(lemma, Counter())[token.pos or ""] += 1
        capitalized = _is_capitalized(token.surface)
        always_capitalized[lemma] = always_capitalized.get(lemma, True) and capitalized

    proper_nouns: set[str] = set()
    rescued_pos: dict[str, str] = {}

    for lemma, counts in tags.items():
        if "PROPN" not in counts:
            continue
        if set(counts) == {"PROPN"} and always_capitalized[lemma]:
            proper_nouns.add(lemma)
            continue

        others = Counter({pos: n for pos, n in counts.items() if pos != "PROPN"})
        # Ties break alphabetically so that a rebuild cannot flip the choice.
        rescued_pos[lemma] = (
            min(others, key=lambda pos: (-others[pos], pos)) if others else "NOUN"
        )

    return frozenset(proper_nouns), rescued_pos


def build_lexicon(chapters: Sequence[Sequence[Sequence[Token]]]) -> Lexicon:
    """Build the lexicon from tokenized chapters.

    `chapters[c][p]` is the token list of paragraph `p` in chapter `c`.

    Keys are assigned after sorting identities alphabetically, not in encounter
    order, so that rebuilding the same EPUB produces byte-identical output and a
    diff between two bundle versions stays readable.
    """
    proper_nouns, rescued_pos = _resolve_proper_nouns(chapters)
    drafts: dict[Identity, _Draft] = {}

    def identity_of(token: Token) -> Identity:
        pos = token.pos or ""
        if pos == "PROPN":
            pos = rescued_pos.get(token.lemma or "", "NOUN")
        return (token.lemma or "", pos)

    for chapter_index, paragraphs in enumerate(chapters):
        for paragraph_index, tokens in enumerate(paragraphs):
            for token in tokens:
                if not token.is_word or token.lemma is None:
                    continue
                if token.lemma in proper_nouns:
                    continue

                identity = identity_of(token)
                draft = drafts.get(identity)
                if draft is None:
                    draft = _Draft(lemma=identity[0], pos=identity[1])
                    drafts[identity] = draft

                draft.count += 1
                draft.chapters.add(chapter_index)
                if draft.first_location is None:
                    draft.first_location = (
                        chapter_index,
                        paragraph_index,
                        token.sentence,
                    )

    width = _key_width(len(drafts))
    records: dict[LemmaKey, LexiconRecord] = {}
    keys_by_identity: dict[Identity, LemmaKey] = {}

    for index, identity in enumerate(sorted(drafts)):
        draft = drafts[identity]
        key = f"m{index:0{width}d}"
        keys_by_identity[identity] = key
        records[key] = LexiconRecord(
            key=key,
            lemma=draft.lemma,
            pos=draft.pos,
            zipf=zipf_frequency(draft.lemma, LANGUAGE),
            book_count=draft.count,
            chapters=frozenset(draft.chapters),
            first_location=draft.first_location or (0, 0, 0),
        )

    chapter_keys = [
        frozenset(
            keys_by_identity[identity_of(token)]
            for tokens in paragraphs
            for token in tokens
            if token.is_word
            and token.lemma is not None
            and token.lemma not in proper_nouns
            and identity_of(token) in keys_by_identity
        )
        for paragraphs in chapters
    ]

    return Lexicon(
        records=records,
        keys_by_identity=keys_by_identity,
        chapter_keys=chapter_keys,
        proper_noun_lemmas=proper_nouns,
        rescued_pos=rescued_pos,
    )


def example_sentence(
    record: LexiconRecord,
    chapters: Sequence[Sequence[Sequence[Token]]],
) -> tuple[str, int] | None:
    """The first sentence in the book containing this lemma, and its chapter.

    Used for the example on a card, so it is only worth computing for lemmas that
    become cards.
    """
    chapter_index, paragraph_index, sentence_index = record.first_location
    try:
        tokens = chapters[chapter_index][paragraph_index]
    except IndexError:
        return None

    text = sentence_text(list(tokens), sentence_index)
    if not text:
        return None
    return text, chapter_index
