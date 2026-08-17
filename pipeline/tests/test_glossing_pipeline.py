"""Tests for the orchestration, and for glossing's effect on the bundle.

The point of interest is ordering: `mexicanism` is one of the three SPEC §5
teach rules, so glossing has to finish before classification starts. These tests
pin that, because getting it backwards produces a bundle that looks perfectly
valid and quietly never teaches a mexicanism.
"""

from __future__ import annotations

import gzip
import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from molcajete_prep.bundle import build_bundle
from molcajete_prep.classify import Classification
from molcajete_prep.glossing.cache import GlossCache
from molcajete_prep.glossing.models import Gloss, GlossSource
from molcajete_prep.glossing.pipeline import (
    CONTEXT_ONLY,
    VERBATIM,
    GlossingOptions,
    gloss_lexicon,
)
from molcajete_prep.glossing.sources import DE_WIKTIONARY, EN_WIKTIONARY
from molcajete_prep.lexicon import build_lexicon
from molcajete_prep.nlp import Token

NOW = datetime(2026, 8, 17, 9, 0, 0)


def word(lemma, pos="NOUN", surface=None, sentence=0):
    return Token(
        surface=surface or lemma,
        lemma=lemma,
        pos=pos,
        is_whitespace=False,
        sentence=sentence,
    )


def entry(word_, pos, gloss, *, tags=None, categories=None, lang="Spanish"):
    sense = {"glosses": [gloss]}
    if tags:
        sense["tags"] = tags
    if categories:
        sense["categories"] = categories
    return {
        "word": word_,
        "pos": pos,
        "lang": lang,
        "lang_code": "es",
        "senses": [sense],
    }


@pytest.fixture
def extracts(tmp_path):
    """Two tiny stand-ins for the real dumps, in the same on-disk format."""
    directory = tmp_path / "kaikki"
    directory.mkdir()

    english = [
        entry("chido", "adj", "cool, awesome", tags=["Mexico"], categories=["Mexican Spanish"]),
        entry("libro", "noun", "book"),
        entry("caballo", "noun", "horse"),
        entry(
            "madriguera",
            "noun",
            "A hole in the ground dug by an animal for shelter",
        ),
    ]
    german = [
        entry("libro", "noun", "das Buch", lang="Spanisch"),
        entry("caballo", "noun", "ein Huftier mit vier Beinen und Hufen", lang="Spanisch"),
    ]

    for source, rows in ((EN_WIKTIONARY, english), (DE_WIKTIONARY, german)):
        with gzip.open(source.path(directory), "wt", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")

    return directory


def fake_client(answers: dict[tuple[str, str], dict]):
    """A stand-in for the SDK that answers whatever it is asked, from `answers`."""
    seen: list[dict] = []

    def create(requests):
        seen.extend(requests)
        return SimpleNamespace(id="batch_test", processing_status="ended")

    def results(_batch_id):
        out = []
        for request in seen:
            content = request["params"]["messages"][0]["content"]
            glosses = []
            for (lemma, pos), answer in answers.items():
                if f"{lemma} · {pos}" in content:
                    glosses.append({"lemma": lemma, "pos": pos, **answer})
            out.append(
                SimpleNamespace(
                    custom_id=request["custom_id"],
                    result=SimpleNamespace(
                        type="succeeded",
                        message=SimpleNamespace(
                            content=[
                                SimpleNamespace(
                                    type="text", text=json.dumps({"glosses": glosses})
                                )
                            ],
                            usage=SimpleNamespace(
                                input_tokens=100,
                                output_tokens=80,
                                cache_creation_input_tokens=0,
                                cache_read_input_tokens=1500,
                            ),
                        ),
                    ),
                )
            )
        return out

    return SimpleNamespace(
        messages=SimpleNamespace(
            batches=SimpleNamespace(
                create=lambda requests: create(requests),
                retrieve=lambda _id: SimpleNamespace(
                    id="batch_test", processing_status="ended"
                ),
                results=results,
            )
        ),
        _requests=seen,
    )


def answer(de=None, en=None, mexicanism=False, region_note=None, **extra):
    built = {
        "de": de,
        "en": en,
        "mexicanism": mexicanism,
        "region_note": region_note,
        "not_spanish": False,
        "corrected_lemma": None,
    }
    built.update(extra)
    return built


@pytest.fixture
def cache():
    with GlossCache.in_memory() as store:
        yield store


class TestSourcePriority:
    def test_english_comes_from_english_wiktionary(self, extracts, cache):
        lexicon = build_lexicon([[[word("libro")]]])

        result = gloss_lexicon(
            lexicon,
            [[[word("libro")]]],
            book_id="test",
            options=GlossingOptions(use_claude=False, extract_dir=extracts),
            cache=cache,
            now=NOW,
        )

        gloss = next(iter(result.glosses.values()))
        assert gloss.en == "book"
        assert gloss.en_source is GlossSource.EN_WIKTIONARY

    def test_german_comes_from_german_wiktionary_when_it_fits_a_card(
        self, extracts, cache
    ):
        lexicon = build_lexicon([[[word("libro")]]])

        result = gloss_lexicon(
            lexicon,
            [[[word("libro")]]],
            book_id="test",
            options=GlossingOptions(use_claude=False, extract_dir=extracts),
            cache=cache,
            now=NOW,
        )

        gloss = next(iter(result.glosses.values()))
        assert gloss.de == "das Buch"
        assert gloss.de_source is GlossSource.DE_WIKTIONARY

    def test_a_definitional_german_entry_leaves_the_gloss_for_claude(
        self, extracts, cache
    ):
        """`caballo` is glossed "ein Huftier mit vier Beinen und Hufen" in German
        Wiktionary — a definition, and too long for a card."""
        tokens = [[[word("caballo")]]]
        lexicon = build_lexicon(tokens)
        client = fake_client({("caballo", "NOUN"): answer(de="das Pferd", en="horse")})

        result = gloss_lexicon(
            lexicon,
            tokens,
            book_id="test",
            options=GlossingOptions(extract_dir=extracts),
            cache=cache,
            now=NOW,
            client=client,
        )

        gloss = next(iter(result.glosses.values()))
        assert gloss.de == "das Pferd"
        assert gloss.de_source is GlossSource.CLAUDE

    def test_context_only_mode_hands_every_german_gloss_to_claude(self, extracts, cache):
        """The escape hatch for short definitions: German Wiktionary glosses
        `lunes` as "der erste Wochentag", which fits a card and reads like a
        riddle. Sizing alone cannot catch that; this flag sidesteps it."""
        tokens = [[[word("libro")]]]
        lexicon = build_lexicon(tokens)
        client = fake_client({("libro", "NOUN"): answer(de="das Buch", en="book")})

        result = gloss_lexicon(
            lexicon,
            tokens,
            book_id="test",
            options=GlossingOptions(extract_dir=extracts, de_wiktionary=CONTEXT_ONLY),
            cache=cache,
            now=NOW,
            client=client,
        )

        gloss = next(iter(result.glosses.values()))
        assert gloss.de_source is GlossSource.CLAUDE

    def test_wiktionary_text_travels_to_claude_as_context(self, extracts, cache):
        tokens = [[[word("madriguera")]]]
        lexicon = build_lexicon(tokens)
        client = fake_client({("madriguera", "NOUN"): answer(de="der Bau", en="burrow")})

        gloss_lexicon(
            lexicon,
            tokens,
            book_id="test",
            options=GlossingOptions(extract_dir=extracts),
            cache=cache,
            now=NOW,
            client=client,
        )

        prompt = client._requests[0]["params"]["messages"][0]["content"]
        assert "A hole in the ground" in prompt

    def test_the_example_sentence_travels_to_claude(self, extracts, cache):
        """It is what settles which sense of the word a card teaches."""
        sentence = [word("el", "DET"), word("caballo"), word("corre", "VERB")]
        tokens = [[sentence]]
        lexicon = build_lexicon(tokens)
        client = fake_client({("caballo", "NOUN"): answer(de="das Pferd")})

        gloss_lexicon(
            lexicon,
            tokens,
            book_id="test",
            options=GlossingOptions(extract_dir=extracts),
            cache=cache,
            now=NOW,
            client=client,
        )

        prompt = client._requests[0]["params"]["messages"][0]["content"]
        assert "elcaballocorre" in prompt.replace(" ", "")


class TestCaching:
    def test_a_cached_gloss_skips_every_later_source(self, extracts, cache):
        tokens = [[[word("libro")]]]
        cache.put(
            Gloss(
                lemma="libro",
                pos="NOUN",
                de="von früher",
                en="from before",
                de_source=GlossSource.CLAUDE,
                en_source=GlossSource.CLAUDE,
            ),
            now=NOW,
        )

        result = gloss_lexicon(
            build_lexicon(tokens),
            tokens,
            book_id="test",
            options=GlossingOptions(use_claude=False, extract_dir=extracts),
            cache=cache,
            now=NOW,
        )

        assert result.cache_hits == 1
        assert next(iter(result.glosses.values())).de == "von früher"

    def test_the_second_book_pays_nothing_for_a_shared_lemma(self, extracts, cache):
        """The whole reason the cache exists."""
        tokens = [[[word("caballo")]]]
        client = fake_client({("caballo", "NOUN"): answer(de="das Pferd", en="horse")})
        options = GlossingOptions(extract_dir=extracts)

        first = gloss_lexicon(
            build_lexicon(tokens), tokens, book_id="a", options=options,
            cache=cache, now=NOW, client=client,
        )
        second = gloss_lexicon(
            build_lexicon(tokens), tokens, book_id="b", options=options,
            cache=cache, now=NOW, client=client,
        )

        assert first.sent_to_claude == 1
        assert second.sent_to_claude == 0
        assert second.cache_hits == 1

    def test_regloss_fetches_again(self, extracts, cache):
        tokens = [[[word("caballo")]]]
        cache.put(Gloss(lemma="caballo", pos="NOUN", de="alt", en="old"), now=NOW)
        client = fake_client({("caballo", "NOUN"): answer(de="das Pferd", en="horse")})

        result = gloss_lexicon(
            build_lexicon(tokens),
            tokens,
            book_id="test",
            options=GlossingOptions(extract_dir=extracts, regloss=True),
            cache=cache,
            now=NOW,
            client=client,
        )

        assert result.cache_hits == 0
        assert next(iter(result.glosses.values())).de == "das Pferd"

    def test_a_wiktionary_only_gloss_is_cached_too(self, extracts, cache):
        """So the next book skips the 22.9 GB stream for that lemma."""
        tokens = [[[word("libro")]]]

        gloss_lexicon(
            build_lexicon(tokens),
            tokens,
            book_id="test",
            options=GlossingOptions(use_claude=False, extract_dir=extracts),
            cache=cache,
            now=NOW,
        )

        assert cache.get("libro", "NOUN") is not None

    def test_the_disambiguating_sentence_is_stored_with_a_claude_gloss(
        self, extracts, cache
    ):
        tokens = [[[word("el", "DET"), word("caballo")]]]
        client = fake_client({("caballo", "NOUN"): answer(de="das Pferd", en="horse")})

        gloss_lexicon(
            build_lexicon(tokens),
            tokens,
            book_id="las-noches",
            options=GlossingOptions(extract_dir=extracts),
            cache=cache,
            now=NOW,
            client=client,
        )

        row = cache._connection.execute(
            "SELECT * FROM glosses WHERE lemma = 'caballo'"
        ).fetchone()
        assert row["book_id"] == "las-noches"
        assert row["model"] == "claude-sonnet-5"
        assert "caballo" in row["example_es"]


class TestLimits:
    def test_a_limit_spends_on_the_most_used_words_first(self, extracts, cache):
        """A --gloss-limit is a cost guard, so it should buy the cards that get
        seen most, not the alphabetically luckiest."""
        rare = [word("madriguera")]
        common = [word("caballo")] * 5
        tokens = [[rare + common]]
        client = fake_client(
            {
                ("caballo", "NOUN"): answer(de="das Pferd", en="horse"),
                ("madriguera", "NOUN"): answer(de="der Bau", en="burrow"),
            }
        )

        result = gloss_lexicon(
            build_lexicon(tokens),
            tokens,
            book_id="test",
            options=GlossingOptions(extract_dir=extracts, claude_limit=1),
            cache=cache,
            now=NOW,
            client=client,
        )

        assert result.sent_to_claude == 1
        assert result.skipped_by_limit == 1
        # Check the lemma lines, not the whole prompt: both words share an
        # example sentence, so a substring test would match either way.
        prompt = client._requests[0]["params"]["messages"][0]["content"]
        asked = {line.split(" · ")[0] for line in prompt.splitlines() if " · " in line}
        assert asked == {"caballo"}

    def test_offline_mode_never_constructs_a_client(self, extracts, cache):
        tokens = [[[word("caballo")]]]

        result = gloss_lexicon(
            build_lexicon(tokens),
            tokens,
            book_id="test",
            options=GlossingOptions(use_claude=False, extract_dir=extracts),
            cache=cache,
            now=NOW,
        )

        assert result.ran_claude is False
        assert result.batch.requests == 0

    def test_a_lexicon_with_nothing_in_it_does_no_work(self, cache):
        result = gloss_lexicon(
            build_lexicon([]), [], book_id="test", cache=cache, now=NOW
        )

        assert result.glosses == {}


class TestBundleIntegration:
    """Glossing runs before classification. These pin that, because getting it
    backwards yields a valid-looking bundle that never teaches a mexicanism."""

    def _tokens(self):
        # bookCount 2 so only the mexicanism rule can teach it: below
        # min_book_count (3), and `chido` has a low enough zipf to miss that rule.
        return [[[word("chido", "ADJ"), word("chido", "ADJ")]]]

    def test_a_mexicanism_reaches_the_teach_set(self, extracts, cache, monkeypatch):
        tokens = self._tokens()
        lexicon = build_lexicon(tokens)

        result = gloss_lexicon(
            lexicon,
            tokens,
            book_id="test",
            options=GlossingOptions(use_claude=False, extract_dir=extracts),
            cache=cache,
            now=NOW,
        )

        entries = lexicon.entries_for_classification(result.mexicanism_by_key())
        key = next(iter(lexicon.records))
        assert entries[key].mexicanism is True

    def test_glosses_reach_the_lexicon_json(self, fixture_epub, extracts, monkeypatch):
        monkeypatch.setenv("MOLCAJETE_TEST", "1")
        built = build_bundle(
            fixture_epub,
            gloss=True,
            gloss_options=GlossingOptions(use_claude=False, extract_dir=extracts),
        )

        glossed = [e for e in built.bundle["lexicon"].values() if "en" in e]
        assert glossed, "no lemma in the fixture book picked up a gloss"
        assert all(isinstance(e["en"], str) and e["en"] for e in glossed)

    def test_a_no_gloss_build_is_still_a_valid_bundle(self, fixture_epub):
        built = build_bundle(fixture_epub, gloss=False)

        assert built.glossed is False
        assert all(
            entry["mexicanism"] is False
            for entry in built.bundle["lexicon"].values()
        )
        assert all("de" not in entry for entry in built.bundle["lexicon"].values())

    def test_a_no_gloss_build_teaches_nothing_by_the_mexicanism_rule(self, fixture_epub):
        """Worth stating out loud: --no-gloss does not merely omit glosses, it
        changes which lemmas are taught."""
        built = build_bundle(fixture_epub, gloss=False)

        reasons = {r.reason for r in built.classifications.values() if r.reason}
        assert all(reason.value != "mexicanism" for reason in reasons)

    def test_the_bundle_carries_no_lemmatizer_diagnostics(self, fixture_epub, extracts):
        """`not_spanish` and `corrected_lemma` are notes about spaCy, not about
        vocabulary. The reader has no use for a field saying the word it is
        about to render is not a word."""
        built = build_bundle(
            fixture_epub,
            gloss=True,
            gloss_options=GlossingOptions(use_claude=False, extract_dir=extracts),
        )

        for entry in built.bundle["lexicon"].values():
            assert "not_spanish" not in entry
            assert "corrected_lemma" not in entry


class TestSchemaGuards:
    def test_a_mexicanism_without_a_region_note_is_rejected(self):
        """A card that claims Mexican usage without saying what kind is a claim
        the reader cannot act on."""
        from molcajete_prep.schema import BundleValidationError, validate_bundle

        bundle = {
            "schemaVersion": 1,
            "book": {
                "id": "x", "title": "x", "author": "x", "language": "es",
                "variant": "es-MX", "totalTokens": 1, "uniqueLemmas": 1,
            },
            "chapters": [],
            "lexicon": {
                "m0000": {
                    "lemma": "chido", "pos": "ADJ", "zipf": 2.1,
                    "bookCount": 6, "firstChapter": 0, "mexicanism": True,
                    "de": "cool",
                }
            },
        }

        with pytest.raises(BundleValidationError, match="regionNote"):
            validate_bundle(bundle)

    def test_an_empty_gloss_string_is_rejected(self):
        """An absent `de` means "no gloss". An empty one means the same thing
        while rendering as a blank line on a card."""
        from molcajete_prep.schema import BundleValidationError, validate_bundle

        bundle = {
            "schemaVersion": 1,
            "book": {
                "id": "x", "title": "x", "author": "x", "language": "es",
                "variant": "es-MX", "totalTokens": 1, "uniqueLemmas": 1,
            },
            "chapters": [],
            "lexicon": {
                "m0000": {
                    "lemma": "libro", "pos": "NOUN", "zipf": 4.0,
                    "bookCount": 3, "firstChapter": 0, "mexicanism": False,
                    "de": "",
                }
            },
        }

        with pytest.raises(BundleValidationError, match="empty"):
            validate_bundle(bundle)
