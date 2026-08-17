"""The 200-lemma trial: check gloss quality before glossing a whole book.

Runs one or more providers over the same small sample and writes the answers out
side by side. Nothing it produces reaches a bundle, and nothing reaches the
shared cache — a sample glossed at experimental settings, or by a model being
auditioned, must not seed the store every later book reads from.

The sample is stratified rather than uniform. Two hundred lemmas drawn at random
from a nine-thousand-lemma lexicon would be almost entirely rare words, and rare
words are the easy case: they have one sense. The words that expose a bad prompt
are the common ones with many senses, the mexicanisms, and the strings the
lemmatizer invented.

**The gold set is the one measurement that is not self-reported.** Everything
else here says how confidently a model answered; a list of words already known to
be Mexican says whether it was right about the flag SPEC §5 teaches from. It is
scored separately, and scored only over the gold lemmas the book actually
contains — recall over an accidental sample of three is a number that means
nothing.
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
from molcajete_prep.glossing.claude import ClaudeProvider, ModelSettings
from molcajete_prep.glossing.models import Gloss
from molcajete_prep.glossing.pipeline import GlossingOptions, GlossingResult, gloss_lexicon
from molcajete_prep.glossing.provider import GlossProvider, GlossStats, GlossTask
from molcajete_prep.lexicon import Lexicon, example_sentence
from molcajete_prep.nlp import Token

Identity = tuple[str, str]

TRIAL_SEED = 20260817

# Enough glosses to judge the register by eye without reading a wall of them.
# The full list follows for anyone who wants it; this is the part to actually
# read.
SAMPLE_SIZE = 30

# The Claude arms: the production setting, and the one worth checking it
# against. Thinking costs output tokens, which are the expensive half of a
# batch, so the question is whether it buys anything.
ARM_A = ModelSettings(name="low", effort="low", thinking=False)
ARM_B = ModelSettings(name="medium", effort="medium", thinking=True)


@dataclass(frozen=True)
class GoldEntry:
    """One lemma known to be Mexican, from the reader's own Anki deck.

    `pos` is optional because the deck records words, not tags. When it is
    absent the entry matches the lemma under any tag, which is the right reading
    of "I know this word is Mexican".
    """

    lemma: str
    pos: str | None = None

    def matches(self, lemma: str, pos: str) -> bool:
        return lemma.lower() == self.lemma.lower() and (self.pos is None or self.pos == pos)


def load_gold(path: str | Path) -> list[GoldEntry]:
    """Read a gold list: one lemma per line, `#` comments, optional tab and tag."""
    entries: list[GoldEntry] = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = [part.strip() for part in line.replace("\t", " ").split(" ") if part.strip()]
        lemma = parts[0].lower()
        pos = parts[1].upper() if len(parts) > 1 else None
        entries.append(GoldEntry(lemma=lemma, pos=pos))
    return entries


@dataclass
class GoldScore:
    """How a run did against the gold set *within this book*.

    Kept honest about its denominator. A gold lemma the book never uses was
    never asked about, so counting it as a miss would make recall a measure of
    the book rather than of the model.
    """

    present: list[LemmaKey] = field(default_factory=list)
    absent: list[str] = field(default_factory=list)
    flagged: list[LemmaKey] = field(default_factory=list)
    missed: list[LemmaKey] = field(default_factory=list)

    @property
    def recall(self) -> float:
        return len(self.flagged) / len(self.present) if self.present else 0.0

    @property
    def is_measurable(self) -> bool:
        """Whether the denominator is large enough for the number to mean much.

        Not a threshold anyone should tune: it exists so the report says "too
        few to measure" instead of printing "0% recall" over a denominator of
        one and letting it be read as a finding.
        """
        return len(self.present) >= 5


@dataclass
class GoldProbe:
    """The gold set asked directly, outside any book.

    The in-book score cannot say anything when the book predates the vocabulary
    — a nineteenth-century novel contains none of a modern Monterrey deck's
    slang, and the intersection came to one word. But the question the gold set
    was written to answer, *does this model know these words are Mexican*, does
    not actually need the book. So it is also asked straight: one request per
    gold lemma, no example sentence, nothing but the word and its tag.

    Deliberately the harder test of the two. With no sentence the model must
    know the word rather than infer the register from context, which is exactly
    the knowledge a 12B model is thinnest on and the thing worth measuring.
    """

    entries: list[GoldEntry] = field(default_factory=list)
    glosses: dict[Identity, Gloss] = field(default_factory=dict)
    stats: GlossStats = field(default_factory=GlossStats)

    def _flag(self, entry: GoldEntry) -> Gloss | None:
        return self.glosses.get((entry.lemma, entry.pos or "NOUN"))

    @property
    def flagged(self) -> list[GoldEntry]:
        return [e for e in self.entries if (g := self._flag(e)) and g.mexicanism]

    @property
    def missed(self) -> list[GoldEntry]:
        return [e for e in self.entries if not ((g := self._flag(e)) and g.mexicanism)]

    @property
    def recall(self) -> float:
        return len(self.flagged) / len(self.entries) if self.entries else 0.0


@dataclass
class TrialArm:
    label: str
    provider: GlossProvider
    glosses: dict[Identity, Gloss] = field(default_factory=dict)
    stats: GlossStats = field(default_factory=GlossStats)
    gold: GoldScore = field(default_factory=GoldScore)
    probe: GoldProbe = field(default_factory=GoldProbe)


@dataclass
class Trial:
    tasks: list[GlossTask]
    arms: list[TrialArm]
    gold_entries: list[GoldEntry] = field(default_factory=list)

    @property
    def total_cost(self) -> float:
        return sum(arm.stats.estimated_cost() for arm in self.arms)


def gold_keys(lexicon: Lexicon, entries: Sequence[GoldEntry]) -> tuple[list[LemmaKey], list[str]]:
    """Split the gold list into what this book contains and what it does not.

    A gold lemma the book never uses cannot be scored — it was never asked
    about — and counting it as a miss would make every recall figure a function
    of the book rather than of the model.
    """
    present: list[LemmaKey] = []
    found_lemmas: set[str] = set()

    for key, record in lexicon.records.items():
        for entry in entries:
            if entry.matches(record.lemma, record.pos):
                present.append(key)
                found_lemmas.add(entry.lemma)
                break

    absent = sorted({e.lemma for e in entries} - found_lemmas)
    return sorted(set(present)), absent


def select_sample(
    lexicon: Lexicon,
    *,
    size: int = 200,
    seed: int = TRIAL_SEED,
    always_include: Sequence[LemmaKey] = (),
) -> list[LemmaKey]:
    """Pick lemmas that will actually stress the prompt.

    Four populations in equal parts. The commonest words carry the most senses
    and are where a wrong sense hurts most. The zipf-0.00 strings are what the
    lemmatizer invented, and the trial is the only measurement of how many the
    model correctly refuses. A uniform draw covers the ordinary middle. Rare
    real words are the long tail a book is mostly made of.

    `always_include` is added *on top of* the size rather than inside it. It
    carries the gold lemmas, and letting them displace the stratified draw would
    trade away the thing the sample was designed to measure to make room for the
    other thing being measured.
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

    chosen += [key for key in always_include if key in records]

    return sorted(set(chosen), key=lambda key: (-records[key].book_count, key))


def build_tasks(
    lexicon: Lexicon,
    chapters: Sequence[Sequence[Sequence[Token]]],
    keys: Sequence[LemmaKey],
    wiktionary: GlossingResult | None = None,
) -> list[GlossTask]:
    """Turn chosen lemmas into requests, with the same context a real run gives.

    The context comes from `GlossingResult.context` — the raw Wiktionary text a
    build would send — rather than from the applied glosses. Under the default
    `--de-wiktionary context-only` the applied German gloss has been removed on
    purpose, and rebuilding the prompt from it would send the model less than
    production does and then judge it on the result.
    """
    tasks: list[GlossTask] = []
    for key in keys:
        record = lexicon.records[key]
        identity = (record.lemma, record.pos)

        if wiktionary and identity in wiktionary.context:
            tasks.append(wiktionary.context[identity])
            continue

        found = example_sentence(record, chapters)
        tasks.append(
            GlossTask(
                lemma=record.lemma,
                pos=record.pos,
                example_es=found[0] if found else None,
            )
        )
    return tasks


def score_gold(
    glosses: dict[Identity, Gloss],
    lexicon: Lexicon,
    present: Sequence[LemmaKey],
    absent: Sequence[str],
) -> GoldScore:
    """Recall over the gold lemmas this book contains, and nothing else."""
    score = GoldScore(present=list(present), absent=list(absent))
    for key in present:
        record = lexicon.records[key]
        gloss = glosses.get((record.lemma, record.pos))
        if gloss is not None and gloss.mexicanism:
            score.flagged.append(key)
        else:
            score.missed.append(key)
    return score


def probe_gold(
    provider: GlossProvider,
    entries: Sequence[GoldEntry],
    *,
    on_status: Any = None,
) -> GoldProbe:
    """Ask the model about the gold lemmas themselves, with no book around them."""
    if not entries:
        return GoldProbe()

    tasks = [GlossTask(lemma=e.lemma, pos=e.pos or "NOUN") for e in entries]
    glosses, stats = provider.gloss(tasks, on_status=on_status)
    return GoldProbe(entries=list(entries), glosses=glosses, stats=stats)


def run_trial(
    lexicon: Lexicon,
    chapters: Sequence[Sequence[Sequence[Token]]],
    *,
    size: int = 200,
    providers: Sequence[tuple[str, GlossProvider]] = (),
    extract_dir: Path | None = None,
    gold: Sequence[GoldEntry] = (),
    seed: int = TRIAL_SEED,
    on_status: Any = None,
) -> Trial:
    """Gloss a sample with each provider. Touches no shared state."""
    present, absent = gold_keys(lexicon, gold) if gold else ([], [])
    keys = select_sample(lexicon, size=size, seed=seed, always_include=present)

    # Wiktionary context, resolved through a throwaway cache so the real one is
    # neither read nor written.
    with GlossCache.in_memory() as scratch:
        wiktionary = gloss_lexicon(
            lexicon,
            chapters,
            book_id="trial",
            options=GlossingOptions(use_model=False, extract_dir=extract_dir),
            cache=scratch,
            now=datetime.now(),
        )

    tasks = build_tasks(lexicon, chapters, keys, wiktionary)

    arms = []
    for label, provider in providers:
        glosses, stats = provider.gloss(tasks, on_status=on_status)
        arms.append(
            TrialArm(
                label=label,
                provider=provider,
                glosses=glosses,
                stats=stats,
                gold=score_gold(glosses, lexicon, present, absent),
                probe=probe_gold(provider, gold, on_status=on_status),
            )
        )

    return Trial(tasks=tasks, arms=arms, gold_entries=list(gold))


def claude_arms(*settings: ModelSettings) -> list[tuple[str, GlossProvider]]:
    return [(one.name, ClaudeProvider(settings=one)) for one in settings]


def _line(gloss: Gloss | None) -> str:
    if gloss is None:
        return "(no answer)"
    if gloss.not_spanish:
        correction = f" -> {gloss.corrected_lemma}" if gloss.corrected_lemma else ""
        return f"NOT SPANISH{correction}"
    mark = " *" if gloss.mexicanism else ""
    note = f"  [{gloss.region_note}]" if gloss.region_note else ""
    return f"DE {gloss.de or '—':<28} EN {gloss.en or '—'}{mark}{note}"


def _sample(tasks: Sequence[GlossTask], *, seed: int = TRIAL_SEED) -> list[GlossTask]:
    """Thirty tasks worth reading, spread across the sample's own strata."""
    if len(tasks) <= SAMPLE_SIZE:
        return list(tasks)
    rng = random.Random(seed)
    third = SAMPLE_SIZE // 3
    head = list(tasks[:third])
    rest = [task for task in tasks[third:]]
    return head + rng.sample(rest, min(SAMPLE_SIZE - len(head), len(rest)))


def _gold_lines(arm: TrialArm, lexicon: Lexicon | None) -> list[str]:
    """Recall against the gold set, with the misses named.

    The misses are listed rather than counted because the count says how good
    the model is and the list says what it is bad at — whether it missed rural
    nineteenth-century vocabulary or missed `platicar`.
    """
    score, probe = arm.gold, arm.probe
    if not score.present and not score.absent and not probe.entries:
        return []

    lines: list[str] = []

    if score.is_measurable:
        lines.append(
            f"  gold set, in this book: {len(score.flagged)}/{len(score.present)} "
            f"flagged ({score.recall:.0%} recall)"
        )
        if score.missed and lexicon is not None:
            names = sorted(lexicon.records[key].lemma for key in score.missed)
            lines.append(f"    not flagged: {', '.join(names)}")
    else:
        # Printing "0% recall" over a denominator of one invites it to be read
        # as a finding about the model. It is a finding about the book.
        lines.append(
            f"  gold set, in this book: only {len(score.present)} of "
            f"{len(score.present) + len(score.absent)} gold lemmas occur here — "
            "too few to measure recall from"
        )

    if score.absent:
        lines.append(f"    absent from this book: {', '.join(score.absent)}")

    if probe.entries:
        lines.append(
            f"  gold set, asked directly: {len(probe.flagged)}/{len(probe.entries)} "
            f"flagged ({probe.recall:.0%} recall, no example sentence)"
        )
        if probe.missed:
            lines.append(
                "    not flagged: "
                + ", ".join(f"{e.lemma}" for e in probe.missed)
            )
        wrong_gloss = [
            e for e in probe.entries
            if (g := probe.glosses.get((e.lemma, e.pos or "NOUN"))) and not g.has_german
        ]
        if wrong_gloss:
            lines.append(
                "    no German gloss at all: "
                + ", ".join(e.lemma for e in wrong_gloss)
            )
    return lines


def render_trial(trial: Trial, *, built_at: datetime, lexicon: Lexicon | None = None) -> str:
    """A page to read, not a dump to scroll."""
    primary, *rest = trial.arms
    lines: list[str] = []

    lines.append("Molcajete gloss trial")
    lines.append(f"Built: {built_at.isoformat(timespec='seconds')}")
    lines.append(f"Lemmas: {len(trial.tasks)}  ·  Arms: {len(trial.arms)}")
    # Still stated for a local run, where it reads $0.00. That is the number the
    # whole exercise was about.
    lines.append(f"Estimated cost: ${trial.total_cost:.2f}")
    lines.append("")

    for arm in trial.arms:
        stats = arm.stats
        answered = len(arm.glosses)
        german = sum(1 for g in arm.glosses.values() if g.has_german)
        english = sum(1 for g in arm.glosses.values() if g.has_english)
        lines.append(f"ARM {arm.label}  ({arm.provider.describe()})")
        lines.append(
            f"  answered {answered}/{len(trial.tasks)}"
            f"  ·  German {german}"
            f" ({german / len(trial.tasks):.0%})"
            f"  ·  English {english}"
            f"  ·  mexicanism {stats.mexicanisms}"
            f"  ·  not Spanish {stats.not_spanish}"
        )
        lines.append(
            f"  cut down {stats.truncated}"
            f"  ·  unanswered {stats.missing}"
            f"  ·  failed requests {stats.errored}"
            f"  ·  output tokens {stats.output_tokens:,}"
            f"  ·  {stats.trial_line()}"
        )
        for line in stats.report_lines():
            lines.append(f"  {line}")
        lines.extend(_gold_lines(arm, lexicon))
        lines.append("")

    lines.append(f"SAMPLE OF {SAMPLE_SIZE} GLOSSES — arm {primary.label}")
    lines.append("  (* mexicanism)")
    for task in _sample(trial.tasks):
        lines.append(f"  {task.lemma:<20} {task.pos:<6} {_line(primary.glosses.get(task.identity))}")
    lines.append("")

    if primary.probe.entries:
        lines.append(f"GOLD SET ASKED DIRECTLY — arm {primary.label}")
        lines.append("  (* flagged as a mexicanism, which is the correct answer here)")
        for entry in primary.probe.entries:
            gloss = primary.probe.glosses.get((entry.lemma, entry.pos or "NOUN"))
            mark = "*" if gloss and gloss.mexicanism else " "
            lines.append(f"  {mark} {entry.lemma:<14} {entry.pos or '':<6} {_line(gloss)}")
        lines.append("")

    lines.append(f"ALL {len(trial.tasks)} GLOSSES — arm {primary.label}")
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
            f"WHERE ARM {arm.label} DISAGREES WITH ARM "
            f"{primary.label} — {len(disagreements)} of {len(trial.tasks)}"
        )
        if not disagreements:
            lines.append("  (no disagreements: the cheaper arm is doing the same work)")
        for task in disagreements:
            lines.append(f"  {task.lemma:<20} {task.pos}")
            lines.append(f"    {primary.label:<8} {_line(primary.glosses.get(task.identity))}")
            lines.append(f"    {arm.label:<8} {_line(arm.glosses.get(task.identity))}")
        lines.append("")

    return "\n".join(lines) + "\n"
