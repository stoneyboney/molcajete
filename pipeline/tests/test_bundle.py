from __future__ import annotations

import json
from datetime import datetime

import pytest

from molcajete_book.bundle import (
    build_bundle,
    make_book_id,
    slugify,
    write_bundle,
)
from molcajete_prep.classify import ClassificationOptions
from molcajete_book.report import render_report
from molcajete_book.schema import BundleValidationError, validate_bundle

BUILT_AT = datetime(2026, 8, 16, 20, 14, 3)


@pytest.fixture(scope="module")
def built(fixture_epub):
    """Build the fixture bundle once; several tests read it."""
    return build_bundle(fixture_epub, gloss=False)


class TestSlugs:
    def test_slugify_strips_accents_and_punctuation(self):
        assert slugify("Los de abajo") == "los-de-abajo"
        assert slugify("¿Quién? ¡Montañés!") == "quien-montanes"

    def test_book_id_is_surname_plus_title(self):
        assert make_book_id("Mariano Azuela", "Los de abajo") == "azuela-los-de-abajo"

    def test_book_id_matches_the_spec_example_shape(self):
        assert (
            make_book_id("Juan Pablo Villalobos", "Fiesta en la madriguera")
            == "villalobos-fiesta-en-la-madriguera"
        )

    def test_book_id_survives_missing_metadata(self):
        assert make_book_id("", "") == "libro"


class TestBundleShape:
    def test_the_fixture_bundle_validates(self, built):
        validate_bundle(built.bundle)

    def test_schema_version_is_one(self, built):
        assert built.bundle["schemaVersion"] == 1

    def test_book_metadata_is_filled(self, built):
        book = built.bundle["book"]

        assert book["title"] == "Los del cerro"
        assert book["author"] == "Anónimo"
        assert book["language"] == "es"
        assert book["variant"] == "es-MX"
        assert book["totalTokens"] > 0
        assert book["uniqueLemmas"] == len(built.bundle["lexicon"])

    def test_chapters_are_indexed_from_zero_in_order(self, built):
        assert [c["index"] for c in built.bundle["chapters"]] == [0, 1, 2]

    def test_paragraph_ids_follow_the_spec_pattern(self, built):
        first = built.bundle["chapters"][0]["paragraphs"][0]

        assert first["id"] == "c0p0"

    def test_token_count_counts_words_not_punctuation(self, built):
        chapter = built.bundle["chapters"][0]
        tokens = [t for p in chapter["paragraphs"] for t in p["tokens"]]

        assert chapter["tokenCount"] < len(tokens)
        assert chapter["tokenCount"] > 0


class TestTokens:
    def test_whitespace_tokens_carry_only_s_and_ws(self, built):
        tokens = [
            token
            for chapter in built.bundle["chapters"]
            for paragraph in chapter["paragraphs"]
            for token in paragraph["tokens"]
            if token.get("ws")
        ]

        assert tokens
        assert all(set(token) == {"s", "ws"} for token in tokens)

    def test_lexicon_references_are_string_keys(self, built):
        """SPEC §4's example shows integers here; its own lexicon is keyed by
        strings and Appendix A assigns the key. The strings win."""
        keys = [
            token["t"]
            for chapter in built.bundle["chapters"]
            for paragraph in chapter["paragraphs"]
            for token in paragraph["tokens"]
            if "t" in token
        ]

        assert keys
        assert all(isinstance(key, str) and key.startswith("m") for key in keys)

    def test_every_reference_resolves(self, built):
        lexicon = built.bundle["lexicon"]

        for chapter in built.bundle["chapters"]:
            for paragraph in chapter["paragraphs"]:
                for token in paragraph["tokens"]:
                    if "t" in token:
                        assert token["t"] in lexicon

    def test_proper_nouns_keep_their_tag_and_carry_no_reference(self, built):
        """The reader reads `p` to decide a word needs no gloss. A name demoted
        to NOUN would look like vocabulary with a missing lexicon entry."""
        names = [
            token
            for chapter in built.bundle["chapters"]
            for paragraph in chapter["paragraphs"]
            for token in paragraph["tokens"]
            if token.get("l") == "demetrio"
        ]

        assert names
        assert all(token["p"] == "PROPN" for token in names)
        assert all("t" not in token for token in names)

    def test_surfaces_rejoin_into_the_source_text(self, built, fixture_chapters):
        for chapter, (_title, paragraphs) in zip(
            built.bundle["chapters"], fixture_chapters, strict=True
        ):
            for paragraph, expected in zip(
                chapter["paragraphs"], paragraphs, strict=True
            ):
                assert "".join(t["s"] for t in paragraph["tokens"]) == expected


class TestLexiconSerialization:
    def test_entries_carry_what_phase_one_can_compute(self, built):
        entry = next(iter(built.bundle["lexicon"].values()))

        assert set(entry) >= {
            "lemma",
            "pos",
            "zipf",
            "bookCount",
            "firstChapter",
            "mexicanism",
        }

    def test_glosses_are_absent_until_phase_two(self, built):
        for entry in built.bundle["lexicon"].values():
            assert "de" not in entry
            assert "en" not in entry

    def test_mexicanism_is_written_explicitly_as_false(self, built):
        """Written rather than omitted, so its absence can never be read as
        'not yet determined'."""
        assert all(
            entry["mexicanism"] is False for entry in built.bundle["lexicon"].values()
        )

    def test_examples_are_attached_to_teach_lemmas_only(self, built):
        teach = {k for k, v in built.classifications.items() if v.is_teach}

        for key, entry in built.bundle["lexicon"].items():
            if "example" in entry:
                assert key in teach
                assert entry["example"]["es"]
                assert isinstance(entry["example"]["chapterIndex"], int)


class TestDeterminism:
    def test_building_twice_produces_byte_identical_json(self, fixture_epub, tmp_path):
        first = write_bundle(build_bundle(fixture_epub, gloss=False).bundle, tmp_path / "a.json")
        second = write_bundle(build_bundle(fixture_epub, gloss=False).bundle, tmp_path / "b.json")

        assert first.read_bytes() == second.read_bytes()

    def test_written_json_round_trips(self, built, tmp_path):
        path = write_bundle(built.bundle, tmp_path / "bundle.json")

        assert json.loads(path.read_text(encoding="utf-8")) == built.bundle

    def test_pretty_and_compact_carry_the_same_data(self, built, tmp_path):
        compact = write_bundle(built.bundle, tmp_path / "c.json")
        pretty = write_bundle(built.bundle, tmp_path / "p.json", pretty=True)

        assert json.loads(compact.read_text()) == json.loads(pretty.read_text())
        assert pretty.stat().st_size > compact.stat().st_size


class TestKnownLemmas:
    def test_seeding_a_known_lemma_removes_it_from_every_teach_set(self, fixture_epub):
        unseeded = build_bundle(fixture_epub, gloss=False)
        taught = unseeded.bundle["lexicon"][unseeded.chapter_vocabulary[0].teach[0]]

        seeded = build_bundle(fixture_epub, gloss=False, known_lemmas=frozenset({taught["lemma"]}))

        all_teach = [k for c in seeded.bundle["chapters"] for k in c["teachSet"]]
        assert all(
            seeded.bundle["lexicon"][key]["lemma"] != taught["lemma"]
            for key in all_teach
        )


class TestOptions:
    def test_raising_the_zipf_threshold_shrinks_the_teach_set(self, fixture_epub):
        default = build_bundle(fixture_epub, gloss=False)
        strict = build_bundle(
            fixture_epub,
            gloss=False,
            options=ClassificationOptions(min_book_count=99, zipf_threshold=9.0),
        )

        def teach_count(result):
            return sum(len(c["teachSet"]) for c in result.bundle["chapters"])

        assert teach_count(strict) < teach_count(default)


class TestValidator:
    def test_rejects_a_missing_schema_version(self, built):
        bundle = dict(built.bundle)
        del bundle["schemaVersion"]

        with pytest.raises(BundleValidationError, match="schemaVersion"):
            validate_bundle(bundle)

    def test_rejects_a_future_schema_version(self, built):
        bundle = {**built.bundle, "schemaVersion": 2}

        with pytest.raises(BundleValidationError, match="unsupported schemaVersion"):
            validate_bundle(bundle)

    def test_rejects_a_dangling_lexicon_reference(self, built):
        bundle = json.loads(json.dumps(built.bundle))
        bundle["chapters"][0]["paragraphs"][0]["tokens"][0]["t"] = "m9999"
        bundle["chapters"][0]["paragraphs"][0]["tokens"][0]["l"] = "x"

        with pytest.raises(BundleValidationError, match="unknown lexicon key"):
            validate_bundle(bundle)

    def test_rejects_a_token_with_no_surface(self, built):
        bundle = json.loads(json.dumps(built.bundle))
        del bundle["chapters"][0]["paragraphs"][0]["tokens"][0]["s"]

        with pytest.raises(BundleValidationError, match="no 's'"):
            validate_bundle(bundle)

    def test_rejects_a_whitespace_token_carrying_a_lemma(self, built):
        bundle = json.loads(json.dumps(built.bundle))
        tokens = bundle["chapters"][0]["paragraphs"][0]["tokens"]
        whitespace = next(t for t in tokens if t.get("ws"))
        whitespace["l"] = "el"

        with pytest.raises(BundleValidationError, match="whitespace token"):
            validate_bundle(bundle)

    def test_rejects_misnumbered_chapters(self, built):
        bundle = json.loads(json.dumps(built.bundle))
        bundle["chapters"][1]["index"] = 7

        with pytest.raises(BundleValidationError, match="index is 7"):
            validate_bundle(bundle)

    def test_rejects_a_teach_set_naming_an_unknown_lemma(self, built):
        bundle = json.loads(json.dumps(built.bundle))
        bundle["chapters"][0]["teachSet"].append("m9999")

        with pytest.raises(BundleValidationError, match="unknown lexicon key"):
            validate_bundle(bundle)

    def test_rejects_a_lemma_count_that_disagrees_with_the_lexicon(self, built):
        bundle = json.loads(json.dumps(built.bundle))
        bundle["book"]["uniqueLemmas"] += 1

        with pytest.raises(BundleValidationError, match="uniqueLemmas"):
            validate_bundle(bundle)


class TestReport:
    def test_report_answers_the_three_required_questions(self, built):
        report = render_report(built, built_at=BUILT_AT)

        assert "Total distinct lemmas" in report
        assert "Teach" in report
        assert "Gloss only" in report
        assert "Skipped (PROPN)" in report
        assert "TOP 20 TEACH LEMMAS BY BOOK COUNT" in report

    def test_report_is_deterministic_for_a_fixed_timestamp(self, built):
        assert render_report(built, built_at=BUILT_AT) == render_report(
            built, built_at=BUILT_AT
        )

    def test_report_names_the_over_cap_chapters(self, built):
        report = render_report(built, built_at=BUILT_AT)

        assert "18-card cap" in report

    def test_report_flags_lemmas_wordfreq_has_never_seen(self, built):
        report = render_report(built, built_at=BUILT_AT)

        assert "zipf 0.00" in report

    def test_report_says_when_no_seed_was_applied(self, built):
        report = render_report(built, built_at=BUILT_AT)

        assert "unseeded worst-case" in report

    def test_report_shows_the_bundle_size_when_given_one(self, built):
        report = render_report(built, built_at=BUILT_AT, bundle_bytes=3_400_000)

        assert "3.4 MB" in report
