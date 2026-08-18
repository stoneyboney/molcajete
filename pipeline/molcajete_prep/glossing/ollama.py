"""The local gloss provider: a model running on this machine, via Ollama.

Same input and output contract as the Claude path, and the same prompt. What
differs is everything about how much you can trust the answer.

**A local model breaks the format.** Ollama constrains generation to the JSON
schema, which stops malformed JSON but not a model that answers for the wrong
lemma, omits half the batch, or writes a dictionary definition where a two-word
gloss belongs. So nothing here trusts the response: the echoed lemma is checked
against what was asked, the word limit is re-derived in Python from
`normalize_gloss` rather than believed, and a failure buys one stricter retry
before being written down as a miss. A miss is a number in the report; a crash
is a build that has to start over.

**One lemma per request, not twenty-five.** The Claude path batches because a
cached prompt prefix is what makes a batch cheap. Locally there is no bill to
amortize, Ollama reuses the KV cache for a fixed system prefix anyway, and a
12B model asked for twenty-five aligned objects starts merging and dropping
them — one bad response would cost twenty-five lemmas instead of one.

**Concurrency is throttled, not maximised.** One request already saturates the
GPU; the second keeps the pipe full while the first detokenizes. Beyond that it
gets *slower*, which is worth stating as a measurement rather than an intuition
— twenty lemmas through gemma3:12b on an M4 Pro, 24 GB:

    concurrency 2   81s   22.4 output tok/s
    concurrency 4   84s   21.5 output tok/s
    concurrency 6   96s   18.8 output tok/s

So the default is two, and `--gloss-concurrency` exists because those numbers
describe one laptop and one model, not a law.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, ClassVar

from molcajete_prep.glossing.models import (
    MAX_UNITS,
    MAX_WORDS_PER_UNIT,
    Gloss,
    GlossSource,
    normalize_gloss,
)
from molcajete_prep.glossing.prompts import (
    GLOSS_SCHEMA,
    SYSTEM_PROMPT,
    render_batch,
    render_correction,
)
from molcajete_prep.glossing.provider import (
    OLLAMA,
    GlossStats,
    GlossTask,
    Identity,
    ProviderOptions,
)

DEFAULT_MODEL = "gemma3:12b"
DEFAULT_HOST = "http://localhost:11434"

# One. See the module docstring: locally there is nothing to amortize, and a
# bad answer should cost one lemma rather than twenty-five.
DEFAULT_CHUNK_SIZE = 1

DEFAULT_CONCURRENCY = 2
DEFAULT_RETRIES = 1
DEFAULT_TIMEOUT = 120.0


class OllamaUnavailableError(RuntimeError):
    """Ollama is not reachable. Distinct from a model behaving badly."""


@dataclass
class LocalStats(GlossStats):
    """What a local run measured that a batch API cannot.

    `retried` and `failed_after_retry` are the quality signal — they say how
    often the model could not hold the format, which is the number that decides
    whether a smaller model is usable. `elapsed_seconds` and the throughput
    derived from it are the local equivalent of a bill.
    """

    retried: int = 0
    failed_after_retry: int = 0
    salvaged: int = 0
    malformed_json: int = 0
    schema_violations: int = 0
    wrong_echo: int = 0
    over_length: int = 0
    timeouts: int = 0

    elapsed_seconds: float = 0.0

    # Wall clock under concurrency is not a sum. Two chunks that ran at the same
    # time took as long as the slower one, and it is set once for the whole run.
    NON_ADDITIVE: ClassVar[tuple[str, ...]] = ("elapsed_seconds",)

    @property
    def tokens_per_second(self) -> float:
        if self.elapsed_seconds <= 0:
            return 0.0
        return (self.input_tokens + self.output_tokens) / self.elapsed_seconds

    @property
    def output_tokens_per_second(self) -> float:
        if self.elapsed_seconds <= 0:
            return 0.0
        return self.output_tokens / self.elapsed_seconds

    def report_lines(self) -> list[str]:
        lines = [
            f"{'Ran locally, no cost':<28} {'free':>7}"
            f"   ({self.elapsed_seconds / 60:.1f} min, "
            f"{self.output_tokens_per_second:.0f} output tok/s)"
        ]
        if self.retried:
            lines.append(
                f"{'Needed a stricter retry':<28} {self.retried:>7,}"
                f"   ({self.rejection_summary()})"
            )
        if self.salvaged:
            lines.append(
                f"{'Trimmed on the last attempt':<28} {self.salvaged:>7,}"
                "   (surplus alternatives dropped)"
            )
        if self.failed_after_retry:
            lines.append(
                f"{'Still wrong after retry':<28} {self.failed_after_retry:>7,}"
                "   (recorded as misses, not guesses)"
            )
        if self.timeouts:
            lines.append(f"{'Timed out':<28} {self.timeouts:>7,}")
        return lines

    def rejection_summary(self) -> str:
        """Why answers were rejected, which says what to fix."""
        parts = [
            (self.over_length, "too long"),
            (self.wrong_echo, "wrong lemma echoed"),
            (self.malformed_json, "unparseable"),
            (self.schema_violations, "missing fields"),
        ]
        named = [f"{count} {label}" for count, label in parts if count]
        return ", ".join(named) if named else "no rejections"

    def trial_line(self) -> str:
        return (
            f"free · {self.elapsed_seconds / 60:.1f} min · "
            f"{self.output_tokens_per_second:.0f} output tok/s"
        )


class Rejected(Exception):
    """One answer failed a check. Carries what to tell the model on the retry."""

    def __init__(self, reason: str, counter: str, *, raw: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.counter = counter  # which LocalStats field to bump
        self.raw = raw


def _post_json(url: str, payload: dict, timeout: float) -> dict:
    """One JSON round trip, on the standard library.

    No SDK and no HTTP client dependency: this is one POST to localhost, and
    CLAUDE.md asks before dependencies for exactly this kind of thing.

    All three arguments are positional because this is the default `transport`,
    and a test double has to be substitutable for it. `timeout` was keyword-only
    here once; every test passed, because every test supplied its own double.
    """
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _require_fields(item: Any) -> dict:
    """Reject anything the prompt's schema promised and this answer lacks."""
    if not isinstance(item, dict):
        raise Rejected("the answer was not an object", "schema_violations")
    for name in ("lemma", "pos", "de", "en", "mexicanism", "not_spanish"):
        if name not in item:
            raise Rejected(f"the field {name!r} was missing", "schema_violations")
    return item


def _clean(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def echoed_lemma(value: Any) -> str:
    """The lemma the model meant, with the prompt's own formatting undone.

    `render_batch` writes each lemma as `lunes · NOUN`, and gemma3:12b echoes
    the whole line back into the `lemma` field. The gloss beside it is correct;
    only the echo is mangled, and rejecting a good gloss over the separator this
    code put there is a self-inflicted miss.

    Narrow on purpose. It strips the one artefact the prompt is responsible for
    and nothing else, so an answer about a genuinely different word — `casona`
    for `casa` — still fails, which is the failure the check exists to catch.
    """
    text = str(value or "").strip()
    head = text.split("·", 1)[0]
    return head.strip().lower()


def _checked_gloss(text: str | None, language: str, *, strict: bool) -> tuple[str | None, bool]:
    """Enforce the one-to-three-words rule in code, not only in the prompt.

    `normalize_gloss` already encodes the rule and is what the Wiktionary
    readers use, so the check is derived from it rather than restated. Reusing
    it also means the two paths cannot drift apart on what "three words" means.

    `strict` is the difference between an attempt that has a retry left and the
    last one. While a retry is available, any shortening is a rejection — the
    model is asked again with the rule spelled out. On the last attempt the
    existing `NormalizedGloss` distinction decides: text that was merely
    `trimmed` had too many short alternatives and "der Bau, die Höhle, das Loch"
    cut to three is still good card text, so it is kept and counted. Text that
    was `clipped` is the wreckage of a definition, and a miss beats that.

    Returns the text and whether it had to be shortened to get there.
    """
    if text is None:
        return None, False
    normalized = normalize_gloss(text)
    if not normalized.was_shortened:
        return normalized.text, False

    if strict or normalized.clipped:
        raise Rejected(
            f"the {language} gloss {text!r} is longer than "
            f"{MAX_UNITS} alternatives of {MAX_WORDS_PER_UNIT} words each",
            "over_length",
            raw=text,
        )
    return normalized.text, True


def gloss_from_item(item: Any, task: GlossTask, *, strict: bool = True) -> tuple[Gloss, bool]:
    """Turn one returned object into a Gloss, or reject it.

    Strict where the Claude parser is forgiving. There the response came from a
    model that reliably echoes what it was asked and the batch had already been
    paid for, so a slightly-too-long gloss was cut down and counted. Here the
    retry is free and the model is less reliable, so the same input is sent back
    with the rule spelled out instead — until the retries run out.

    Returns the gloss and whether anything had to be shortened to build it.
    """
    payload = _require_fields(item)

    echoed = (echoed_lemma(payload.get("lemma")), str(payload.get("pos", "")).strip())
    if echoed != (task.lemma.lower(), task.pos):
        raise Rejected(
            f"the answer was for {echoed[0]!r}/{echoed[1]} but "
            f"{task.lemma!r}/{task.pos} was asked",
            "wrong_echo",
        )

    not_spanish = bool(payload.get("not_spanish"))

    # A rejected lemma has no meaning to gloss. Trusting a gloss that arrived
    # alongside not_spanish would put an invented word on a card.
    if not_spanish:
        de = en = None
        shortened = False
    else:
        de, cut_de = _checked_gloss(_clean(payload.get("de")), "German", strict=strict)
        en, cut_en = _checked_gloss(_clean(payload.get("en")), "English", strict=strict)
        shortened = cut_de or cut_en

    mexicanism = bool(payload.get("mexicanism")) and not not_spanish
    note = _clean(payload.get("region_note")) if not not_spanish else None

    return (
        Gloss(
            lemma=task.lemma,
            pos=task.pos,
            de=de,
            en=en,
            de_source=GlossSource.OLLAMA if de else None,
            en_source=GlossSource.OLLAMA if en else None,
            mexicanism=mexicanism,
            region_note=note,
            not_spanish=not_spanish,
            corrected_lemma=_clean(payload.get("corrected_lemma")),
        ),
        shortened,
    )


@dataclass
class OllamaProvider:
    """A `GlossProvider` backed by a model running on localhost.

    No key, no account, no network beyond the loopback interface. `transport` is
    the seam the tests drive: a callable taking `(url, payload, timeout)` and
    returning the decoded response, so every parsing and retry path is testable
    without a server.
    """

    model: str = DEFAULT_MODEL
    host: str = DEFAULT_HOST
    chunk_size: int = DEFAULT_CHUNK_SIZE
    concurrency: int = DEFAULT_CONCURRENCY
    retries: int = DEFAULT_RETRIES
    timeout_seconds: float = DEFAULT_TIMEOUT
    temperature: float = 0.0
    retry_temperature: float = 0.3
    transport: Any = None

    name: str = OLLAMA

    @classmethod
    def from_options(
        cls, options: ProviderOptions, *, transport: Any = None
    ) -> OllamaProvider:
        return cls(
            model=options.model or DEFAULT_MODEL,
            host=os.environ.get("OLLAMA_HOST", DEFAULT_HOST),
            chunk_size=options.chunk_size or DEFAULT_CHUNK_SIZE,
            concurrency=max(1, options.concurrency),
            retries=max(0, options.retries),
            timeout_seconds=options.timeout_seconds,
            transport=transport,
        )

    def describe(self) -> str:
        return (
            f"Ollama {self.model} on {self.host} "
            f"({self.chunk_size} per request, {self.concurrency} at a time, "
            f"{self.retries} retry)"
        )

    # -- the port --------------------------------------------------------

    def gloss(
        self,
        tasks: Sequence[GlossTask],
        *,
        on_status: Any = None,
        on_written: Any = None,
    ) -> tuple[dict[Identity, Gloss], LocalStats]:
        stats = LocalStats()
        if not tasks:
            return {}, stats

        chunks = [
            list(tasks[start : start + self.chunk_size])
            for start in range(0, len(tasks), self.chunk_size)
        ]
        stats.requests = len(chunks)

        glosses: dict[Identity, Gloss] = {}
        started = time.monotonic()
        done = 0

        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            for answered, chunk_stats in pool.map(self._gloss_chunk, chunks):
                glosses.update(answered)
                stats.merge(chunk_stats)
                done += 1
                # Hand each chunk over as it lands. Hours of work should not
                # depend on the process surviving to the end of them.
                if on_written is not None and answered:
                    on_written(answered)
                if on_status is not None and (done % 10 == 0 or done == len(chunks)):
                    on_status(_progress(self.model, done, len(chunks), len(glosses)))

        stats.elapsed_seconds = time.monotonic() - started
        stats.missing = len(tasks) - len(glosses)
        stats.glosses_returned = len(glosses)
        stats.not_spanish = sum(1 for g in glosses.values() if g.not_spanish)
        stats.mexicanisms = sum(1 for g in glosses.values() if g.mexicanism)
        return glosses, stats

    # -- one request, with its retry -------------------------------------

    def _gloss_chunk(
        self, chunk: Sequence[GlossTask]
    ) -> tuple[dict[Identity, Gloss], LocalStats]:
        """Ask for one chunk, retry what came back wrong, then give up on it.

        Retries are per chunk rather than per lemma because the response is per
        chunk; with the default chunk size of one those are the same thing, and
        with a larger one a single bad object costs its neighbours a re-ask
        rather than costing them their glosses.
        """
        stats = LocalStats()
        correction: str | None = None
        attempts = self.retries + 1

        for attempt in range(attempts):
            last = attempt == attempts - 1
            try:
                response = self._call(chunk, correction)
            except OllamaUnavailableError:
                # Not a lemma the model got wrong — the server is not there.
                # Nine thousand identical failures is not a partial result, so
                # this is the one thing that stops the build.
                raise
            except TimeoutError:
                stats.timeouts += 1
                stats.errored += 1
                correction = None
                continue
            except (urllib.error.URLError, OSError) as error:
                stats.errored += 1
                stats.errors.append(f"{chunk[0].lemma}: {error}")
                correction = None
                continue

            body = _content_of(response)
            stats.input_tokens += int(response.get("prompt_eval_count") or 0)
            stats.output_tokens += int(response.get("eval_count") or 0)

            try:
                items = _parse_body(body)
                answered, shortened = self._match(items, chunk, strict=not last)
            except Rejected as rejection:
                setattr(stats, rejection.counter, getattr(stats, rejection.counter) + 1)
                if not last:
                    stats.retried += 1
                    correction = render_correction(
                        [task.as_prompt_item() for task in chunk],
                        offending=rejection.raw or body,
                        reason=rejection.reason,
                    )
                    continue
                stats.failed_after_retry += len(chunk)
                stats.errors.append(f"{chunk[0].lemma}: {rejection.reason}")
                return {}, stats

            stats.succeeded += 1
            stats.salvaged += shortened
            stats.truncated += shortened
            return answered, stats

        # Every attempt failed for a transport reason rather than a parsing one.
        stats.failed_after_retry += len(chunk)
        return {}, stats

    def _call(self, chunk: Sequence[GlossTask], correction: str | None) -> dict:
        prompt = render_batch([task.as_prompt_item() for task in chunk])
        payload = {
            "model": self.model,
            "stream": False,
            "format": GLOSS_SCHEMA,
            # The first attempt is greedy, so a build is reproducible and two
            # runs of the trial can be compared. A retry is not: at temperature
            # zero the model is a function of its input, and the correction
            # changes the input less than it looks — the first observed retry
            # returned a byte-identical answer. A little heat is what makes the
            # second attempt a second attempt rather than a second copy.
            "options": {
                "temperature": self.retry_temperature if correction else self.temperature
            },
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": correction or prompt},
            ],
        }

        transport = self.transport or _post_json
        try:
            return transport(f"{self.host}/api/chat", payload, self.timeout_seconds)
        except urllib.error.URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise TimeoutError(str(error)) from error
            raise OllamaUnavailableError(
                f"could not reach Ollama at {self.host} ({error.reason}). "
                "Start it with `ollama serve`, or build with --gloss-offline."
            ) from error

    def _match(
        self, items: Sequence[Any], chunk: Sequence[GlossTask], *, strict: bool
    ) -> tuple[dict[Identity, Gloss], int]:
        """Pair answers to questions, rejecting the chunk if any lemma is unanswered.

        A partial answer is a rejection rather than a partial success: the retry
        is free, and accepting half a chunk silently teaches the model's
        sloppiness to the cache.

        Returns the glosses and how many had to be shortened to fit a card.
        """
        by_identity = {(task.lemma.lower(), task.pos): task for task in chunk}
        answered: dict[Identity, Gloss] = {}
        shortened = 0

        for item in items:
            payload = _require_fields(item)
            key = (
                echoed_lemma(payload.get("lemma")),
                str(payload.get("pos", "")).strip(),
            )
            task = by_identity.get(key)
            if task is None:
                raise Rejected(
                    f"the answer named {key[0]!r}/{key[1]}, which was not asked for",
                    "wrong_echo",
                )
            gloss, was_shortened = gloss_from_item(payload, task, strict=strict)
            answered[task.identity] = gloss
            shortened += int(was_shortened)

        if len(answered) != len(chunk):
            unanswered = [t.lemma for t in chunk if t.identity not in answered]
            raise Rejected(
                f"no answer for {', '.join(unanswered)}",
                "schema_violations",
            )
        return answered, shortened


def _content_of(response: dict) -> str:
    message = response.get("message") or {}
    return str(message.get("content") or "")


def _parse_body(body: str) -> list[Any]:
    """The response text, as the list of gloss objects it should be."""
    if not body.strip():
        raise Rejected("the answer was empty", "malformed_json")
    try:
        payload = json.loads(body)
    except ValueError:
        raise Rejected("the answer was not JSON", "malformed_json", raw=body) from None

    if isinstance(payload, list):
        # Some models answer with the array rather than the wrapper object,
        # which is unambiguous and not worth a retry.
        return payload
    if not isinstance(payload, dict):
        raise Rejected("the answer was not an object", "schema_violations", raw=body)

    items = payload.get("glosses")
    if items is None:
        raise Rejected("the answer had no 'glosses' array", "schema_violations", raw=body)
    if not isinstance(items, list):
        raise Rejected("'glosses' was not an array", "schema_violations", raw=body)
    return items


@dataclass(frozen=True)
class _Counts:
    processing: int
    succeeded: int


@dataclass(frozen=True)
class _Progress:
    """What `on_status` is handed.

    Shaped like the batch object `claude_status.print_batch_status` reads, so a
    local run reuses the existing progress printer instead of growing a second
    one that says the same thing differently.
    """

    processing_status: str
    request_counts: _Counts


def _progress(model: str, done: int, total: int, glossed: int) -> _Progress:
    return _Progress(
        processing_status=f"{model} on localhost",
        request_counts=_Counts(processing=total - done, succeeded=glossed),
    )


def probe(host: str = DEFAULT_HOST, *, timeout: float = 5.0) -> list[str]:
    """Which models are pulled. Used to fail early with something actionable."""
    request = urllib.request.Request(f"{host}/api/tags", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise OllamaUnavailableError(
            f"could not reach Ollama at {host} ({error}). Start it with "
            "`ollama serve`, or build with --gloss-offline."
        ) from error
    return [str(entry.get("name", "")) for entry in payload.get("models") or ()]
