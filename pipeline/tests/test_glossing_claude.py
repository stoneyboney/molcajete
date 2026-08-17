"""Tests for the Claude batch pass.

Nothing here touches the network or needs an API key. Batch results are faked
with the shape the SDK returns — `result.custom_id`, `result.result.type`,
`result.result.message.content[].text`, `result.result.message.usage` — so the
parsing under test is the same code the real run executes.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from molcajete_prep.glossing.claude import (
    BatchStats,
    GlossTask,
    ModelSettings,
    build_requests,
    chunk_tasks,
    custom_id_for,
    gloss_from_payload,
    parse_results,
    run,
)
from molcajete_prep.glossing.models import GlossSource
from molcajete_prep.glossing.prompts import GLOSS_SCHEMA, SYSTEM_PROMPT


def task(lemma: str, pos: str = "NOUN", **extra) -> GlossTask:
    return GlossTask(lemma=lemma, pos=pos, **extra)


def payload(lemma, pos="NOUN", **overrides):
    built = {
        "lemma": lemma,
        "pos": pos,
        "de": "der Bau",
        "en": "burrow",
        "mexicanism": False,
        "region_note": None,
        "not_spanish": False,
        "corrected_lemma": None,
    }
    built.update(overrides)
    return built


def succeeded(custom_id: str, glosses: list[dict], **usage):
    counts = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    counts.update(usage)
    return SimpleNamespace(
        custom_id=custom_id,
        result=SimpleNamespace(
            type="succeeded",
            message=SimpleNamespace(
                content=[SimpleNamespace(type="text", text=json.dumps({"glosses": glosses}))],
                usage=SimpleNamespace(**counts),
            ),
        ),
    )


def failed(custom_id: str, kind: str = "errored", error_type: str = "overloaded_error"):
    return SimpleNamespace(
        custom_id=custom_id,
        result=SimpleNamespace(type=kind, error=SimpleNamespace(type=error_type)),
    )


class TestRequestConstruction:
    def test_lemmas_are_chunked_so_one_prefix_serves_many(self):
        tasks = [task(f"palabra{i}") for i in range(60)]

        assert [len(c) for c in chunk_tasks(tasks, 25)] == [25, 25, 10]

    def test_custom_ids_use_only_the_characters_the_api_accepts(self):
        """It cannot be the lemma: Spanish lemmas carry accents and the mangled
        ones carry spaces, and `custom_id` takes only [A-Za-z0-9_-]."""
        import re

        assert re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", custom_id_for(0))
        assert re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", custom_id_for(99_999))

    def test_every_request_carries_a_cache_breakpoint_on_the_instructions(self):
        requests, _ = build_requests([task("madriguera")])

        system = requests[0]["params"]["system"][0]
        assert system["cache_control"] == {"type": "ephemeral", "ttl": "1h"}

    def test_the_cached_prefix_stays_clear_of_the_1024_token_minimum(self):
        """Sonnet 5 silently declines to cache a prefix under 1024 tokens — no
        error, just `cache_creation_input_tokens: 0`. A trim below this line
        would quietly multiply the bill, so the floor is asserted rather than
        assumed. Roughly 4 characters per token is the pessimistic ratio."""
        assert len(SYSTEM_PROMPT) >= 4500

    def test_the_output_schema_is_strict_enough_to_match_answers_to_questions(self):
        item = GLOSS_SCHEMA["properties"]["glosses"]["items"]

        assert item["additionalProperties"] is False
        assert "lemma" in item["required"] and "pos" in item["required"]

    def test_the_default_arm_spends_nothing_on_thinking(self):
        """Glossing is recall, not reasoning, and thinking tokens bill as output
        — the expensive half of a batch."""
        requests, _ = build_requests([task("madriguera")], ModelSettings())

        params = requests[0]["params"]
        assert params["thinking"] == {"type": "disabled"}
        assert params["output_config"]["effort"] == "low"
        assert params["model"] == "claude-sonnet-5"

    def test_the_comparison_arm_turns_thinking_on(self):
        settings = ModelSettings(name="medium", effort="medium", thinking=True)

        requests, _ = build_requests([task("madriguera")], settings)

        assert requests[0]["params"]["thinking"] == {"type": "adaptive"}
        assert requests[0]["params"]["output_config"]["effort"] == "medium"

    def test_the_example_sentence_reaches_the_prompt(self):
        """It is what settles which sense of `banco` a card teaches."""
        requests, _ = build_requests(
            [task("banco", example_es="Se sentó en el banco del río.")]
        )

        assert "banco del río" in requests[0]["params"]["messages"][0]["content"]

    def test_wiktionary_context_reaches_the_prompt_when_we_have_it(self):
        requests, _ = build_requests(
            [
                task(
                    "madriguera",
                    wiktionary_en="burrow, den",
                    wiktionary_de="unterirdischer Unterschlupf eines Tieres",
                    region_hint="Mexico",
                )
            ]
        )

        content = requests[0]["params"]["messages"][0]["content"]
        assert "burrow, den" in content
        assert "unterirdischer Unterschlupf" in content
        assert "Mexico" in content

    def test_the_map_back_to_lemmas_covers_every_request(self):
        tasks = [task(f"palabra{i}") for i in range(30)]

        requests, by_custom_id = build_requests(tasks)

        assert set(by_custom_id) == {r["custom_id"] for r in requests}
        assert sum(len(c) for c in by_custom_id.values()) == 30


class TestResultParsing:
    def test_a_clean_batch_produces_one_gloss_per_lemma(self):
        tasks = [task("madriguera"), task("chido", "ADJ")]
        _, by_id = build_requests(tasks)
        results = [
            succeeded(
                "gloss-00000",
                [
                    payload("madriguera"),
                    payload("chido", "ADJ", de="cool, super", en="cool, great"),
                ],
            )
        ]

        glosses, stats = parse_results(results, by_id)

        assert glosses[("madriguera", "NOUN")].de == "der Bau"
        assert glosses[("chido", "ADJ")].en == "cool, great"
        assert stats.succeeded == 1 and stats.missing == 0

    def test_answers_are_matched_by_lemma_not_by_position(self):
        """Structured outputs pin the shape, not the ordering."""
        tasks = [task("uno"), task("dos"), task("tres")]
        _, by_id = build_requests(tasks)
        results = [
            succeeded(
                "gloss-00000",
                [payload("tres", de="drei"), payload("uno", de="eins"), payload("dos", de="zwei")],
            )
        ]

        glosses, _ = parse_results(results, by_id)

        assert glosses[("uno", "NOUN")].de == "eins"
        assert glosses[("dos", "NOUN")].de == "zwei"
        assert glosses[("tres", "NOUN")].de == "drei"

    def test_results_arriving_out_of_order_are_all_collected(self):
        tasks = [task(f"palabra{i}") for i in range(50)]
        _, by_id = build_requests(tasks)
        results = [
            succeeded("gloss-00001", [payload(f"palabra{i}") for i in range(25, 50)]),
            succeeded("gloss-00000", [payload(f"palabra{i}") for i in range(25)]),
        ]

        glosses, stats = parse_results(results, by_id)

        assert len(glosses) == 50
        assert stats.missing == 0

    def test_a_failed_request_costs_only_its_own_lemmas(self):
        tasks = [task(f"palabra{i}") for i in range(50)]
        _, by_id = build_requests(tasks)
        results = [
            succeeded("gloss-00000", [payload(f"palabra{i}") for i in range(25)]),
            failed("gloss-00001"),
        ]

        glosses, stats = parse_results(results, by_id)

        assert len(glosses) == 25
        assert stats.errored == 1
        assert stats.missing == 25
        assert "gloss-00001" in stats.errors[0]

    @pytest.mark.parametrize(
        ("kind", "attribute"), [("expired", "expired"), ("canceled", "canceled")]
    )
    def test_expired_and_canceled_requests_are_counted_separately(self, kind, attribute):
        _, by_id = build_requests([task("madriguera")])

        _, stats = parse_results([failed("gloss-00000", kind)], by_id)

        assert getattr(stats, attribute) == 1

    def test_a_response_that_is_not_json_is_an_error_not_a_crash(self):
        _, by_id = build_requests([task("madriguera")])
        broken = SimpleNamespace(
            custom_id="gloss-00000",
            result=SimpleNamespace(
                type="succeeded",
                message=SimpleNamespace(
                    content=[SimpleNamespace(type="text", text="I'm sorry, but")],
                    usage=SimpleNamespace(
                        input_tokens=10,
                        output_tokens=5,
                        cache_creation_input_tokens=0,
                        cache_read_input_tokens=0,
                    ),
                ),
            ),
        )

        glosses, stats = parse_results([broken], by_id)

        assert glosses == {}
        assert stats.errored == 1

    def test_a_gloss_for_a_lemma_that_was_never_asked_for_is_dropped(self):
        _, by_id = build_requests([task("madriguera")])
        results = [succeeded("gloss-00000", [payload("madriguera"), payload("inventado")])]

        glosses, stats = parse_results(results, by_id)

        assert set(glosses) == {("madriguera", "NOUN")}
        assert stats.unmatched == 1

    def test_lemmas_the_model_skipped_are_counted_as_missing(self):
        tasks = [task("madriguera"), task("chido", "ADJ")]
        _, by_id = build_requests(tasks)

        _, stats = parse_results([succeeded("gloss-00000", [payload("madriguera")])], by_id)

        assert stats.missing == 1

    def test_a_lemma_echoed_with_different_casing_still_matches(self):
        _, by_id = build_requests([task("madriguera")])

        glosses, stats = parse_results(
            [succeeded("gloss-00000", [payload("Madriguera")])], by_id
        )

        assert set(glosses) == {("madriguera", "NOUN")}
        assert stats.unmatched == 0

    def test_the_lexicon_key_comes_from_the_task_not_from_the_echo(self):
        """An echo with a stray accent must not create a second lexicon entry."""
        _, by_id = build_requests([task("madriguera")])

        glosses, _ = parse_results([succeeded("gloss-00000", [payload("madriguera")])], by_id)

        assert glosses[("madriguera", "NOUN")].lemma == "madriguera"


class TestGlossQuality:
    def test_an_overlong_gloss_is_cut_down_and_counted(self):
        """The rule is prose in the prompt because JSON Schema cannot express a
        word count, so it is enforced again here."""
        built, truncated = gloss_from_payload(
            payload("madriguera", de="Bau, Höhle, unterirdischer Unterschlupf eines Tieres"),
            task("madriguera"),
        )

        assert built.de == "Bau, Höhle"
        assert truncated is True

    def test_a_gloss_with_no_short_alternative_is_clipped_rather_than_dropped(self):
        """A clipped gloss still beats a blank card, and the count makes it
        visible in the report."""
        built, truncated = gloss_from_payload(
            payload("madriguera", de="unterirdischer Unterschlupf eines Tieres"),
            task("madriguera"),
        )

        assert built.de == "unterirdischer Unterschlupf eines"
        assert truncated is True

    def test_a_card_sized_gloss_is_left_alone(self):
        built, truncated = gloss_from_payload(payload("madriguera", de="der Bau"), task("madriguera"))

        assert built.de == "der Bau"
        assert truncated is False

    def test_a_rejected_lemma_carries_no_gloss_at_all(self):
        """Trusting a gloss that arrived beside not_spanish would put an invented
        word on a card, which is worse than a blank."""
        built, _ = gloss_from_payload(
            payload(
                "acaeceír",
                "VERB",
                de="geschehen",
                en="to happen",
                not_spanish=True,
                corrected_lemma="acaecer",
                mexicanism=True,
            ),
            task("acaeceír", "VERB"),
        )

        assert built.de is None and built.en is None
        assert built.mexicanism is False
        assert built.not_spanish is True
        assert built.corrected_lemma == "acaecer"

    def test_sources_are_recorded_only_for_the_fields_actually_filled(self):
        built, _ = gloss_from_payload(payload("madriguera", en=None), task("madriguera"))

        assert built.de_source is GlossSource.CLAUDE
        assert built.en_source is None

    def test_an_empty_string_is_treated_as_no_gloss(self):
        built, _ = gloss_from_payload(payload("x", de="   ", en=""), task("x"))

        assert built.de is None and built.en is None

    def test_a_mexicanism_and_its_german_note_survive(self):
        built, _ = gloss_from_payload(
            payload(
                "chido",
                "ADJ",
                de="cool, super",
                mexicanism=True,
                region_note="Mexiko, umgangssprachlich",
            ),
            task("chido", "ADJ"),
        )

        assert built.mexicanism is True
        assert built.region_note == "Mexiko, umgangssprachlich"


class TestAccounting:
    def test_token_usage_accumulates_across_requests(self):
        tasks = [task(f"palabra{i}") for i in range(50)]
        _, by_id = build_requests(tasks)
        results = [
            succeeded(
                "gloss-00000",
                [payload(f"palabra{i}") for i in range(25)],
                input_tokens=900,
                output_tokens=700,
                cache_creation_input_tokens=1500,
            ),
            succeeded(
                "gloss-00001",
                [payload(f"palabra{i}") for i in range(25, 50)],
                input_tokens=900,
                output_tokens=700,
                cache_read_input_tokens=1500,
            ),
        ]

        _, stats = parse_results(results, by_id)

        assert stats.input_tokens == 1800
        assert stats.output_tokens == 1400
        assert stats.cache_creation_tokens == 1500
        assert stats.cache_read_tokens == 1500
        # 1800 uncached + 1500 written at 1.25x + 1500 read at 0.1x, all at
        # $1/MTok, plus 1400 output at $5/MTok.
        assert stats.estimated_cost() == pytest.approx(0.010825, abs=1e-6)

    def test_a_multi_request_batch_that_never_read_cache_is_flagged(self):
        """The only visible symptom of a system prompt trimmed under 1024
        tokens. There is no API error for it."""
        stats = BatchStats(requests=4, cache_read_tokens=0)

        assert stats.cache_worked is False

    def test_a_single_request_batch_is_not_expected_to_read_cache(self):
        assert BatchStats(requests=1, cache_read_tokens=0).cache_worked is True

    def test_merging_two_arms_sums_their_counts_and_errors(self):
        first = BatchStats(requests=2, succeeded=2, output_tokens=100, errors=["a"])
        second = BatchStats(requests=2, succeeded=1, errored=1, output_tokens=50, errors=["b"])

        first.merge(second)

        assert (first.requests, first.succeeded, first.errored) == (4, 3, 1)
        assert first.output_tokens == 150
        assert first.errors == ["a", "b"]


class TestRunShortCircuits:
    def test_an_empty_task_list_never_constructs_a_client(self):
        """Guards against a build with full Wiktionary coverage paying for a
        batch of nothing — and against needing an API key to build one."""
        glosses, stats = run([])

        assert glosses == {} and stats.requests == 0
