"""Assembling a bundle from an EPUB.

Wires the other modules together and emits the §4 JSON. Nothing here decides
anything the spec settles elsewhere; the rules live in `classify`, the keys in
`lexicon`, the contract in `schema`.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from molcajete_prep.classify import (
    ChapterVocabulary,
    Classification,
    ClassificationOptions,
    ClassificationResult,
    LemmaKey,
    assign_to_chapters,
    classify_all,
)
from molcajete_prep.epub import ChapterSource, book_metadata, extract_chapters
from molcajete_prep.lexicon import Lexicon, build_lexicon, example_sentence
from molcajete_prep.nlp import Token, load_pipeline, tokenize_paragraphs
from molcajete_prep.schema import SCHEMA_VERSION, validate_bundle

LANGUAGE = "es"
VARIANT = "es-MX"

# Zipf scores carry two decimals in wordfreq's own reporting; keeping more would
# only make the file bigger and the diffs noisier.
_ZIPF_PRECISION = 2


@dataclass(frozen=True)
class BuildResult:
    """The bundle, plus everything the report needs that the bundle drops."""

    bundle: dict[str, Any]
    lexicon: Lexicon
    classifications: dict[LemmaKey, ClassificationResult]
    chapter_vocabulary: list[ChapterVocabulary]
    options: ClassificationOptions
    known_lemmas: frozenset[str] = field(default=frozenset())

    @property
    def book_id(self) -> str:
        return self.bundle["book"]["id"]


def slugify(text: str) -> str:
    """ASCII slug. 'Los de abajo' -> 'los-de-abajo'."""
    stripped = unicodedata.normalize("NFKD", text)
    ascii_text = stripped.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_text)).strip("-")


def make_book_id(author: str, title: str) -> str:
    """Surname plus title, as in SPEC §4's 'villalobos-fiesta-madriguera'."""
    surname = author.split()[-1] if author.split() else ""
    parts = [slugify(surname), slugify(title)]
    return "-".join(part for part in parts if part) or "libro"


def _token_json(token: Token, lexicon: Lexicon) -> dict[str, Any]:
    if token.is_whitespace:
        return {"s": token.surface, "ws": True}

    entry: dict[str, Any] = {"s": token.surface, "p": lexicon.effective_pos(token)}
    if not token.is_word or token.lemma is None:
        # Punctuation, symbols and numerals. 'l' would only repeat 's'.
        return entry

    entry["l"] = token.lemma
    key = lexicon.key_for(token)
    if key is not None:
        entry["t"] = key
    return entry


def _lexicon_json(
    lexicon: Lexicon,
    classifications: dict[LemmaKey, ClassificationResult],
    chapters: list[list[list[Token]]],
) -> dict[str, Any]:
    """Serialize the lexicon.

    Phase 1 fills only what it can compute. `de`, `en` and `regionNote` arrive in
    Phase 2 — filling a field is not a shape change, so `schemaVersion` stays 1.
    `mexicanism` is written explicitly as false rather than omitted, so that its
    absence can never be mistaken for "not yet determined".

    Example sentences are attached to teach-set lemmas only: a card is the only
    thing that displays one, and emitting them for every lemma would inflate the
    file for nothing.
    """
    out: dict[str, Any] = {}
    for key in sorted(lexicon.records):
        record = lexicon.records[key]
        entry: dict[str, Any] = {
            "lemma": record.lemma,
            "pos": record.pos,
            "zipf": round(record.zipf, _ZIPF_PRECISION),
            "bookCount": record.book_count,
            "firstChapter": record.first_chapter,
            "mexicanism": False,
        }

        if classifications[key].is_teach:
            example = example_sentence(record, chapters)
            if example is not None:
                text, chapter_index = example
                entry["example"] = {"es": text, "chapterIndex": chapter_index}

        out[key] = entry
    return out


def build_bundle(
    epub_path: str | Path,
    *,
    book_id: str | None = None,
    title: str | None = None,
    author: str | None = None,
    known_lemmas: frozenset[str] = frozenset(),
    options: ClassificationOptions = ClassificationOptions(),
    split_on_heading: bool = False,
    keep_boilerplate: bool = False,
) -> BuildResult:
    """Read an EPUB and produce a validated `schemaVersion: 1` bundle."""
    epub_path = Path(epub_path)
    metadata = book_metadata(str(epub_path))
    sources: list[ChapterSource] = extract_chapters(
        str(epub_path),
        split_on_heading=split_on_heading,
        keep_boilerplate=keep_boilerplate,
    )
    if not sources:
        raise ValueError(f"{epub_path} yielded no chapters with prose in them")

    nlp = load_pipeline()
    chapters: list[list[list[Token]]] = [
        tokenize_paragraphs(nlp, list(source.paragraphs)) for source in sources
    ]

    lexicon = build_lexicon(chapters)
    entries = lexicon.entries_for_classification()
    classifications = classify_all(entries, known_lemmas, options)
    vocabulary = assign_to_chapters(entries, lexicon.chapter_keys, known_lemmas, options)

    resolved_title = title or metadata["title"] or epub_path.stem
    resolved_author = author or metadata["author"] or "Desconocido"

    chapters_json = []
    total_tokens = 0
    for index, (source, paragraphs, chapter_vocabulary) in enumerate(
        zip(sources, chapters, vocabulary, strict=True)
    ):
        token_count = sum(
            1 for tokens in paragraphs for token in tokens if token.is_word
        )
        total_tokens += token_count
        chapters_json.append(
            {
                "index": index,
                "title": source.title,
                "tokenCount": token_count,
                "paragraphs": [
                    {
                        "id": f"c{index}p{paragraph_index}",
                        "tokens": [_token_json(token, lexicon) for token in tokens],
                    }
                    for paragraph_index, tokens in enumerate(paragraphs)
                ],
                "teachSet": list(chapter_vocabulary.teach),
                "glossOnly": list(chapter_vocabulary.gloss_only),
            }
        )

    lexicon_json = _lexicon_json(lexicon, classifications, chapters)

    bundle = {
        "schemaVersion": SCHEMA_VERSION,
        "book": {
            "id": book_id or make_book_id(resolved_author, resolved_title),
            "title": resolved_title,
            "author": resolved_author,
            "language": LANGUAGE,
            "variant": VARIANT,
            "totalTokens": total_tokens,
            "uniqueLemmas": len(lexicon_json),
        },
        "chapters": chapters_json,
        "lexicon": lexicon_json,
    }

    validate_bundle(bundle)

    return BuildResult(
        bundle=bundle,
        lexicon=lexicon,
        classifications=classifications,
        chapter_vocabulary=vocabulary,
        options=options,
        known_lemmas=known_lemmas,
    )


def write_bundle(bundle: dict[str, Any], path: str | Path, *, pretty: bool = False) -> Path:
    """Write the bundle as UTF-8 JSON.

    Keys are sorted and separators are tight: rebuilding the same EPUB must
    produce a byte-identical file, and the token array dominates the file size.
    `--pretty` exists for reading a bundle by eye, not for shipping one.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        bundle,
        ensure_ascii=False,
        sort_keys=True,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    )
    path.write_text(text, encoding="utf-8")
    return path


def count_classifications(
    classifications: dict[LemmaKey, ClassificationResult],
) -> dict[Classification, int]:
    counts = {classification: 0 for classification in Classification}
    for result in classifications.values():
        counts[result.classification] += 1
    return counts
