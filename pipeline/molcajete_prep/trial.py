"""The 200-lemma trial: check gloss quality before paying for a whole book.

Runs the Claude pass twice over the same small sample, at two settings, and
writes both answers out side by side. Nothing it produces reaches a bundle, and
nothing reaches the shared cache — a sample glossed at experimental settings
must not seed the store every later book reads from.

The sample is stratified rather than uniform. Two hundred lemmas drawn at random
from a nine-thousand-lemma lexicon would be almost entirely rare words, and rare
words are the easy case: they have one sense. The words that expose a bad prompt
are the common ones with many senses, the mexicanisms, and the strings the
lemmatizer invented.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from molcajete_prep.classify import LemmaKey
from molcajete_prep.glossing.cache import GlossCache
from molcajete_prep.glossing.claude import BatchStats, GlossTask, ModelSettings
from molcajete_prep.glossing.claude import run as run_claude
from molcajete_prep.glossing.models import Gloss
from molcajete_prep.glossing.pipeline import GlossingOptions, GlossingResult, gloss_lexicon
from molcajete_prep.lexicon import Lexicon, example_sentence
from molcajete_prep.nlp import Token

Identity = tuple[str, str]

TRIAL_SEED = 20260817

# The production setting, and the one worth checking it against. Thinking costs
# output tokens, which are the expensive half of a batch, so the question is
# whether it buys anything.
ARM_A = ModelSettings(name="low", effort="low", thinking=False)
ARM_B = ModelSettings(name="medium", effort="medium", thinking=True)


@dataclass
class TrialArm:
    settings: ModelSettings
    glosses: dict[Identity, Gloss] = field(default_factory=dict)
    stats: BatchStats = field(default_factory=BatchStats)


@dataclass
class Trial:
    tasks: list[GlossTask]
    arms: list[TrialArm]

    @property
    def total_cost(self) -> float:
        return sum(arm.stats.estimated_cost() for arm in self.arms)


def select_sample(
    lexicon: Lexicon,
    *,
    size: int = 200,
    seed: int = TRIAL_SEED,
) -> list[LemmaKey]:
    """Pick lemmas that will actually stress the prompt.

    Four populations in equal parts. The commonest words carry the most senses
    and are where a wrong sense hurts most. The zipf-0.00 strings are what the
    lemmatizer invented, and the trial is the only measurement of how many the
    model correctly refuses. A uniform draw covers the ordinary middle. Rare
    real words are the long tail a book is mostly made of.
    """
    rng = random.Random(seed)
    records = lexicon.records
    quarter = size // 4

    by_count = sorted(records, key=lambda key: (-records[key].book_count, key))
    chosen: list[LemmaKey] = list(by_count[:quarter])

    invented = sorted(key for key in records if records[key].zipf == 0.0)
    chosen += (
        invented[:quarter] if len(invented) <= quarter else rng.sample(invented, quarter)
    )

    rare = sorted(
        key for key in records if records[key].zipf > 0 and records[key].book_count <= 2
    )
    pool = [key for key in rare if key not in set(chosen)]
    chosen += rng.sample(pool, min(quarter, len(pool)))

    remaining = sorted(set(records) - set(chosen))
    chosen += rng.sample(remaining, min(size - len(chosen), len(remaining)))

    return sorted(set(chosen), key=lambda key: (-records[key].book_count, key))


def build_tasks(
    lexicon: Lexicon,
    chapters: Sequence[Sequence[Sequence[Token]]],
    keys: Sequence[LemmaKey],
    wiktionary: GlossingResult | None = None,
) -> list[GlossTask]:
    """Turn chosen lemmas into requests, with the same context a real run gives."""
    tasks: list[GlossTask] = []
    for key in keys:
        record = lexicon.records[key]
        found = example_sentence(record, chapters)
        known = wiktionary.glosses.get(key) if wiktionary else None
        tasks.append(
            GlossTask(
                lemma=record.lemma,
                pos=record.pos,
                example_es=found[0] if found else None,
                wiktionary_en=known.en if known else None,
                wiktionary_de=known.de if known else None,
            )
        )
    return tasks


def run_trial(
    lexicon: Lexicon,
    chapters: Sequence[Sequence[Sequence[Token]]],
    *,
    size: int = 200,
    arms: Sequence[ModelSettings] = (ARM_A, ARM_B),
    extract_dir: Path | None = None,
    client: Any = None,
    seed: int = TRIAL_SEED,
    on_status: Any = None,
) -> Trial:
    """Gloss a sample at each setting. Touches no shared state."""
    keys = select_sample(lexicon, size=size, seed=seed)

    # Wiktionary context, resolved through a throwaway cache so the real one is
    # neither read nor written.
    with GlossCache.in_memory() as scratch:
        wiktionary = gloss_lexicon(
            lexicon,
            chapters,
            book_id="trial",
            options=GlossingOptions(use_claude=False, extract_dir=extract_dir),
            cache=scratch,
            now=datetime.now(),
        )

    tasks = build_tasks(lexicon, chapters, keys, wiktionary)

    results = []
    for settings in arms:
        glosses, stats = run_claude(
            tasks, settings, client=client, on_status=on_status
        )
        results.append(TrialArm(settings=settings, glosses=glosses, stats=stats))

    return Trial(tasks=tasks, arms=results)


def _line(gloss: Gloss | None) -> str:
    if gloss is None:
        return "(no answer)"
    if gloss.not_spanish:
        correction = f" -> {gloss.corrected_lemma}" if gloss.corrected_lemma else ""
        return f"NOT SPANISH{correction}"
    mark = " *" if gloss.mexicanism else ""
    note = f"  [{gloss.region_note}]" if gloss.region_note else ""
    return f"DE {gloss.de or '—':<28} EN {gloss.en or '—'}{mark}{note}"


def render_trial(trial: Trial, *, built_at: datetime) -> str:
    """A page to read, not a dump to scroll.

    The full first arm is listed because that is the production setting and the
    glosses have to be judged on their own. The second arm appears only where it
    disagrees — that is the part that answers whether thinking is worth paying
    for, and it keeps the review to a page rather than four hundred lines.
    """
    primary, *rest = trial.arms
    lines: list[str] = []

    lines.append("Molcajete gloss trial")
    lines.append(f"Built: {built_at.isoformat(timespec='seconds')}")
    lines.append(f"Lemmas: {len(trial.tasks)}  ·  Arms: {len(trial.arms)}")
    lines.append(f"Estimated cost: ${trial.total_cost:.2f}")
    lines.append("")

    for arm in trial.arms:
        stats = arm.stats
        answered = len(arm.glosses)
        german = sum(1 for g in arm.glosses.values() if g.has_german)
        english = sum(1 for g in arm.glosses.values() if g.has_english)
        lines.append(
            f"ARM {arm.settings.name}"
            f"  (effort {arm.settings.effort}, "
            f"thinking {'adaptive' if arm.settings.thinking else 'off'})"
        )
        lines.append(
            f"  answered {answered}/{len(trial.tasks)}"
            f"  ·  German {german}  ·  English {english}"
            f"  ·  mexicanism {stats.mexicanisms}"
            f"  ·  not Spanish {stats.not_spanish}"
        )
        lines.append(
            f"  cut down {stats.truncated}"
            f"  ·  unanswered {stats.missing}"
            f"  ·  failed requests {stats.errored}"
            f"  ·  output tokens {stats.output_tokens:,}"
            f"  ·  ${stats.estimated_cost():.2f}"
        )
        if not stats.cache_worked:
            lines.append(
                "  !! nothing was served from prompt cache — the instruction "
                "block may have slipped under 1024 tokens"
            )
        lines.append("")

    lines.append(f"ALL {len(trial.tasks)} GLOSSES — arm {primary.settings.name}")
    lines.append("  (* mexicanism)")
    for task in trial.tasks:
        gloss = primary.glosses.get(task.identity)
        lines.append(f"  {task.lemma:<20} {task.pos:<6} {_line(gloss)}")
        if task.example_es:
            lines.append(f"       „{task.example_es[:96]}\"")
    lines.append("")

    for arm in rest:
        disagreements = [
            task
            for task in trial.tasks
            if _line(primary.glosses.get(task.identity)) != _line(arm.glosses.get(task.identity))
        ]
        lines.append(
            f"WHERE ARM {arm.settings.name} DISAGREES WITH ARM "
            f"{primary.settings.name} — {len(disagreements)} of {len(trial.tasks)}"
        )
        if not disagreements:
            lines.append("  (no disagreements: the cheaper arm is doing the same work)")
        for task in disagreements:
            lines.append(f"  {task.lemma:<20} {task.pos}")
            lines.append(f"    {primary.settings.name:<8} {_line(primary.glosses.get(task.identity))}")
            lines.append(f"    {arm.settings.name:<8} {_line(arm.glosses.get(task.identity))}")
        lines.append("")

    return "\n".join(lines) + "\n"
