"""The gloss provider port, and the contract every implementation answers.

Glossing has two halves that change at different rates. What a gloss *is* —
one to three words, German primary, a mexicanism flag with a region note — is
settled by SPEC §13.1 and does not move. *Who writes it* is an implementation
detail that has already changed once: the Claude batch path was written first
and could not run, so a local model was added behind the same shape.

CLAUDE.md rule 4 puts storage behind interfaces for exactly this reason, and the
same argument applies here. `pipeline.gloss_lexicon` no longer imports a vendor;
it is handed a `GlossProvider` chosen by `--gloss-provider`, and a third one
would be a new module and a line in `build_provider`.

The contract in both directions:

**In** — a `GlossTask`: lemma, part of speech, the book's own example sentence
for sense context, and whatever Wiktionary managed. Identical for every provider,
so a trial comparing two providers is comparing the models and not the prompts.

**Out** — a `Gloss` per identity, plus a `GlossStats`. `Gloss` holds the
invariants itself (`normalize_gloss` for the word limit, `__post_init__` for
mexicanism implying a region note), so a provider cannot return something the
bundle validator would reject, however badly the model behaved.

A provider never raises for a lemma it could not gloss. A missing gloss is a
number in the report; a crash is a build that has to start over.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, fields
from typing import Any, ClassVar, Protocol

from molcajete_prep.glossing.models import Gloss

Identity = tuple[str, str]

CLAUDE = "claude"
OLLAMA = "ollama"
PROVIDER_NAMES = (CLAUDE, OLLAMA)


@dataclass(frozen=True)
class GlossTask:
    """One lemma to gloss, with whatever context we have for it.

    `example_es` is the sentence the lemma occurs in *in this book*, and it is
    the field that earns the pass its quality: it settles which sense of `banco`
    or `pluma` is being asked about. The Wiktionary fields are raw dictionary
    text, passed as context whether or not it was good enough to use verbatim.
    """

    lemma: str
    pos: str
    example_es: str | None = None
    wiktionary_en: str | None = None
    wiktionary_de: str | None = None
    region_hint: str | None = None

    @property
    def identity(self) -> Identity:
        return (self.lemma, self.pos)

    def as_prompt_item(self) -> dict[str, str | None]:
        return {
            "lemma": self.lemma,
            "pos": self.pos,
            "example_es": self.example_es,
            "wiktionary_en": self.wiktionary_en,
            "wiktionary_de": self.wiktionary_de,
            "region_hint": self.region_hint,
        }


@dataclass
class GlossStats:
    """What a pass returned and how cleanly, in terms every provider shares.

    Subclasses add what only they can measure — cache tokens and dollars for a
    remote batch, retries and tokens per second for a local model — and say so
    by overriding `report_lines`. The report prints the shared block and then
    asks the stats for the rest, which keeps `report.py` from having to know
    which provider ran.
    """

    requests: int = 0
    succeeded: int = 0
    errored: int = 0

    glosses_returned: int = 0
    truncated: int = 0
    unmatched: int = 0
    missing: int = 0
    not_spanish: int = 0
    mexicanisms: int = 0

    input_tokens: int = 0
    output_tokens: int = 0

    errors: list[str] = field(default_factory=list)

    # Fields a merge must not simply add up. Wall-clock time under concurrency
    # is the obvious one: two chunks that ran at the same time took as long as
    # the slower of them, not as long as both. ClassVar, so it stays a rule
    # about the fields rather than becoming one of them.
    NON_ADDITIVE: ClassVar[tuple[str, ...]] = ()

    def merge(self, other: GlossStats) -> None:
        """Fold another pass's counts into this one.

        Walks the dataclass fields rather than a hand-written list so that a
        subclass's own counters merge without restating them here — the previous
        hand-written tuple was already one field out of date twice.
        """
        for spec in fields(self):
            if spec.name in self.NON_ADDITIVE:
                continue
            mine = getattr(self, spec.name, None)
            theirs = getattr(other, spec.name, None)
            if isinstance(mine, list) and isinstance(theirs, list):
                mine.extend(theirs)
            elif isinstance(mine, (int, float)) and isinstance(theirs, (int, float)):
                setattr(self, spec.name, mine + theirs)

    def estimated_cost(self) -> float:
        """Dollars, for providers that bill. Local models are free, and say so."""
        return 0.0

    def report_lines(self) -> list[str]:
        """Provider-specific lines for the build report. Indented by the caller."""
        return []

    def trial_line(self) -> str:
        """One line for the trial header: what this arm cost, in its own terms."""
        return f"${self.estimated_cost():.2f}"


class GlossProvider(Protocol):
    """Whatever can turn `GlossTask`s into `Gloss`es.

    `name` and `model` are not decoration: they are two thirds of the cache key.
    A gloss written by a 12B local model and one written by Sonnet are different
    claims about the same word, and the cache must be able to hold both without
    either standing in for the other.
    """

    name: str
    model: str

    def gloss(
        self,
        tasks: Sequence[GlossTask],
        *,
        on_status: Any = None,
    ) -> tuple[dict[Identity, Gloss], GlossStats]:
        """Gloss every task. Returns what it managed, and never raises per-lemma."""
        ...


@dataclass(frozen=True)
class ProviderOptions:
    """The provider knobs the CLI exposes, before a provider exists to hold them.

    One flat record rather than a union of per-provider option types: argparse
    produces a flat namespace, most of these are meaningful to more than one
    provider, and `build_provider` is the single place that knows which
    implementation reads which field.
    """

    name: str = CLAUDE

    # None means "whatever that provider considers its default model", which
    # keeps the model names out of the CLI defaults where they would drift.
    model: str | None = None

    # Locally these matter; against a batch API they do not. `chunk_size` is the
    # sharpest difference between the two — see `ollama.DEFAULT_CHUNK_SIZE`.
    chunk_size: int | None = None
    concurrency: int = 2
    retries: int = 1
    timeout_seconds: float = 120.0


def build_provider(
    options: ProviderOptions = ProviderOptions(),
    *,
    client: Any = None,
) -> GlossProvider:
    """Resolve a provider name to an implementation.

    Imports are deferred so that a local run never imports `anthropic` and an
    API run never reaches for the Ollama module. Selection is by name, from a
    flag — no caller of `gloss_lexicon` imports a provider directly, which is
    the whole point of the port.
    """
    if options.name == CLAUDE:
        from molcajete_prep.glossing.claude import ClaudeProvider

        return ClaudeProvider.from_options(options, client=client)

    if options.name == OLLAMA:
        from molcajete_prep.glossing.ollama import OllamaProvider

        return OllamaProvider.from_options(options, transport=client)

    raise ValueError(
        f"unknown gloss provider {options.name!r}; expected one of "
        f"{', '.join(PROVIDER_NAMES)}"
    )
