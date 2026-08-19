"""Anki export to `known.json` — the SPEC §8 seed.

Without this, chapter one of a real book asks for 263 cards across 15 sessions
and the app feels stupid teaching you *tener* and *más*. The seed is what makes
the teaching loop honest about what you already have.

Pure apart from spaCy: this module takes text in and gives lemma strings back.
The filesystem and argparse live in `cli_seed`.

## The format

`File → Export → Notes in Plain Text (.txt)` writes tab-separated notes, one per
line, with `#`-prefixed header lines in current Anki versions. There is no
schema — the columns are whatever the note type has — so which column holds the
Spanish is a question this module answers by looking rather than by assuming.

## Why the answer is lemma strings and nothing else

`classify.classify_all` tests `entry.lemma in known_lemmas`, and
`cli.load_known_lemmas` reads a flat array. Both existed before this module did.
The app agrees: `LemmaId` in `app/src/domain/lemma.ts` is the bare lemma string
for the same reason. Emitting anything richer would mean three consumers to
change.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from wordfreq import zipf_frequency

from molcajete_prep.nlp import Token, load_pipeline, tokenize

LANGUAGE = "es"

# The native languages of this project (CLAUDE.md): German primary, English
# secondary. A column is Spanish if its words are more Spanish than they are
# either of those — see `score_fields`.
NATIVE_LANGUAGES = ("de", "en")

# Single characters are noise. `a` is a Spanish word and also the whole of a
# deck tag like "A1", and counting it lets a tag column outscore the vocabulary.
MIN_WORD_LENGTH = 2

# Anki fields are HTML. Cloze markup, sound tags and the rest are not words.
_TAG_RE = re.compile(r"<[^>]+>")
_CLOZE_RE = re.compile(r"\{\{c\d+::(.*?)(?:::.*?)?\}\}", re.S)
_SOUND_RE = re.compile(r"\[sound:[^\]]*\]")

# A field often holds several ways of saying the same thing.
_SPLIT_RE = re.compile(r"[;,/|]|\s+·\s+|\s+—\s+")

# Anki's own escape for a tab inside a field.
_ESCAPED_TAB = "\\t"


def clean_field(raw: str) -> str:
    """One Anki field as plain text.

    Cloze deletions keep their answer — `{{c1::perro::animal}}` is `perro` —
    because that is the word the note is about.
    """
    text = _CLOZE_RE.sub(r"\1", raw)
    text = _SOUND_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = text.replace(_ESCAPED_TAB, " ").replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip()


def read_rows(text: str) -> list[list[str]]:
    """Split an export into rows of fields, dropping Anki's `#` headers."""
    rows = []
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        rows.append([clean_field(field) for field in line.split("\t")])
    return rows


@dataclass(frozen=True)
class FieldScore:
    index: int
    spanish_words: int
    sampled: int
    sample: tuple[str, ...]

    @property
    def ratio(self) -> float:
        return self.spanish_words / self.sampled if self.sampled else 0.0


def score_fields(rows: Sequence[Sequence[str]], sample_size: int = 300) -> list[FieldScore]:
    """How Spanish each column looks, so the right one can be chosen by looking.

    The column holding the Spanish depends on the note type, and getting it
    wrong silently seeds the app with German — which is worse than no seed at
    all, because a lemma marked known is never taught *and* counts as covered.
    The app would quietly skip words you actually need.

    So the test is comparative, not absolute. "Has Spanish ever seen this word"
    says yes to most German too — *Hund* scores 1.67 in Spanish. What separates
    the columns is whether a word is **more** Spanish than it is German or
    English:

        perro    es 4.90  de 1.96   ->  Spanish
        laufen   es 0.00  de 5.05   ->  not
        sierra   es 4.48  de 3.74   ->  Spanish

    Single characters are excluded, or a column of deck tags like `A1` scores
    100% on the `a` and wins.
    """
    width = max((len(row) for row in rows), default=0)
    scores = []

    for index in range(width):
        values = [row[index] for row in rows[:sample_size] if index < len(row) and row[index]]
        spanish = 0
        counted = 0
        for value in values:
            for word in re.findall(r"[^\W\d_]+", value, re.UNICODE):
                if len(word) < MIN_WORD_LENGTH:
                    continue
                counted += 1
                lowered = word.lower()
                native = max(
                    zipf_frequency(lowered, language) for language in NATIVE_LANGUAGES
                )
                if zipf_frequency(lowered, LANGUAGE) > native:
                    spanish += 1
        scores.append(
            FieldScore(
                index=index,
                spanish_words=spanish,
                sampled=counted,
                sample=tuple(values[:3]),
            )
        )

    return scores


def choose_field(scores: Sequence[FieldScore]) -> int:
    """The most Spanish-looking column.

    Ties break on the lower index, which is the front of an Anki card and the
    conventional place for the target language.
    """
    if not scores:
        raise ValueError("the export has no columns")
    best = max(scores, key=lambda score: (score.ratio, -score.index))
    if best.sampled == 0:
        raise ValueError("no column in the export contained any words")
    return best.index


def lemmas_from_values(values: Iterable[str], nlp=None) -> set[str]:
    """Lemmatize field values into the lemma strings §8 asks for.

    Proper nouns are dropped: §5 never teaches one, so seeding it would be
    recording a fact nothing reads. Everything else that `Token.is_word` accepts
    is kept, lowercased — including apocopated forms like `pa'` and `nomás`,
    which is exactly the vocabulary a Mexican deck is worth having.
    """
    nlp = nlp or load_pipeline()
    lemmas: set[str] = set()

    for value in values:
        for part in _SPLIT_RE.split(value):
            part = part.strip()
            if not part:
                continue
            tokens: list[Token] = tokenize(nlp, part)
            for token in tokens:
                if not token.is_word or token.is_proper_noun or not token.lemma:
                    continue
                lemmas.add(token.lemma.lower())

    return lemmas


def seed_from_text(text: str, *, field: int | None = None, nlp=None) -> tuple[set[str], int, list[FieldScore]]:
    """The whole pass: export text in, lemmas out, plus what it decided and why."""
    rows = read_rows(text)
    if not rows:
        raise ValueError("the export contained no notes")

    scores = score_fields(rows)
    chosen = field if field is not None else choose_field(scores)
    if chosen < 0 or chosen >= len(scores):
        raise ValueError(f"--field {chosen} but the export has {len(scores)} columns")

    values = [row[chosen] for row in rows if chosen < len(row) and row[chosen]]
    return lemmas_from_values(values, nlp=nlp), chosen, scores


def merge(existing: Iterable[str], new: Iterable[str]) -> list[str]:
    """§8: re-runnable at any time, merging rather than replacing."""
    return sorted({*(lemma.lower() for lemma in existing), *(lemma.lower() for lemma in new)})


def dumps(lemmas: Iterable[str]) -> str:
    """A flat array of lemma strings, sorted so a re-run diffs cleanly."""
    return json.dumps(sorted(set(lemmas)), ensure_ascii=False, indent=0) + "\n"
