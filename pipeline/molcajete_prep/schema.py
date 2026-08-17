"""The bundle format, and a validator for it.

SPEC §4 and CLAUDE.md constraint 6: the bundle is a versioned contract between
two products that will eventually be maintained separately, one of them in
Swift. This module is the written-down half of that contract. Read it as the
specification a decoder has to satisfy, and change it only alongside a
`schemaVersion` bump and a migration path.

Two points where §4's example is not self-consistent, resolved here:

`t` is a **string** lexicon key — `"m0118"`. The example block shows integers
(`"t": 4012`) while its own lexicon is keyed by strings (`"m0031"`), and
Appendix A assigns `"t": key`. The strings win.

**Not every token carries every field.** The example implies all four are always
present. In practice a whitespace token has only `s` and `ws`; punctuation and
numerals have `s` and `p`; a proper noun has `s`, `l` and `p` but no `t`,
because it has no lexicon entry to point at.

Field reference:

| Field | Meaning |
|---|---|
| `s`  | surface form, verbatim — concatenating every `s` in a paragraph reproduces the source text |
| `ws` | true on whitespace-only tokens; no other field but `s` is present |
| `l`  | lemma, lower-cased; absent on punctuation, numerals and whitespace |
| `p`  | part-of-speech tag |
| `t`  | lexicon key; absent when the token has no entry (proper nouns, numerals, punctuation) |

Lexicon entries gained `de`, `en` and `regionNote` in Phase 2. They are
**optional**, present only where the glossing pass found something, and their
arrival did not bump `schemaVersion`: the §4 shape already reserved them, and a
decoder written against Phase 1 ignores fields it does not know. A Phase 1
bundle is still a valid Phase 2 bundle — with no glosses in it.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = 1

_BOOK_FIELDS = (
    "id",
    "title",
    "author",
    "language",
    "variant",
    "totalTokens",
    "uniqueLemmas",
)
_CHAPTER_FIELDS = ("index", "title", "tokenCount", "paragraphs", "teachSet", "glossOnly")
_LEXICON_FIELDS = ("lemma", "pos", "zipf", "bookCount", "firstChapter", "mexicanism")

# Written when the glossing pass produced them, omitted when it did not. An
# absent `de` means "no gloss"; an empty string would mean the same thing while
# rendering as a blank line on a card, so the validator rejects it.
_OPTIONAL_GLOSS_FIELDS = ("de", "en", "regionNote")


class BundleValidationError(ValueError):
    """The bundle does not satisfy the §4 contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BundleValidationError(message)


def _validate_token(token: Any, where: str, lexicon: dict[str, Any]) -> None:
    _require(isinstance(token, dict), f"{where}: token is not an object")
    _require("s" in token and isinstance(token["s"], str), f"{where}: token has no 's'")

    if token.get("ws"):
        _require(
            set(token) <= {"s", "ws"},
            f"{where}: whitespace token carries fields beyond 's' and 'ws'",
        )
        return

    key = token.get("t")
    if key is not None:
        _require(isinstance(key, str), f"{where}: 't' must be a string lexicon key")
        _require(key in lexicon, f"{where}: 't' references unknown lexicon key {key!r}")
        _require("l" in token, f"{where}: token with a 't' must also carry 'l'")


def _validate_chapter(chapter: Any, index: int, lexicon: dict[str, Any]) -> None:
    where = f"chapters[{index}]"
    _require(isinstance(chapter, dict), f"{where}: not an object")
    for field in _CHAPTER_FIELDS:
        _require(field in chapter, f"{where}: missing '{field}'")
    _require(chapter["index"] == index, f"{where}: index is {chapter['index']}, expected {index}")

    seen_ids: set[str] = set()
    for paragraph_index, paragraph in enumerate(chapter["paragraphs"]):
        paragraph_where = f"{where}.paragraphs[{paragraph_index}]"
        _require(isinstance(paragraph, dict), f"{paragraph_where}: not an object")
        _require("id" in paragraph, f"{paragraph_where}: missing 'id'")
        _require(
            paragraph["id"] not in seen_ids,
            f"{paragraph_where}: duplicate paragraph id {paragraph['id']!r}",
        )
        seen_ids.add(paragraph["id"])
        _require("tokens" in paragraph, f"{paragraph_where}: missing 'tokens'")
        for token in paragraph["tokens"]:
            _validate_token(token, paragraph_where, lexicon)

    for field in ("teachSet", "glossOnly"):
        for key in chapter[field]:
            _require(
                key in lexicon,
                f"{where}.{field}: unknown lexicon key {key!r}",
            )


def validate_bundle(bundle: Any) -> None:
    """Raise `BundleValidationError` if `bundle` is not a valid §4 bundle."""
    _require(isinstance(bundle, dict), "bundle is not an object")
    _require("schemaVersion" in bundle, "bundle has no 'schemaVersion'")
    _require(
        bundle["schemaVersion"] == SCHEMA_VERSION,
        f"unsupported schemaVersion {bundle['schemaVersion']!r}, expected {SCHEMA_VERSION}",
    )

    for section in ("book", "chapters", "lexicon"):
        _require(section in bundle, f"bundle has no '{section}'")

    book = bundle["book"]
    for field in _BOOK_FIELDS:
        _require(field in book, f"book: missing '{field}'")

    lexicon = bundle["lexicon"]
    _require(isinstance(lexicon, dict), "lexicon is not an object")
    for key, entry in lexicon.items():
        for field in _LEXICON_FIELDS:
            _require(field in entry, f"lexicon[{key!r}]: missing '{field}'")
        for field in _OPTIONAL_GLOSS_FIELDS:
            if field in entry:
                _require(
                    isinstance(entry[field], str) and entry[field].strip() != "",
                    f"lexicon[{key!r}]: '{field}' is present but empty — omit it instead",
                )
        # A card that claims Mexican usage without saying what kind is a claim
        # the reader cannot act on, so the two travel together.
        if entry["mexicanism"]:
            _require(
                "regionNote" in entry,
                f"lexicon[{key!r}]: mexicanism is true but no 'regionNote' says where or how",
            )

    for index, chapter in enumerate(bundle["chapters"]):
        _validate_chapter(chapter, index, lexicon)

    _require(
        book["uniqueLemmas"] == len(lexicon),
        f"book.uniqueLemmas is {book['uniqueLemmas']}, lexicon holds {len(lexicon)}",
    )
