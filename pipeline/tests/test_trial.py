"""Tests for the 200-lemma trial.

The trial's job is to be cheap and to touch nothing: it must not write a bundle,
and it must not seed the shared gloss cache with answers produced at
experimental settings. Both are asserted here, because both would be silent.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from molcajete_prep.glossing.cache import GlossCache
from molcajete_prep.glossing.claude import BatchStats, ClaudeProvider, GlossTask, ModelSettings
from molcajete_prep.glossing.models import Gloss
from molcajete_prep.lexicon import build_lexicon
from molcajete_prep.nlp import Token
from molcajete_prep.trial import (
    ARM_A,
    ARM_B,
    GoldEntry,
    GoldProbe,
    GoldScore,
    Trial,
    TrialArm,
    build_tasks,
    gold_keys,
    load_gold,
    render_trial,
    score_gold,
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
        """The trial must send the prompt a real build would send.

        The context is taken from the *raw* Wiktionary text a build passes
        along, not from the applied glosses: under the default
        `--de-wiktionary context-only` the German has deliberately been stripped
        out of the applied gloss, and rebuilding the prompt from it would send
        the model less than production does and then judge the answer."""
        from molcajete_prep.glossing.pipeline import GlossingResult

        tokens = [[[word("casa")]]]
        small = build_lexicon(tokens)
        key = next(iter(small.records))
        known = GlossingResult(
            # No German on the applied gloss — context-only removed it — but
            # the raw German Wiktionary text still travels.
            glosses={key: Gloss(lemma="casa", pos="NOUN", en="house")},
            context={
                ("casa", "NOUN"): GlossTask(
                    lemma="casa",
                    pos="NOUN",
                    wiktionary_en="house",
                    wiktionary_de="das Haus",
                )
            },
        )

        tasks = build_tasks(small, tokens, [key], known)

        assert tasks[0].wiktionary_en == "house"
        assert tasks[0].wiktionary_de == "das Haus"


def arm(name, glosses, **stats):
    return TrialArm(
        label=name,
        provider=ClaudeProvider(settings=ModelSettings(name=name)),
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
                    label="low",
                    provider=ClaudeProvider(settings=ARM_A),
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

        trial_module.run_trial(
            lexicon,
            [[[word("casa")]]],
            size=4,
            providers=[("fake", _SilentProvider())],
        )

        assert opened, "the trial should gloss through a throwaway cache"


class TestTheGoldSet:
    """The one measurement in the trial that is not self-reported.

    Everything else says how confidently a model answered. A list of words
    already known to be Mexican says whether it was right about the flag SPEC §5
    teaches from.
    """

    @pytest.fixture
    def gold_lexicon(self):
        return build_lexicon(
            [[[word("chido", "ADJ"), word("platicar", "VERB"), word("casa")]]]
        )

    def test_a_gold_list_is_read_with_comments_and_blank_lines_ignored(self, tmp_path):
        path = tmp_path / "gold.txt"
        path.write_text("# from the Monterrey deck\n\nchido\nplaticar\n", encoding="utf-8")

        entries = load_gold(path)

        assert [e.lemma for e in entries] == ["chido", "platicar"]
        assert entries[0].pos is None

    def test_a_gold_entry_may_pin_a_part_of_speech(self, tmp_path):
        path = tmp_path / "gold.txt"
        path.write_text("padre\tADJ\n", encoding="utf-8")

        entry = load_gold(path)[0]

        assert (entry.lemma, entry.pos) == ("padre", "ADJ")
        assert entry.matches("padre", "ADJ") is True
        assert entry.matches("padre", "NOUN") is False

    def test_a_gold_lemma_without_a_tag_matches_any_tag(self):
        assert GoldEntry(lemma="padre").matches("padre", "NOUN") is True

    def test_only_the_gold_lemmas_in_the_book_are_scored(self, gold_lexicon):
        """Recall over an accidental sample of three means nothing, and a word
        the book never uses was never asked about."""
        entries = [GoldEntry("chido"), GoldEntry("platicar"), GoldEntry("popote")]

        present, absent = gold_keys(gold_lexicon, entries)

        assert len(present) == 2
        assert absent == ["popote"]

    def test_recall_counts_flags_over_the_lemmas_actually_present(self, gold_lexicon):
        present, absent = gold_keys(gold_lexicon, [GoldEntry("chido"), GoldEntry("platicar")])
        glosses = {
            ("chido", "ADJ"): Gloss(lemma="chido", pos="ADJ", de="cool", mexicanism=True),
            ("platicar", "VERB"): Gloss(lemma="platicar", pos="VERB", de="plaudern"),
        }

        score = score_gold(glosses, gold_lexicon, present, absent)

        assert score.recall == 0.5
        assert len(score.flagged) == 1
        assert len(score.missed) == 1

    def test_a_lemma_the_model_never_answered_counts_as_missed(self, gold_lexicon):
        present, absent = gold_keys(gold_lexicon, [GoldEntry("chido")])

        score = score_gold({}, gold_lexicon, present, absent)

        assert score.recall == 0.0
        assert len(score.missed) == 1

    def test_an_empty_gold_set_scores_zero_without_dividing_by_it(self):
        assert GoldScore().recall == 0.0

    def test_gold_lemmas_are_added_to_the_sample_rather_than_displacing_it(
        self, gold_lexicon
    ):
        """Letting them crowd out the stratified draw would trade away the thing
        the sample was designed to measure."""
        present, _ = gold_keys(gold_lexicon, [GoldEntry("chido")])

        without = select_sample(gold_lexicon, size=2)
        with_gold = select_sample(gold_lexicon, size=2, always_include=present)

        assert set(without) <= set(with_gold)
        assert set(present) <= set(with_gold)

    def _arm(self, lexicon, entries, glosses=None, probe=None):
        present, absent = gold_keys(lexicon, entries)
        return TrialArm(
            label="local",
            provider=_SilentProvider(),
            glosses=glosses or {},
            stats=BatchStats(),
            gold=score_gold(glosses or {}, lexicon, present, absent),
            probe=probe or GoldProbe(),
        )

    def _render(self, lexicon, arm):
        return render_trial(
            Trial(tasks=[GlossTask("chido", "ADJ")], arms=[arm]),
            built_at=BUILT_AT,
            lexicon=lexicon,
        )

    def test_the_misses_are_named_in_the_report(self, gold_lexicon):
        """The count says how good the model is; the list says what it is bad at."""
        wide = build_lexicon(
            [[[word(lemma, "ADJ") for lemma in
               ("chido", "padre", "naco", "fresa", "gacho", "chafa")]]]
        )
        entries = [GoldEntry(lemma, "ADJ") for lemma in
                   ("chido", "padre", "naco", "fresa", "gacho", "chafa", "popote")]

        report = self._render(wide, self._arm(wide, entries))

        assert "0/6 flagged" in report
        assert "not flagged: chafa, chido" in report
        assert "absent from this book: popote" in report

    def test_a_denominator_of_one_is_reported_as_unmeasurable(self, gold_lexicon):
        """A nineteenth-century novel contains none of a modern Monterrey deck.
        Printing "0% recall" over one word invites it to be read as a finding
        about the model when it is a finding about the book."""
        entries = [GoldEntry("chido", "ADJ")] + [
            GoldEntry(name) for name in ("popote", "güey", "chela", "elote", "neta")
        ]

        report = self._render(gold_lexicon, self._arm(gold_lexicon, entries))

        assert "too few to measure recall from" in report
        assert "% recall)" not in report.split("asked directly")[0]

    def test_the_direct_probe_scores_the_whole_gold_list(self, gold_lexicon):
        """Which is the point of it: the model's knowledge of these words does
        not depend on whether this particular book uses them."""
        entries = [GoldEntry("chido", "ADJ"), GoldEntry("popote", "NOUN")]
        probe = GoldProbe(
            entries=entries,
            glosses={
                ("chido", "ADJ"): Gloss(
                    lemma="chido", pos="ADJ", de="cool", mexicanism=True
                ),
                ("popote", "NOUN"): Gloss(
                    lemma="popote", pos="NOUN", de="der Strohhalm"
                ),
            },
        )

        report = self._render(gold_lexicon, self._arm(gold_lexicon, entries, probe=probe))

        assert "1/2 flagged (50% recall" in report
        assert "not flagged: popote" in report

    def test_the_probe_recall_does_not_divide_by_an_empty_list(self):
        assert GoldProbe().recall == 0.0

    def test_a_probed_lemma_with_no_gloss_at_all_is_called_out(self, gold_lexicon):
        """Distinct from a wrong mexicanism judgement: the model did not know
        the word, rather than judging its register wrongly."""
        entries = [GoldEntry("apapachar", "VERB")]
        probe = GoldProbe(entries=entries, glosses={})

        report = self._render(gold_lexicon, self._arm(gold_lexicon, entries, probe=probe))

        assert "0/1 flagged" in report


class _EmptyGlossing:
    glosses: dict = {}
    context: dict = {}


class _SilentProvider:
    """A provider that answers nothing, so the test is about the cache alone."""

    name = "fake"
    model = "none"

    def describe(self) -> str:
        return "a provider that answers nothing"

    def gloss(self, tasks, *, on_status=None):
        return {}, BatchStats()
