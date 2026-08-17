"""Turning wiktextract records into glosses.

Two editions, one shape. Both dumps use `lang_code: "es"` for Spanish and put
the text in `senses[].glosses`; only the language of that text differs. The
English edition supplies `en` and the region labels, the German edition supplies
`de`.

Three properties of the data drive everything here:

**`glosses` is a hierarchy, not a string.** `["Unconstrained.", "Not imprisoned
or enslaved."]` is a parent gloss followed by the subsense that actually applies.
The last element is the specific one, so that is what a card gets.

**Form-of senses are traps.** `banco` as a verb glosses to "first-person singular
present indicative of bancar" — grammatically true, useless on a card, and
actively misleading as a translation. Those senses are skipped outright.

**Region labels are structured.** `chido` arrives as `tags: ["Mexico"]` with
`categories: ["Mexican Spanish"]`, not as prose to be pattern-matched. That makes
the `mexicanism` flag reliable where Wiktionary has an opinion at all.

Region and register are read from the *glossed* sense rather than from the whole
entry. `carro` means "cart" everywhere and "car" in Latin America; labelling the
cart card as Latin-American because a later sense is would put a false claim on
the card.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from molcajete_prep.glossing.models import (
    Gloss,
    GlossSource,
    normalize_gloss,
    upos_candidates,
)
from molcajete_prep.glossing.sources import iter_spanish_records

Identity = tuple[str, str]

# A sense that describes a word form rather than a meaning. Its gloss is a
# grammatical statement and never belongs on a card.
_FORM_OF_TAGS = frozenset(
    {"form-of", "alt-of", "misspelling", "obsolete-spelling", "romanization", "participle"}
)

# Usable, but only if nothing better exists in the entry.
_LAST_RESORT_TAGS = frozenset({"obsolete", "archaic", "rare", "dated", "poetic", "historical"})

_MEXICO_TAGS = frozenset({"Mexico"})
_MEXICO_CATEGORIES = frozenset({"Mexican Spanish"})
_LATIN_AMERICA_TAGS = frozenset({"Latin-America", "Latin America"})
_LATIN_AMERICA_CATEGORIES = frozenset({"Latin American Spanish"})
_PENINSULAR_TAGS = frozenset({"Spain"})
_PENINSULAR_CATEGORIES = frozenset({"Peninsular Spanish", "Spain Spanish"})

# CLAUDE.md: every user-facing string in the app is German. SPEC §4's example
# shows `"regionNote": "MX, coloquial"`, but CLAUDE.md wins where the two
# conflict, and this note renders on the card next to a German gloss.
_REGION_DE = {
    "Mexico": "Mexiko",
    "Latin-America": "Lateinamerika",
    "Latin America": "Lateinamerika",
    "Spain": "Spanien",
}

_REGISTER_DE = {
    "colloquial": "umgangssprachlich",
    "informal": "umgangssprachlich",
    "slang": "Slang",
    "vulgar": "vulgär",
    "derogatory": "abwertend",
    "offensive": "beleidigend",
    "humorous": "scherzhaft",
    "figuratively": "übertragen",
    "dated": "veraltend",
    "archaic": "veraltet",
    "obsolete": "veraltet",
    "poetic": "dichterisch",
    "literary": "literarisch",
    "rare": "selten",
}

# A regionNote is a chip on a card, not a label set.
_MAX_NOTE_PARTS = 3


def _category_names(sense: dict) -> list[str]:
    """Category entries are bare strings in current dumps and dicts in older ones."""
    names = []
    for category in sense.get("categories") or ():
        if isinstance(category, dict):
            name = category.get("name")
        else:
            name = category
        if isinstance(name, str):
            names.append(name)
    return names


def _sense_tags(sense: dict) -> set[str]:
    tags = set(sense.get("tags") or ())
    tags.update(sense.get("raw_tags") or ())
    return tags


def _sense_text(sense: dict) -> str | None:
    """The most specific gloss in the sense's hierarchy."""
    glosses = sense.get("glosses") or ()
    return glosses[-1] if glosses else None


def _is_form_of(sense: dict) -> bool:
    return bool(sense.get("form_of") or sense.get("alt_of")) or bool(
        _sense_tags(sense) & _FORM_OF_TAGS
    )


def usable_senses(record: dict) -> list[dict]:
    """The record's senses worth glossing, best first.

    Form-of senses are dropped entirely. Obsolete and archaic ones sort last
    rather than being dropped: a word can be in the book precisely because it is
    archaic, and a dated gloss beats no gloss.
    """
    preferred: list[dict] = []
    last_resort: list[dict] = []

    for sense in record.get("senses") or ():
        if not isinstance(sense, dict) or _is_form_of(sense) or not _sense_text(sense):
            continue
        if _sense_tags(sense) & _LAST_RESORT_TAGS:
            last_resort.append(sense)
        else:
            preferred.append(sense)

    return preferred + last_resort


def _entry_is_peninsular_anywhere(record: dict) -> bool:
    for sense in record.get("senses") or ():
        if not isinstance(sense, dict):
            continue
        if _sense_tags(sense) & _PENINSULAR_TAGS:
            return True
        if set(_category_names(sense)) & _PENINSULAR_CATEGORIES:
            return True
    return False


def sense_is_mexican(sense: dict, *, entry_is_peninsular_anywhere: bool) -> bool:
    """Whether this sense is Mexican vocabulary in the sense SPEC §5 means.

    An explicit Mexico label is taken at face value. A Latin-American label only
    counts when the same entry also carries a peninsular-specific sense — that
    is the "where the peninsular sense differs" case, and it is the difference
    that makes the word worth a card rather than the region alone. Anything
    broader would flag half the book: a Latin-American label is the norm for a
    Mexican novel, and `mexicanism && bookCount >= 2` teaches whatever it marks.

    Everything this misses is left to the Claude pass, which sees the sentence.
    """
    tags = _sense_tags(sense)
    categories = set(_category_names(sense))

    if tags & _MEXICO_TAGS or categories & _MEXICO_CATEGORIES:
        return True
    if tags & _LATIN_AMERICA_TAGS or categories & _LATIN_AMERICA_CATEGORIES:
        return entry_is_peninsular_anywhere
    return False


def region_note(sense: dict) -> str | None:
    """A German chip describing where and how the word is used.

    Set independently of `mexicanism`: `carro` for "car" is worth marking
    *Lateinamerika* on the card even though it does not earn a card of its own
    under the §5 rules.
    """
    tags = _sense_tags(sense)
    parts: list[str] = []

    for tag in sorted(tags):
        german = _REGION_DE.get(tag)
        if german and german not in parts:
            parts.append(german)
    for tag in sorted(tags):
        german = _REGISTER_DE.get(tag)
        if german and german not in parts:
            parts.append(german)

    return ", ".join(parts[:_MAX_NOTE_PARTS]) or None


@dataclass(frozen=True)
class WiktionaryHit:
    """What one Wiktionary record yields for one lemma.

    `gloss` carries the gloss *only when normalizing produced a translation
    rather than the wreckage of a definition*. Both editions write definitions as
    readily as translations — English Wiktionary opens `dictionary` with a
    forty-word sentence — and a definition cut to three words is worse than
    either the definition or no gloss at all: "Not imprisoned or" teaches nothing
    and looks deliberate.

    Trimming a surplus of short alternatives is a different matter and is fine:
    "burrow, den, sett, warren" becomes "burrow, den, sett" and stays a gloss.

    Anything that had to be clipped is left out of `gloss` and kept in `raw_de` /
    `raw_en`, where it becomes context for the Claude pass rather than card text.
    `raw_*` is always populated, accepted or not, so the model can see what
    Wiktionary thought even where we took its answer.
    """

    lemma: str
    gloss: Gloss
    raw_de: str | None = None
    raw_en: str | None = None
    region_hint: str | None = None

    @property
    def is_complete(self) -> bool:
        return self.gloss.has_german and self.gloss.has_english


def gloss_from_record(record: dict, *, source: GlossSource) -> WiktionaryHit | None:
    """Build one hit from one wiktextract record, or None if nothing is usable."""
    lemma = (record.get("word") or "").strip().lower()
    if not lemma:
        return None

    senses = usable_senses(record)
    if not senses:
        return None

    chosen = senses[0]
    raw = _sense_text(chosen)
    normalized = normalize_gloss(raw)
    if not normalized.text:
        return None

    # The gate the whole design turns on: keep Wiktionary's words when they
    # survive as a translation, hand them to Claude when they only survive as a
    # clipped definition.
    usable = normalized.text if normalized.is_translation else None

    peninsular = _entry_is_peninsular_anywhere(record)
    is_german = source is GlossSource.DE_WIKTIONARY
    tags = sorted(_sense_tags(chosen))

    return WiktionaryHit(
        lemma=lemma,
        gloss=Gloss(
            lemma=lemma,
            pos="",  # filled in per candidate tag by the caller
            de=usable if is_german else None,
            en=None if is_german else usable,
            de_source=source if is_german and usable else None,
            en_source=None if is_german or not usable else source,
            mexicanism=sense_is_mexican(chosen, entry_is_peninsular_anywhere=peninsular),
            region_note=region_note(chosen),
        ),
        raw_de=raw if is_german else None,
        raw_en=None if is_german else raw,
        region_hint=", ".join(tags) or None,
    )


def index_records(
    records: Iterable[dict],
    *,
    source: GlossSource,
    wanted_lemmas: set[str] | None = None,
) -> dict[Identity, WiktionaryHit]:
    """Collapse a stream of records into `{(lemma, spaCy tag): WiktionaryHit}`.

    `wanted_lemmas` bounds memory: the English edition holds three quarters of a
    million Spanish entries and a book needs nine thousand of them, so anything
    the lexicon did not ask for is dropped as it goes past.

    Wiktionary splits a word across several records when it has several
    etymologies. The first record to supply a gloss for an identity wins, and
    later ones can still contribute a region flag they alone carry.
    """
    index: dict[Identity, WiktionaryHit] = {}

    for record in records:
        pos_candidates = upos_candidates(record.get("pos") or "")
        if not pos_candidates:
            continue
        if wanted_lemmas is not None:
            lemma = (record.get("word") or "").strip().lower()
            if lemma not in wanted_lemmas:
                continue

        hit = gloss_from_record(record, source=source)
        if hit is None:
            continue

        for pos in pos_candidates:
            identity = (hit.lemma, pos)
            tagged = Gloss(
                lemma=hit.lemma,
                pos=pos,
                de=hit.gloss.de,
                en=hit.gloss.en,
                de_source=hit.gloss.de_source,
                en_source=hit.gloss.en_source,
                mexicanism=hit.gloss.mexicanism,
                region_note=hit.gloss.region_note,
            )
            existing = index.get(identity)
            if existing is None:
                index[identity] = WiktionaryHit(
                    lemma=hit.lemma,
                    gloss=tagged,
                    raw_de=hit.raw_de,
                    raw_en=hit.raw_en,
                    region_hint=hit.region_hint,
                )
                continue

            index[identity] = WiktionaryHit(
                lemma=hit.lemma,
                gloss=existing.gloss.merged_with(tagged),
                raw_de=existing.raw_de or hit.raw_de,
                raw_en=existing.raw_en or hit.raw_en,
                region_hint=existing.region_hint or hit.region_hint,
            )

    return index


def read_extract(
    path: Path,
    *,
    source: GlossSource,
    wanted_lemmas: set[str] | None = None,
) -> dict[Identity, WiktionaryHit]:
    """Stream one downloaded extract straight into an index."""
    return index_records(
        iter_spanish_records(path), source=source, wanted_lemmas=wanted_lemmas
    )


def iter_records_from_lines(lines: Iterable[str]) -> Iterator[dict]:
    """Parse already-decompressed JSONL. Used by the tests and by nothing else."""
    import json

    for line in lines:
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        if record.get("lang_code") == "es":
            yield record
