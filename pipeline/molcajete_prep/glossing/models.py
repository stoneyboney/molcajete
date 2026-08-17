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

# What a mexicanism says when nothing more specific is known. German, per
# CLAUDE.md's language rule — this renders on the card.
DEFAULT_REGION_NOTE = "Mexiko"


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

    def __post_init__(self) -> None:
        """Hold the one invariant the bundle format insists on.

        A card claiming Mexican usage without saying what kind is a claim the
        reader cannot act on, so `validate_bundle` rejects the pair. Enforcing it
        here rather than at each call site covers every way a Gloss comes into
        being — parsed from either Wiktionary edition, returned by Claude, or
        read back from a cache row written by an older version of this code.
        That last one is not hypothetical: it is how the invariant was found.
        """
        if self.mexicanism and not self.region_note:
            object.__setattr__(self, "region_note", DEFAULT_REGION_NOTE)

    @property
    def has_german(self) -> bool:
        return bool(self.de)

    @property
    def has_english(self) -> bool:
        return bool(self.en)

    @property
    def has_any_gloss(self) -> bool:
        return bool(self.de or self.en)

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

    def text_filled_from(self, other: Gloss) -> Gloss:
        """Take only missing gloss *text* from `other`, never its flags.

        Used when merging two Wiktionary records for the same word. A region
        label describes the sense it sits on, so carrying it across records
        attaches it to a meaning it was never about: `coche` has a peninsular
        sense and a Mexican one, and OR-ing them produced a card labelled both
        "Mexiko, Spanien"; `mano` picked up "Mexiko, Slang" from the *bro* sense
        while being glossed as *hand*.

        Text is different. A German entry filling in German for an English
        entry's word is exactly the merge this pass exists to do.
        """
        return Gloss(
            lemma=self.lemma,
            pos=self.pos,
            de=self.de or other.de,
            en=self.en or other.en,
            de_source=self.de_source if self.de else other.de_source,
            en_source=self.en_source if self.en else other.en_source,
            mexicanism=self.mexicanism,
            region_note=self.region_note,
            not_spanish=self.not_spanish,
            corrected_lemma=self.corrected_lemma,
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


@dataclass(frozen=True)
class NormalizedGloss:
    """Card text, plus how much violence was needed to get it there.

    The two flags separate the two ways dictionary text overruns a card, because
    they deserve opposite treatment:

    `trimmed` — there were more alternatives than a card holds, but each was
    short. "burrow, den, sett, warren" becomes "burrow, den, sett" and loses
    nothing that matters. Perfectly good card text.

    `clipped` — every alternative was a phrase, so a prefix of the first was
    kept. "unterirdischer Unterschlupf eines Tieres" becomes "unterirdischer
    Unterschlupf eines", which is not a translation but the wreckage of a
    definition. Usable only as a last resort.
    """

    text: str | None
    trimmed: bool = False
    clipped: bool = False

    @property
    def is_translation(self) -> bool:
        """Whether this reads as a gloss rather than as a mangled definition."""
        return bool(self.text) and not self.clipped

    @property
    def was_shortened(self) -> bool:
        return self.trimmed or self.clipped


def normalize_gloss(text: str | None) -> NormalizedGloss:
    """Reduce dictionary prose to card text.

    Both halves of the one-to-three-words rule are enforced: at most three
    alternatives, and at most three words in each. Capping only the count would
    let "Bau, Höhle, unterirdischer Unterschlupf eines Tieres" through intact,
    which is a definition wearing a gloss's punctuation.
    """
    if not text:
        return NormalizedGloss(None)

    seen: list[str] = []
    for raw in _SEPARATORS.split(_ASIDE.sub(" ", text)):
        unit = _clean_unit(raw)
        if unit and unit not in seen:
            seen.append(unit)

    short = [unit for unit in seen if len(unit.split()) <= MAX_WORDS_PER_UNIT]
    if short:
        return NormalizedGloss(
            ", ".join(short[:MAX_UNITS]),
            trimmed=len(short) > MAX_UNITS or len(short) != len(seen),
        )

    # Every alternative is a phrase. Keep a bounded prefix of the first rather
    # than nothing — a caller with no further fallback would rather have this —
    # but say so, because a caller that can ask Claude instead should.
    if seen:
        clipped = " ".join(seen[0].split()[:MAX_WORDS_PER_UNIT])
        return NormalizedGloss(clipped or None, clipped=bool(clipped))
    return NormalizedGloss(None)


def gloss_text(text: str | None) -> str | None:
    """`normalize_gloss` when only the text matters."""
    return normalize_gloss(text).text
