"""Tests for the local gloss provider.

Nothing here needs Ollama installed, running, or a model pulled. The provider
takes a `transport` — a callable of `(url, payload, timeout)` returning the
decoded response — and every test drives that, so the parsing, the length
enforcement, the retry and the give-up are the same code a real run executes.

The bulk of these are about a model behaving badly, because that is the whole
reason the local path is written differently from the Claude one. A hosted model
echoes what it was asked and keeps to a word limit; a 12B model on a laptop does
neither reliably, and the build has to survive it without putting a definition
on a flashcard.
"""

from __future__ import annotations

import json
import urllib.error

import pytest

from molcajete_prep.glossing.models import GlossSource
from molcajete_prep.glossing.ollama import (
    LocalStats,
    OllamaProvider,
    OllamaUnavailableError,
)
from molcajete_prep.glossing.provider import GlossTask, ProviderOptions, build_provider

CASA = GlossTask(lemma="casa", pos="NOUN", example_es="La casa era blanca.")
CHIDO = GlossTask(lemma="chido", pos="ADJ", example_es="Está bien chido tu carro.")


def gloss_object(lemma="casa", pos="NOUN", **overrides):
    built = {
        "lemma": lemma,
        "pos": pos,
        "de": "das Haus",
        "en": "house",
        "mexicanism": False,
        "region_note": None,
        "not_spanish": False,
        "corrected_lemma": None,
    }
    built.update(overrides)
    return built


def response(objects, *, prompt_tokens=100, output_tokens=20):
    """One Ollama /api/chat reply, shaped as the server returns it."""
    return {
        "message": {"content": json.dumps({"glosses": objects})},
        "prompt_eval_count": prompt_tokens,
        "eval_count": output_tokens,
    }


def raw_response(text: str):
    return {"message": {"content": text}, "prompt_eval_count": 1, "eval_count": 1}


class Transport:
    """Replies from a script, one per call, and records what it was sent."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.payloads: list[dict] = []

    def __call__(self, url, payload, timeout):
        self.payloads.append(payload)
        reply = self.replies[min(len(self.payloads) - 1, len(self.replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        return reply

    @property
    def calls(self) -> int:
        return len(self.payloads)

    def prompt(self, index: int) -> str:
        return self.payloads[index]["messages"][-1]["content"]


def provider(*replies, **options):
    return OllamaProvider(transport=Transport(*replies), **options)


class TestTheHappyPath:
    def test_a_clean_answer_becomes_a_gloss(self):
        local = provider(response([gloss_object()]))

        glosses, stats = local.gloss([CASA])

        gloss = glosses[("casa", "NOUN")]
        assert gloss.de == "das Haus"
        assert gloss.en == "house"
        assert stats.glosses_returned == 1
        assert stats.failed_after_retry == 0

    def test_the_gloss_is_attributed_to_the_local_model(self):
        """So `_wants_model` will not send it again, and the report can separate
        what a dictionary knew from what a model asserted."""
        local = provider(response([gloss_object()]))

        gloss = local.gloss([CASA])[0][("casa", "NOUN")]

        assert gloss.de_source is GlossSource.OLLAMA
        assert gloss.en_source is GlossSource.OLLAMA

    def test_the_example_sentence_reaches_the_prompt(self):
        """It is what settles which sense of a word is being asked about."""
        local = provider(response([gloss_object()]))
        local.gloss([CASA])

        assert "La casa era blanca." in local.transport.prompt(0)

    def test_the_schema_constrains_generation(self):
        """Ollama's structured output is the first line of defence; the checks
        in Python are the second."""
        local = provider(response([gloss_object()]))
        local.gloss([CASA])

        assert local.transport.payloads[0]["format"]["type"] == "object"
        assert local.transport.payloads[0]["stream"] is False

    def test_a_mexicanism_without_a_note_still_gets_one(self):
        """The bundle validator rejects the pair, and a local model is exactly
        the kind that sets the flag and forgets the note."""
        local = provider(
            response([gloss_object("chido", "ADJ", de="cool", en="cool", mexicanism=True)])
        )

        gloss = local.gloss([CHIDO])[0][("chido", "ADJ")]

        assert gloss.mexicanism is True
        assert gloss.region_note == "Mexiko"

    def test_a_rejected_lemma_carries_no_gloss(self):
        local = provider(
            response(
                [
                    gloss_object(
                        "acaeceír",
                        "VERB",
                        de="geschehen",
                        en="happen",
                        not_spanish=True,
                        corrected_lemma="acaecer",
                    )
                ]
            )
        )

        gloss = local.gloss([GlossTask("acaeceír", "VERB")])[0][("acaeceír", "VERB")]

        assert gloss.not_spanish is True
        assert gloss.de is None and gloss.en is None
        assert gloss.corrected_lemma == "acaecer"


class TestLengthIsEnforcedInCode:
    """The prompt asks for one to three words. The prompt is not the mechanism."""

    def test_a_definition_is_rejected_and_re_asked(self):
        local = provider(
            response([gloss_object(de="unterirdischer Unterschlupf eines Tieres")]),
            response([gloss_object(de="der Bau")]),
        )

        glosses, stats = local.gloss([CASA])

        assert local.transport.calls == 2
        assert stats.over_length == 1
        assert stats.retried == 1
        assert glosses[("casa", "NOUN")].de == "der Bau"

    def test_too_many_alternatives_are_rejected_and_re_asked(self):
        local = provider(
            response([gloss_object(de="das Haus, das Heim, die Bude, die Hütte")]),
            response([gloss_object(de="das Haus")]),
        )

        _, stats = local.gloss([CASA])

        assert stats.over_length == 1
        assert local.transport.calls == 2

    def test_a_gloss_that_fits_is_not_re_asked(self):
        local = provider(response([gloss_object(de="das Haus, das Heim")]))

        _, stats = local.gloss([CASA])

        assert local.transport.calls == 1
        assert stats.over_length == 0

    def test_a_parenthetical_does_not_count_against_the_limit(self):
        local = provider(response([gloss_object(de="(Architektur) das Haus")]))

        glosses, stats = local.gloss([CASA])

        assert stats.over_length == 0
        assert glosses[("casa", "NOUN")].de == "das Haus"

    def test_a_surplus_of_short_alternatives_is_kept_on_the_last_attempt(self):
        """Trimmed and clipped deserve opposite treatment when the retries run
        out. "das Haus, das Heim, die Bude, die Hütte" cut to three is still
        good card text, so it is kept rather than thrown away."""
        local = provider(
            response([gloss_object(de="das Haus, das Heim, die Bude, die Hütte")]),
            response([gloss_object(de="das Haus, das Heim, die Bude, die Hütte")]),
        )

        glosses, stats = local.gloss([CASA])

        assert glosses[("casa", "NOUN")].de == "das Haus, das Heim, die Bude"
        assert stats.salvaged == 1
        assert stats.failed_after_retry == 0

    def test_a_definition_is_still_a_miss_on_the_last_attempt(self):
        """Cutting a definition to three words yields wreckage, not a gloss, and
        a missing gloss the report counts beats a bad one on a card."""
        definition = response([gloss_object(de="unterirdischer Unterschlupf eines Tieres")])
        local = provider(definition, definition)

        glosses, stats = local.gloss([CASA])

        assert glosses == {}
        assert stats.failed_after_retry == 1


class TestMalformedAnswers:
    def test_unparseable_output_is_re_asked(self):
        local = provider(
            raw_response("Sure! Here are your glosses:"),
            response([gloss_object()]),
        )

        glosses, stats = local.gloss([CASA])

        assert stats.malformed_json == 1
        assert glosses[("casa", "NOUN")].de == "das Haus"

    def test_an_empty_answer_is_re_asked(self):
        local = provider(raw_response("   "), response([gloss_object()]))

        _, stats = local.gloss([CASA])

        assert stats.malformed_json == 1
        assert local.transport.calls == 2

    def test_a_missing_glosses_array_is_re_asked(self):
        local = provider(
            raw_response(json.dumps({"result": "ok"})),
            response([gloss_object()]),
        )

        _, stats = local.gloss([CASA])

        assert stats.schema_violations == 1

    def test_a_bare_array_is_accepted_without_a_retry(self):
        """Unambiguous, and not worth a round trip to punish."""
        local = provider(raw_response(json.dumps([gloss_object()])))

        glosses, stats = local.gloss([CASA])

        assert glosses[("casa", "NOUN")].de == "das Haus"
        assert stats.retried == 0

    def test_a_missing_field_is_re_asked(self):
        broken = gloss_object()
        del broken["mexicanism"]
        local = provider(response([broken]), response([gloss_object()]))

        _, stats = local.gloss([CASA])

        assert stats.schema_violations == 1

    def test_an_answer_for_the_wrong_lemma_is_rejected(self):
        """The single most dangerous failure: a plausible gloss filed under the
        wrong word, which nothing downstream could detect."""
        local = provider(
            response([gloss_object("casona", "NOUN")]),
            response([gloss_object()]),
        )

        glosses, stats = local.gloss([CASA])

        assert stats.wrong_echo == 1
        assert ("casona", "NOUN") not in glosses
        assert glosses[("casa", "NOUN")].de == "das Haus"

    def test_a_partly_answered_chunk_is_rejected_rather_than_half_kept(self):
        both = [CASA, CHIDO]
        local = provider(
            response([gloss_object()]),
            response([gloss_object(), gloss_object("chido", "ADJ", de="cool", en="cool")]),
            chunk_size=2,
        )

        glosses, stats = local.gloss(both)

        assert stats.schema_violations == 1
        assert len(glosses) == 2


class TestGivingUp:
    def test_a_lemma_that_never_parses_is_a_miss_not_a_crash(self):
        junk = raw_response("not json at all")
        local = provider(junk, junk)

        glosses, stats = local.gloss([CASA])

        assert glosses == {}
        assert stats.failed_after_retry == 1
        assert stats.missing == 1

    def test_one_bad_lemma_does_not_cost_the_others_their_glosses(self):
        """The reason the default chunk is one lemma rather than twenty-five."""

        def transport(url, payload, timeout):
            asked = payload["messages"][-1]["content"]
            if "chido" in asked:
                return raw_response("¯\\_(ツ)_/¯")
            return response([gloss_object()])

        local = OllamaProvider(transport=transport)

        glosses, stats = local.gloss([CASA, CHIDO])

        assert ("casa", "NOUN") in glosses
        assert ("chido", "ADJ") not in glosses
        assert stats.failed_after_retry == 1

    def test_no_retries_means_one_attempt(self):
        local = provider(raw_response("junk"), retries=0)

        glosses, _ = local.gloss([CASA])

        assert local.transport.calls == 1
        assert glosses == {}

    def test_more_retries_means_more_attempts(self):
        local = provider(raw_response("junk"), retries=3)

        local.gloss([CASA])

        assert local.transport.calls == 4


class TestTheEchoedLemma:
    """The echo check catches the most dangerous failure there is — a plausible
    gloss filed under the wrong word. It must not also catch the prompt's own
    punctuation coming back."""

    def test_the_prompts_own_separator_is_stripped_before_comparing(self):
        """gemma3:12b echoes the whole input line, `lunes · NOUN`, into the
        lemma field. The gloss beside it was `der Montag`, and rejecting that
        over a separator this code wrote is a self-inflicted miss."""
        local = provider(response([gloss_object("lunes · NOUN", "NOUN", de="der Montag")]))

        glosses, stats = local.gloss([GlossTask("lunes", "NOUN")])

        assert glosses[("lunes", "NOUN")].de == "der Montag"
        assert stats.wrong_echo == 0

    def test_surrounding_whitespace_and_case_do_not_matter(self):
        local = provider(response([gloss_object("  CASA  ")]))

        assert local.gloss([CASA])[0][("casa", "NOUN")].de == "das Haus"

    def test_a_genuinely_different_word_is_still_rejected(self):
        """The loosening must stay narrow enough to keep doing its job."""
        local = provider(
            response([gloss_object("casona · NOUN", "NOUN")]),
            response([gloss_object()]),
        )

        _, stats = local.gloss([CASA])

        assert stats.wrong_echo == 1


class TestTheRetryPrompt:
    def test_the_first_attempt_is_greedy_so_a_build_is_reproducible(self):
        local = provider(response([gloss_object()]))
        local.gloss([CASA])

        assert local.transport.payloads[0]["options"]["temperature"] == 0.0

    def test_a_retry_is_not_greedy_so_it_can_answer_differently(self):
        """At temperature zero the model is a function of its input, and the
        first observed retry returned a byte-identical answer. A little heat is
        what makes the second attempt a second attempt."""
        local = provider(raw_response("junk"), response([gloss_object()]))
        local.gloss([CASA])

        assert local.transport.payloads[1]["options"]["temperature"] > 0.0

    def test_the_correction_quotes_the_model_its_own_answer(self):
        """Naming the rule alone produces the same answer again."""
        local = provider(
            response([gloss_object(de="unterirdischer Unterschlupf eines Tieres")]),
            response([gloss_object(de="der Bau")]),
        )
        local.gloss([CASA])

        retry = local.transport.prompt(1)
        assert "unterirdischer Unterschlupf eines Tieres" in retry

    def test_the_correction_restates_the_rule_and_repeats_the_question(self):
        local = provider(raw_response("junk"), response([gloss_object()]))
        local.gloss([CASA])

        retry = local.transport.prompt(1)
        assert "rejected" in retry.lower()
        assert "casa · NOUN" in retry

    def test_a_transport_failure_does_not_send_a_correction(self):
        """There is no bad answer to quote back — the request never landed."""
        local = provider(TimeoutError("too slow"), response([gloss_object()]))

        local.gloss([CASA])

        assert "rejected" not in local.transport.prompt(1).lower()


class TestTransportFailures:
    def test_a_timeout_is_counted_and_retried(self):
        local = provider(TimeoutError("too slow"), response([gloss_object()]))

        glosses, stats = local.gloss([CASA])

        assert stats.timeouts == 1
        assert glosses[("casa", "NOUN")].de == "das Haus"

    def test_an_unreachable_server_stops_the_build(self):
        """Not a lemma the model got wrong. Nine thousand identical failures is
        not a partial result, so this is the one thing that raises."""
        local = provider(urllib.error.URLError("connection refused"))

        with pytest.raises(OllamaUnavailableError) as raised:
            local.gloss([CASA])

        assert "ollama serve" in str(raised.value)


class TestChunkingAndConcurrency:
    def test_the_default_is_one_lemma_per_request(self):
        local = provider(response([gloss_object()]))

        assert local.chunk_size == 1

    def test_a_larger_chunk_asks_for_several_at_once(self):
        local = provider(
            response([gloss_object(), gloss_object("chido", "ADJ", de="cool", en="cool")]),
            chunk_size=2,
        )

        glosses, stats = local.gloss([CASA, CHIDO])

        assert local.transport.calls == 1
        assert stats.requests == 1
        assert len(glosses) == 2

    def test_every_lemma_is_glossed_under_concurrency(self):
        tasks = [GlossTask(f"palabra{i:03d}", "NOUN") for i in range(24)]

        def transport(url, payload, timeout):
            asked = payload["messages"][-1]["content"].split(" · ")[0].split("\n")[-1]
            return response([gloss_object(asked, "NOUN")])

        glosses, stats = OllamaProvider(transport=transport, concurrency=4).gloss(tasks)

        assert len(glosses) == 24
        assert stats.requests == 24
        assert stats.missing == 0

    def test_concurrency_is_conservative_by_default(self):
        """A local model saturates the machine; four in flight mostly costs
        memory the model itself wants."""
        assert OllamaProvider().concurrency == 2


class TestStats:
    def test_tokens_and_wall_clock_are_recorded(self):
        local = provider(response([gloss_object()], prompt_tokens=800, output_tokens=40))

        _, stats = local.gloss([CASA])

        assert stats.input_tokens == 800
        assert stats.output_tokens == 40
        assert stats.elapsed_seconds > 0
        assert stats.tokens_per_second > 0

    def test_a_local_run_costs_nothing(self):
        assert LocalStats().estimated_cost() == 0.0

    def test_wall_clock_is_not_summed_across_chunks(self):
        """Two requests that ran at the same time took as long as the slower
        one. Adding them would report a machine twice as fast as it is."""
        merged = LocalStats(elapsed_seconds=5.0)
        merged.merge(LocalStats(elapsed_seconds=5.0))

        assert merged.elapsed_seconds == 5.0

    def test_subclass_counters_merge_without_being_listed_twice(self):
        first = LocalStats(retried=1, over_length=1)
        first.merge(LocalStats(retried=2, over_length=3))

        assert (first.retried, first.over_length) == (3, 4)

    def test_the_rejection_summary_says_what_to_fix(self):
        stats = LocalStats(over_length=4, wrong_echo=1)

        assert "4 too long" in stats.rejection_summary()
        assert "1 wrong lemma echoed" in stats.rejection_summary()


class TestTheDefaultTransport:
    """The doubles above are only worth anything if they are substitutable for
    the real thing. They were not: `_post_json` took `timeout` keyword-only
    while `_call` passes it positionally, and every test passed anyway because
    every test supplied its own double. The first real request found it."""

    def test_the_real_transport_is_called_the_way_it_is_declared(self):
        import inspect

        from molcajete_prep.glossing.ollama import _post_json

        parameters = list(inspect.signature(_post_json).parameters.values())

        assert [p.name for p in parameters] == ["url", "payload", "timeout"]
        assert all(
            p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD for p in parameters
        ), "the default transport must accept the arguments _call passes positionally"

    def test_a_provider_with_no_transport_uses_the_real_one(self):
        """Nothing is sent — the assertion is that the default is wired at all."""
        from molcajete_prep.glossing.ollama import _post_json

        local = OllamaProvider()

        assert local.transport is None
        assert (local.transport or _post_json) is _post_json


class TestSelection:
    def test_the_provider_is_reached_by_name_and_never_by_import(self):
        """CLAUDE.md rule 4: selectable by config, not by import."""
        built = build_provider(ProviderOptions(name="ollama", model="qwen3:8b"))

        assert built.name == "ollama"
        assert built.model == "qwen3:8b"

    def test_an_unknown_provider_says_what_the_choices_are(self):
        with pytest.raises(ValueError, match="ollama"):
            build_provider(ProviderOptions(name="llamafile"))

    def test_the_cli_knobs_reach_the_provider(self):
        built = build_provider(
            ProviderOptions(name="ollama", chunk_size=5, concurrency=3, retries=2)
        )

        assert (built.chunk_size, built.concurrency, built.retries) == (5, 3, 2)
