"""Tests for the 200-lemma trial.

The trial's job is to be cheap and to touch nothing: it must not write a bundle,
and it must not seed the shared gloss cache with answers produced at
experimental settings. Both are asserted here, because both would be silent.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from molcajete_prep.glossing.cache import GlossCache
from molcajete_prep.glossing.claude import BatchStats, GlossTask, ModelSettings
from molcajete_prep.glossing.models import Gloss
from molcajete_prep.lexicon import build_lexicon
from molcajete_prep.nlp import Token
from molcajete_prep.trial import (
    ARM_A,
    ARM_B,
    Trial,
    TrialArm,
    build_tasks,
    render_trial,
    select_sample,
)

BUILT_AT = datetime(2026, 8, 17, 10, 0, 0)


def word(lemma, pos="NOUN", sentence=0):
    return Token(
        surface=lemma, lemma=lemma, pos=pos, is_whitespace=False, sentence=sentence
    )


@pytest.fixture
def lexicon():
    """A book with a common word, a rare one, and a lemmatizer invention."""
    paragraph = (
        [word("casa")] * 20
        + [word("sargento")] * 2
        + [word("acaeceír", "VERB")]
        + [word(f"palabra{i:03d}") for i in range(40)]
    )
    return build_lexicon([[paragraph]])


class TestSampleSelection:
    def test_the_sample_is_capped_at_the_size_asked_for(self, lexicon):
        assert len(select_sample(lexicon, size=20)) <= 20

    def test_the_commonest_words_are_always_included(self, lexicon):
        """They carry the most senses, so a wrong sense hurts most there."""
        keys = select_sample(lexicon, size=20)
        lemmas = {lexicon.records[key].lemma for key in keys}

        assert "casa" in lemmas

    def test_lemmatizer_inventions_are_deliberately_sampled(self, lexicon):
        """The trial is the only measurement of how many the model refuses."""
        keys = select_sample(lexicon, size=20)
        lemmas = {lexicon.records[key].lemma for key in keys}

        assert "acaeceír" in lemmas

    def test_the_sample_is_deterministic(self, lexicon):
        assert select_sample(lexicon, size=20) == select_sample(lexicon, size=20)

    def test_a_different_seed_draws_differently(self, lexicon):
        assert select_sample(lexicon, size=20, seed=1) != select_sample(
            lexicon, size=20, seed=2
        )

    def test_no_lemma_is_sampled_twice(self, lexicon):
        keys = select_sample(lexicon, size=40)

        assert len(keys) == len(set(keys))

    def test_asking_for_more_than_the_book_holds_is_not_an_error(self, lexicon):
        keys = select_sample(lexicon, size=10_000)

        assert len(keys) == len(lexicon.records)


class TestTaskConstruction:
    def test_each_task_carries_the_books_own_sentence(self, lexicon):
        tokens = [[[word("el", "DET"), word("casa")]]]
        small = build_lexicon(tokens)
        keys = list(small.records)

        tasks = build_tasks(small, tokens, keys)

        assert any(task.example_es for task in tasks)

    def test_wiktionary_answers_travel_as_context(self, lexicon):
        from molcajete_prep.glossing.pipeline import GlossingResult

        tokens = [[[word("casa")]]]
        small = build_lexicon(tokens)
        key = next(iter(small.records))
        known = GlossingResult(
            glosses={key: Gloss(lemma="casa", pos="NOUN", en="house", de="das Haus")}
        )

        tasks = build_tasks(small, tokens, [key], known)

        assert tasks[0].wiktionary_en == "house"
        assert tasks[0].wiktionary_de == "das Haus"


def arm(name, glosses, **stats):
    return TrialArm(
        settings=ModelSettings(name=name),
        glosses=glosses,
        stats=BatchStats(requests=1, succeeded=1, **stats),
    )


class TestRendering:
    def _trial(self):
        tasks = [
            GlossTask("casa", "NOUN", example_es="La casa era blanca."),
            GlossTask("acaeceír", "VERB"),
        ]
        low = {
            ("casa", "NOUN"): Gloss(lemma="casa", pos="NOUN", de="das Haus", en="house"),
            ("acaeceír", "VERB"): Gloss(
                lemma="acaeceír", pos="VERB", not_spanish=True, corrected_lemma="acaecer"
            ),
        }
        medium = dict(low)
        medium[("casa", "NOUN")] = Gloss(
            lemma="casa", pos="NOUN", de="das Haus, das Heim", en="house, home"
        )
        return Trial(tasks=tasks, arms=[arm("low", low), arm("medium", medium)])

    def test_every_sampled_lemma_appears_in_the_primary_listing(self):
        report = render_trial(self._trial(), built_at=BUILT_AT)

        assert "casa" in report and "acaeceír" in report

    def test_a_rejected_lemma_shows_its_correction(self):
        report = render_trial(self._trial(), built_at=BUILT_AT)

        assert "NOT SPANISH -> acaecer" in report

    def test_the_example_sentence_is_shown_beside_the_gloss(self):
        """It is what a reviewer needs to judge whether the sense is right."""
        report = render_trial(self._trial(), built_at=BUILT_AT)

        assert "La casa era blanca." in report

    def test_only_disagreements_are_listed_for_the_second_arm(self):
        """The comparison exists to answer one question — is thinking worth
        paying for — and 400 lines of agreement does not answer it."""
        report = render_trial(self._trial(), built_at=BUILT_AT)

        section = report.split("WHERE ARM medium DISAGREES")[1]
        assert "casa" in section
        assert "acaeceír" not in section
        assert "1 of 2" in report

    def test_two_identical_arms_report_no_disagreement(self):
        tasks = [GlossTask("casa", "NOUN")]
        same = {("casa", "NOUN"): Gloss(lemma="casa", pos="NOUN", de="das Haus")}
        trial = Trial(tasks=tasks, arms=[arm("low", same), arm("medium", dict(same))])

        report = render_trial(trial, built_at=BUILT_AT)

        assert "no disagreements" in report

    def test_a_single_arm_trial_renders_without_a_comparison(self):
        tasks = [GlossTask("casa", "NOUN")]
        trial = Trial(
            tasks=tasks,
            arms=[arm("low", {("casa", "NOUN"): Gloss(lemma="casa", pos="NOUN", de="x")})],
        )

        report = render_trial(trial, built_at=BUILT_AT)

        assert "DISAGREES" not in report

    def test_a_silent_cache_failure_is_called_out(self):
        """The only symptom of a system prompt trimmed under 1024 tokens."""
        trial = Trial(
            tasks=[GlossTask("casa", "NOUN")],
            arms=[
                TrialArm(
                    settings=ARM_A,
                    glosses={},
                    stats=BatchStats(requests=8, succeeded=8, cache_read_tokens=0),
                )
            ],
        )

        report = render_trial(trial, built_at=BUILT_AT)

        assert "1024" in report

    def test_the_cost_is_stated_up_front(self):
        report = render_trial(self._trial(), built_at=BUILT_AT)

        assert "Estimated cost:" in report.split("ARM")[0]


class TestIsolation:
    def test_the_two_arms_are_the_production_setting_and_a_check_on_it(self):
        assert (ARM_A.effort, ARM_A.thinking) == ("low", False)
        assert (ARM_B.effort, ARM_B.thinking) == ("medium", True)

    def test_the_trial_never_writes_to_the_shared_cache(self, lexicon, monkeypatch):
        """A sample glossed at experimental settings must not seed the store
        every later book reads from."""
        from molcajete_prep import trial as trial_module

        opened: list[object] = []
        real = GlossCache.in_memory

        def spy():
            store = real()
            opened.append(store)
            return store

        monkeypatch.setattr(GlossCache, "in_memory", staticmethod(spy))
        monkeypatch.setattr(
            trial_module, "gloss_lexicon", lambda *a, **k: _EmptyGlossing()
        )
        monkeypatch.setattr(trial_module, "run_claude", lambda *a, **k: ({}, BatchStats()))

        trial_module.run_trial(lexicon, [[[word("casa")]]], size=4)

        assert opened, "the trial should gloss through a throwaway cache"


class _EmptyGlossing:
    glosses: dict = {}
