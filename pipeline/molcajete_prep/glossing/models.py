"""What a gloss is, and how a Wiktionary part of speech becomes a spaCy one.

A gloss is card-sized by construction: `normalize_gloss` is the only way text
gets into one, and it enforces the one-to-three-words rule from the top down.
The rule is not decoration. A card shows the Spanish word, the German gloss
large and the English gloss small beneath it (SPEC §6.3); a dictionary sentence
in either slot turns the card into something you read rather than something you
recall, which is the whole failure mode this app exists to avoid.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

# A gloss carries at most this many comma-separated alternatives, each of at
# most this many words. "der Bau, die Höhle" passes; "unterirdischer Unterschlupf
# eines Tieres" does not.
MAX_UNITS = 3
MAX_WORDS_PER_UNIT = 3


class GlossSource(str, Enum):
    """Where a gloss came from. Reported, never written to the bundle."""

    DE_WIKTIONARY = "de-wiktionary"
    EN_WIKTIONARY = "en-wiktionary"
    CLAUDE = "claude"


@dataclass(frozen=True)
class Gloss:
    """One lemma's glosses, in both languages, with their provenance.

    `de` and `en` are independent: Wiktionary routinely has one and not the
    other, and the Claude pass fills whichever is missing. Either may be None,
    which the report counts and the bundle writer omits.
    """

    lemma: str
    pos: str  # spaCy UPOS, matching LexiconRecord.pos
    de: str | None = None
    en: str | None = None
    de_source: GlossSource | None = None
    en_source: GlossSource | None = None
    mexicanism: bool = False
    region_note: str | None = None

    # Claude judged the string not to be a real Spanish word. `es_core_news_sm`
    # invents roughly one lemma in ten — `acaeceír`, `abrasadorar` — and this is
    # how many of those there are.
    not_spanish: bool = False

    # Claude's reading of a mangled lemma: `abalanzar él` -> `abalanzarse`.
    # Diagnostic only. Never applied: the lemma string is half the lexicon key,
    # so rewriting it here would orphan every token that points at this entry.
    corrected_lemma: str | None = None

    @property
    def has_german(self) -> bool:
        return bool(self.de)

    @property
    def has_english(self) -> bool:
        return bool(self.en)

    def merged_with(self, other: Gloss) -> Gloss:
        """Fill this gloss's gaps from `other`, keeping what is already here.

        Sources are consulted in priority order and each one merges into the
        running result, so an earlier source always wins a field it filled.
        """
        return Gloss(
            lemma=self.lemma,
            pos=self.pos,
            de=self.de or other.de,
            en=self.en or other.en,
            de_source=self.de_source if self.de else other.de_source,
            en_source=self.en_source if self.en else other.en_source,
            mexicanism=self.mexicanism or other.mexicanism,
            region_note=self.region_note or other.region_note,
            not_spanish=self.not_spanish or other.not_spanish,
            corrected_lemma=self.corrected_lemma or other.corrected_lemma,
        )


# wiktextract's part of speech is coarser than spaCy's, so one Wiktionary entry
# can answer for several lexicon keys. `verb` covers both VERB and AUX because
# spaCy tags `ser` and `haber` as AUX while Wiktionary calls them verbs; `conj`
# covers CCONJ and SCONJ for the same reason. The lexicon key `(lemma, pos)`
# then picks whichever one actually occurs in the book.
#
# Parts of speech absent from this table are dropped: `name` is a proper noun,
# which CLAUDE.md excludes entirely, and `phrase`, `proverb`, `prefix`,
# `suffix`, `character` and `punct` are not single-word vocabulary.
WIKTEXTRACT_POS_TO_UPOS: dict[str, tuple[str, ...]] = {
    "noun": ("NOUN",),
    "verb": ("VERB", "AUX"),
    "adj": ("ADJ",),
    "adv": ("ADV",),
    "prep": ("ADP",),
    "prep_phrase": ("ADP",),
    "postp": ("ADP",),
    "conj": ("CCONJ", "SCONJ"),
    "det": ("DET",),
    "article": ("DET",),
    "pron": ("PRON",),
    "num": ("NUM", "DET"),
    "intj": ("INTJ",),
    "particle": ("PART",),
    # `al` and `del` — spaCy tags them ADP, but editions disagree.
    "contraction": ("ADP", "DET", "PRON"),
}


def upos_candidates(wiktextract_pos: str) -> tuple[str, ...]:
    """The spaCy tags a Wiktionary entry may answer for. Empty means ignore it."""
    return WIKTEXTRACT_POS_TO_UPOS.get(wiktextract_pos.strip().lower(), ())


# Parenthesized and bracketed asides: "(Mexico) cool", "burrow [of an animal]".
_ASIDE = re.compile(r"[(\[{][^)\]}]*[)\]}]")
# English Wiktionary writes verbs as infinitives; the card front is the Spanish
# lemma, so "to burrow" would put an English artefact on a Spanish flashcard.
_ENGLISH_INFINITIVE = re.compile(r"^to\s+", re.IGNORECASE)
_SEPARATORS = re.compile(r"\s*[,;/]\s*")
_WHITESPACE = re.compile(r"\s+")


def _clean_unit(unit: str) -> str:
    unit = _ENGLISH_INFINITIVE.sub("", unit)
    return _WHITESPACE.sub(" ", unit).strip(" .:-—– ")


def normalize_gloss(text: str | None) -> str | None:
    """Reduce dictionary prose to a card-sized gloss, or None if nothing survives.

    Truncating rather than rejecting is deliberate: a Wiktionary entry whose
    first alternative is usable is worth keeping even when the four that follow
    are not. Whether the result was *shortened* is a separate question, which
    `is_card_sized` answers on the original text — the report counts those so a
    silent quality drop stays visible.
    """
    if not text:
        return None

    units: list[str] = []
    for raw in _SEPARATORS.split(_ASIDE.sub(" ", text)):
        unit = _clean_unit(raw)
        if not unit or unit in units:
            continue
        units.append(unit)
        if len(units) == MAX_UNITS:
            break

    return ", ".join(units) or None


def is_card_sized(text: str | None) -> bool:
    """Whether `text` already meets the card bar without being cut down.

    This is the gate that decides whether a German Wiktionary gloss is used
    verbatim or handed to Claude to condense. "Buch" passes; "Bau, Höhle,
    unterirdischer Unterschlupf eines Tieres" does not.
    """
    if not text:
        return False

    units = [_clean_unit(u) for u in _SEPARATORS.split(_ASIDE.sub(" ", text))]
    units = [u for u in units if u]
    if not units or len(units) > MAX_UNITS:
        return False
    return all(len(unit.split()) <= MAX_WORDS_PER_UNIT for unit in units)
