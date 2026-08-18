"""The Claude fallback: everything Wiktionary could not gloss.

Uses the Message Batches API. This script runs once per book and nobody is
waiting on it, so there is no reason to pay full price for synchronous calls —
batching halves the bill. SPEC §11.2 settles the model: Sonnet 5, because
glossing is not a hard reasoning task and there are thousands of lemmas.

Three decisions worth knowing about:

**Twenty-five lemmas ride in one request.** One request per lemma would multiply
the cached prefix by the lexicon size. Batching them risks answers drifting out
of alignment with questions, which structured outputs solve: every returned
object echoes the lemma and tag it answers for, and results are matched on that
rather than on position.

**The instructions are cached, the lemmas are not.** The system prompt is
identical on every request and carries a one-hour cache breakpoint. Requests
within a batch run concurrently, so the first few pay the write; the rest read.

**Nothing here trusts the model's word count.** JSON Schema cannot express "one
to three words", so the rule is prose in the prompt and enforced again on the way
out. Overlong glosses are cut down and counted, so a quality drift shows up in
the report rather than on a card.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from molcajete_prep.glossing.models import Gloss, GlossSource, normalize_gloss
from molcajete_prep.glossing.prompts import (
    GLOSS_SCHEMA,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    render_batch,
)
from molcajete_prep.glossing.provider import (
    CLAUDE,
    GlossStats,
    GlossTask,
    Identity,
    ProviderOptions,
)

MODEL = "claude-sonnet-5"
LEMMAS_PER_REQUEST = 25

# Sonnet 5 list prices per million tokens, halved for the Batches API. The
# introductory $2/$10 runs through 2026-08-31; after that it is $3/$15, so treat
# any figure derived from these as an estimate and not an invoice.
_BATCH_INPUT_PER_MTOK = 1.00
_BATCH_OUTPUT_PER_MTOK = 5.00
_CACHE_WRITE_MULTIPLIER = 1.25
_CACHE_READ_MULTIPLIER = 0.10


@dataclass(frozen=True)
class ModelSettings:
    """One arm of the trial, or the production setting.

    Thinking is off and effort is low by default. Glossing is recall, not
    reasoning, and on Sonnet 5 thinking tokens bill as output — the expensive
    half of the batch. The 200-lemma trial exists to check that this is not a
    false economy before the full run.
    """

    name: str = "low"
    model: str = MODEL
    effort: str = "low"
    thinking: bool = False
    max_tokens: int = 4096

    def output_config(self) -> dict[str, Any]:
        return {
            "effort": self.effort,
            "format": {"type": "json_schema", "schema": GLOSS_SCHEMA},
        }

    def thinking_config(self) -> dict[str, str]:
        return {"type": "adaptive"} if self.thinking else {"type": "disabled"}


@dataclass
class BatchStats(GlossStats):
    """What a batch cost and how cleanly it came back.

    The shared counters live on `GlossStats`. What is added here is what only a
    remote batch has: the two batch-only terminal states, the prompt-cache token
    columns, and a bill.
    """

    expired: int = 0
    canceled: int = 0

    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def cache_worked(self) -> bool:
        """A prefix under 1024 tokens silently fails to cache on Sonnet 5.

        There is no error for it, so this is the only place the failure becomes
        visible. A multi-request batch that never reads from cache means the
        system prompt has been trimmed below the threshold.
        """
        return self.requests < 2 or self.cache_read_tokens > 0

    def estimated_cost(self) -> float:
        """Rough dollars, at the batch rates above. An estimate, not an invoice."""
        return (
            self.input_tokens * _BATCH_INPUT_PER_MTOK
            + self.cache_creation_tokens * _BATCH_INPUT_PER_MTOK * _CACHE_WRITE_MULTIPLIER
            + self.cache_read_tokens * _BATCH_INPUT_PER_MTOK * _CACHE_READ_MULTIPLIER
            + self.output_tokens * _BATCH_OUTPUT_PER_MTOK
        ) / 1_000_000

    def report_lines(self) -> list[str]:
        """The two things worth saying about a batch that a local run cannot."""
        lines = [f"{'Estimated batch cost':<28} {'$' + format(self.estimated_cost(), '.2f'):>7}"]
        if self.expired or self.canceled:
            lines.append(
                f"{'Requests never answered':<28} "
                f"{self.expired + self.canceled:>7,}   (expired or canceled)"
            )
        if not self.cache_worked:
            lines.append(
                "!! The instruction prompt was never served from cache. It has "
                "probably slipped"
            )
            lines.append(
                "   below the 1024-token minimum, which fails silently and "
                "multiplies the bill."
            )
        return lines


def chunk_tasks(
    tasks: Sequence[GlossTask], size: int = LEMMAS_PER_REQUEST
) -> list[list[GlossTask]]:
    return [list(tasks[start : start + size]) for start in range(0, len(tasks), size)]


def custom_id_for(index: int) -> str:
    """`custom_id` accepts only letters, digits, underscore and hyphen.

    So it cannot be the lemma: Spanish lemmas carry accents, and the mangled ones
    carry spaces. The index addresses the chunk, and the echoed lemma inside the
    answer addresses the lemma.
    """
    return f"gloss-{index:05d}"


def build_requests(
    tasks: Sequence[GlossTask],
    settings: ModelSettings = ModelSettings(),
    *,
    chunk_size: int = LEMMAS_PER_REQUEST,
) -> tuple[list[dict[str, Any]], dict[str, list[GlossTask]]]:
    """Build the batch body, and the map from `custom_id` back to its lemmas.

    Returned as plain dicts rather than SDK models so that everything up to the
    network call is testable without the SDK or an API key.
    """
    requests: list[dict[str, Any]] = []
    by_custom_id: dict[str, list[GlossTask]] = {}

    for index, chunk in enumerate(chunk_tasks(tasks, chunk_size)):
        custom_id = custom_id_for(index)
        by_custom_id[custom_id] = chunk
        requests.append(
            {
                "custom_id": custom_id,
                "params": {
                    "model": settings.model,
                    "max_tokens": settings.max_tokens,
                    "thinking": settings.thinking_config(),
                    "output_config": settings.output_config(),
                    "system": [
                        {
                            "type": "text",
                            "text": SYSTEM_PROMPT,
                            # One hour rather than five minutes: a book's worth
                            # of requests takes longer than five minutes to work
                            # through, and a cache that expires mid-batch pays
                            # the write premium twice.
                            "cache_control": {"type": "ephemeral", "ttl": "1h"},
                        }
                    ],
                    "messages": [
                        {
                            "role": "user",
                            "content": render_batch(
                                [task.as_prompt_item() for task in chunk]
                            ),
                        }
                    ],
                },
            }
        )

    return requests, by_custom_id


def _text_of(message: Any) -> str | None:
    for block in getattr(message, "content", None) or ():
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", None)
    return None


def _clean(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def gloss_from_payload(payload: dict, task: GlossTask) -> tuple[Gloss, bool]:
    """Turn one returned object into a Gloss. Returns it and whether it was cut.

    The task supplies the identity, not the payload: the model echoes the lemma
    so we can match it, but the lexicon key is ours and an echo with a stray
    accent must not create a second entry.
    """
    raw_de = _clean(payload.get("de"))
    raw_en = _clean(payload.get("en"))
    not_spanish = bool(payload.get("not_spanish"))

    # A rejected lemma has no meaning to gloss. Trusting a gloss that arrived
    # alongside not_spanish would put an invented word on a card.
    german = normalize_gloss(None if not_spanish else raw_de)
    english = normalize_gloss(None if not_spanish else raw_en)
    de, en = german.text, english.text

    # Unlike the Wiktionary readers, clipped text is kept: there is no further
    # source to fall back to, and a clipped gloss beats a blank card. The count
    # is what makes the model drifting toward definitions visible in the report.
    truncated = german.was_shortened or english.was_shortened

    # A mexicanism with no note is filled in by Gloss itself — the model is
    # asked for one but is not obliged to comply.
    mexicanism = bool(payload.get("mexicanism")) and not not_spanish
    note = _clean(payload.get("region_note")) if not not_spanish else None

    return (
        Gloss(
            lemma=task.lemma,
            pos=task.pos,
            de=de,
            en=en,
            de_source=GlossSource.CLAUDE if de else None,
            en_source=GlossSource.CLAUDE if en else None,
            mexicanism=mexicanism,
            region_note=note,
            not_spanish=not_spanish,
            corrected_lemma=_clean(payload.get("corrected_lemma")),
        ),
        truncated and not not_spanish,
    )


def parse_results(
    results: Iterable[Any],
    by_custom_id: dict[str, list[GlossTask]],
) -> tuple[dict[Identity, Gloss], BatchStats]:
    """Fold batch results into glosses, keyed by lexicon identity.

    Results arrive in arbitrary order, so nothing here depends on sequence. A
    request that errored costs its 25 lemmas their glosses and nothing else —
    they stay ungloszed and the report counts them.
    """
    stats = BatchStats(requests=len(by_custom_id))
    glosses: dict[Identity, Gloss] = {}
    answered: set[Identity] = set()

    for result in results:
        custom_id = getattr(result, "custom_id", None)
        chunk = by_custom_id.get(custom_id or "", [])
        outcome = getattr(result, "result", None)
        status = getattr(outcome, "type", None)

        if status != "succeeded":
            if status == "errored":
                stats.errored += 1
                error = getattr(outcome, "error", None)
                stats.errors.append(f"{custom_id}: {getattr(error, 'type', 'unknown')}")
            elif status == "expired":
                stats.expired += 1
            elif status == "canceled":
                stats.canceled += 1
            else:
                stats.errored += 1
                stats.errors.append(f"{custom_id}: unrecognized status {status!r}")
            continue

        stats.succeeded += 1
        message = getattr(outcome, "message", None)
        usage = getattr(message, "usage", None)
        if usage is not None:
            stats.input_tokens += getattr(usage, "input_tokens", 0) or 0
            stats.output_tokens += getattr(usage, "output_tokens", 0) or 0
            stats.cache_creation_tokens += (
                getattr(usage, "cache_creation_input_tokens", 0) or 0
            )
            stats.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0

        text = _text_of(message)
        try:
            payload = json.loads(text or "")
        except ValueError:
            stats.errored += 1
            stats.errors.append(f"{custom_id}: response was not JSON")
            continue

        # Match on the echoed lemma and tag rather than on position. Structured
        # outputs guarantee the shape, not the ordering.
        wanted = {(task.lemma.lower(), task.pos): task for task in chunk}
        for item in payload.get("glosses") or ():
            if not isinstance(item, dict):
                stats.unmatched += 1
                continue
            key = (str(item.get("lemma", "")).strip().lower(), str(item.get("pos", "")).strip())
            task = wanted.get(key)
            if task is None:
                stats.unmatched += 1
                continue

            gloss, truncated = gloss_from_payload(item, task)
            glosses[task.identity] = gloss
            answered.add(task.identity)
            stats.glosses_returned += 1
            stats.truncated += int(truncated)
            stats.not_spanish += int(gloss.not_spanish)
            stats.mexicanisms += int(gloss.mexicanism)

    for chunk in by_custom_id.values():
        stats.missing += sum(1 for task in chunk if task.identity not in answered)

    return glosses, stats


def submit_and_wait(
    client: Any,
    requests: Sequence[dict[str, Any]],
    *,
    poll_seconds: float = 20.0,
    timeout_seconds: float = 24 * 60 * 60,
    on_status: Any = None,
) -> Iterator[Any]:
    """Send one batch and block until it ends, then stream its results.

    Most batches finish inside an hour; the API's own ceiling is 24 hours, which
    is what the default timeout mirrors.
    """
    batch = client.messages.batches.create(requests=list(requests))
    deadline = time.monotonic() + timeout_seconds

    while True:
        batch = client.messages.batches.retrieve(batch.id)
        if batch.processing_status == "ended":
            break
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"batch {batch.id} still {batch.processing_status} after "
                f"{timeout_seconds / 3600:.1f}h; retrieve it later with its id"
            )
        if on_status is not None:
            on_status(batch)
        time.sleep(poll_seconds)

    return client.messages.batches.results(batch.id)


def run(
    tasks: Sequence[GlossTask],
    settings: ModelSettings = ModelSettings(),
    *,
    client: Any = None,
    chunk_size: int = LEMMAS_PER_REQUEST,
    poll_seconds: float = 20.0,
    on_status: Any = None,
) -> tuple[dict[Identity, Gloss], BatchStats]:
    """Gloss `tasks` with Claude. The only function here that touches the network.

    The client is constructed with no arguments so the SDK resolves the key from
    `ANTHROPIC_API_KEY`. No key is read from, or written to, anything in this
    repository.
    """
    if not tasks:
        return {}, BatchStats()

    if client is None:
        import anthropic

        client = anthropic.Anthropic()

    requests, by_custom_id = build_requests(tasks, settings, chunk_size=chunk_size)
    results = submit_and_wait(
        client, requests, poll_seconds=poll_seconds, on_status=on_status
    )
    return parse_results(results, by_custom_id)


@dataclass
class ClaudeProvider:
    """The `GlossProvider` face of everything above.

    A thin wrapper by design. `run` predates the port and is what the tests
    drive; this exists so `gloss_lexicon` can hold a provider rather than an
    import, and so `name`/`model` reach the cache key.
    """

    settings: ModelSettings = ModelSettings()
    client: Any = None
    chunk_size: int = LEMMAS_PER_REQUEST
    poll_seconds: float = 20.0

    name: str = CLAUDE

    @property
    def model(self) -> str:
        return self.settings.model

    @classmethod
    def from_options(
        cls, options: ProviderOptions, *, client: Any = None
    ) -> ClaudeProvider:
        settings = ModelSettings(model=options.model) if options.model else ModelSettings()
        return cls(
            settings=settings,
            client=client,
            chunk_size=options.chunk_size or LEMMAS_PER_REQUEST,
        )

    def gloss(
        self,
        tasks: Sequence[GlossTask],
        *,
        on_status: Any = None,
        on_written: Any = None,
    ) -> tuple[dict[Identity, Gloss], BatchStats]:
        glosses, stats = run(
            tasks,
            self.settings,
            client=self.client,
            chunk_size=self.chunk_size,
            poll_seconds=self.poll_seconds,
            on_status=on_status,
        )
        # Once, at the end. The Batches API hands back a finished batch rather
        # than a stream, so there is nothing earlier to hand over — the callback
        # is honoured for the caller's sake, not for resumability.
        if on_written is not None and glosses:
            on_written(glosses)
        return glosses, stats

    def describe(self) -> str:
        return (
            f"Claude {self.settings.model} (effort {self.settings.effort}, "
            f"thinking {'adaptive' if self.settings.thinking else 'off'}, "
            f"batched {self.chunk_size} per request)"
        )


PROMPT_VERSION = PROMPT_VERSION  # re-exported: the cache stores it per row
GlossTask = GlossTask  # re-exported: it lived here before the port existed
