"""Running the sources in order, and folding the answers together.

    cache  ->  en.wiktionary  ->  de.wiktionary  ->  a model  ->  cache

Each stage fills only what the stage before it left empty, so a source's
priority is simply its position. English glosses come from English Wiktionary
because that is where they exist; German mostly comes from the model, because
German Wiktionary holds about 6,600 Spanish entries against a book's nine
thousand lemmas.

Which model is not this module's business. It is handed a `GlossProvider`
(`glossing/provider.py`) chosen by `--gloss-provider`, and nothing here imports
Claude or Ollama — the same rule CLAUDE.md applies to storage, applied to the
one other place this pipeline talks to something it does not control.

The whole lexicon is glossed, not just the teach set. Two reasons: `mexicanism`
is an *input* to the SPEC §5 teach rules, so scoping the pass to the teach set
would need the teach set to already exist; and the reader glosses every
dotted-underline word, so Phase 3 needs them regardless. At batch rates the
difference is under a dollar.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from molcajete_prep.classify import LemmaKey
from molcajete_prep.glossing.cache import NO_PROVIDER, GlossCache
from molcajete_prep.glossing.models import Gloss, GlossSource, is_model_source
from molcajete_prep.glossing.prompts import PROMPT_VERSION
from molcajete_prep.glossing.provider import (
    GlossProvider,
    GlossStats,
    GlossTask,
    Identity,
    ProviderOptions,
    build_provider,
)
from molcajete_prep.glossing.sources import (
    DE_WIKTIONARY,
    DEFAULT_EXTRACT_DIR,
    EN_WIKTIONARY,
    SourceUnavailableError,
)
from molcajete_prep.glossing.wiktionary import WiktionaryHit, read_extract
from molcajete_prep.lexicon import Lexicon, example_sentence
from molcajete_prep.nlp import Token

# How German Wiktionary's text is treated.
VERBATIM = "verbatim"
CONTEXT_ONLY = "context-only"


@dataclass(frozen=True)
class GlossingOptions:
    """How much of the pass to run, and how much to trust.

    `de_wiktionary` exists because sizing alone cannot catch a *short*
    definition: German Wiktionary glosses `lunes` as "der erste Wochentag",
    which fits a card and reads like a riddle. `verbatim` keeps such glosses;
    `context-only` demotes every German Wiktionary gloss to model context and
    lets the model write all the German.

    `context-only` is the default because that is what the riddle argument
    concludes: a gloss that fits a card is not the same as a gloss that teaches
    the word, and only the model has the example sentence in front of it.
    `--de-wiktionary verbatim` keeps the old behaviour for comparison.
    """

    use_model: bool = True
    use_cache: bool = True
    regloss: bool = False
    model_limit: int | None = None
    de_wiktionary: str = CONTEXT_ONLY

    # How the model half of the pass is run. `provider` wins when given — that
    # is the seam tests and the trial use; otherwise one is built from the
    # options, which is what the CLI flags reach.
    provider_options: ProviderOptions = field(default_factory=ProviderOptions)
    provider: GlossProvider | None = None

    # None means "wherever the extracts normally live". Resolved at call time
    # rather than baked in as a default, so the test suite can redirect it and
    # a forgotten `gloss=False` fails loudly instead of streaming 22.9 GB.
    extract_dir: Path | None = None


@dataclass
class GlossingResult:
    """The glosses, keyed by lexicon key, plus how they were come by."""

    glosses: dict[LemmaKey, Gloss] = field(default_factory=dict)
    cache_hits: int = 0
    sent_to_model: int = 0
    skipped_by_limit: int = 0
    stats: GlossStats = field(default_factory=GlossStats)
    ran_model: bool = False
    provider_name: str = ""
    provider_model: str = ""
    de_wiktionary_mode: str = CONTEXT_ONLY

    # The raw Wiktionary text behind each identity, which is what the model is
    # shown as context. Kept so the trial can build exactly the prompts a real
    # build would send: under `context-only` the applied gloss has had its
    # German removed, and reconstructing context from it would quietly send the
    # model less than production does.
    context: dict[Identity, GlossTask] = field(default_factory=dict)

    def gloss_for(self, key: LemmaKey) -> Gloss | None:
        return self.glosses.get(key)

    def mexicanism_by_key(self) -> dict[LemmaKey, bool]:
        """What SPEC §5 needs from this pass, and the reason it runs first."""
        return {key: gloss.mexicanism for key, gloss in self.glosses.items()}


def _wants_model(gloss: Gloss | None) -> bool:
    """Whether this lemma still has something to gain from the model.

    Complete in both languages, or already answered by a model — including a
    refusal — means there is nothing more to ask. Re-sending a lemma the model
    has already declined would pay for the same "not a word" on every rebuild.

    Tested against model sources in general rather than against Claude
    specifically: a lemma Ollama answered must not be re-asked either, or every
    local rebuild would run the whole book again.
    """
    if gloss is None:
        return True
    if gloss.not_spanish:
        return False
    if gloss.has_german and gloss.has_english:
        return False
    return not (is_model_source(gloss.de_source) or is_model_source(gloss.en_source))


def _require(path: Path, what: str) -> None:
    if not path.exists():
        raise SourceUnavailableError(
            f"{what} is not downloaded ({path}). Run:\n"
            "  uv run python -m molcajete_prep.glossing.sources --fetch\n"
            "or build with --no-gloss to skip glossing entirely."
        )


def _apply_hit(gloss: Gloss, hit: WiktionaryHit, *, take_german: bool) -> Gloss:
    """Merge one Wiktionary hit into the running gloss."""
    incoming = hit.gloss
    if not take_german and incoming.de:
        incoming = Gloss(
            lemma=incoming.lemma,
            pos=incoming.pos,
            en=incoming.en,
            en_source=incoming.en_source,
            mexicanism=incoming.mexicanism,
            region_note=incoming.region_note,
        )
    return gloss.merged_with(incoming)


def _task_for(
    identity: Identity,
    hits: dict[Identity, list[WiktionaryHit]],
    example: str | None,
) -> GlossTask:
    """Hand the model everything we know: the sentence, and Wiktionary's attempt."""
    lemma, pos = identity
    raw_en = raw_de = hint = None
    for hit in hits.get(identity, ()):
        raw_en = raw_en or hit.raw_en
        raw_de = raw_de or hit.raw_de
        hint = hint or hit.region_hint

    return GlossTask(
        lemma=lemma,
        pos=pos,
        example_es=example,
        wiktionary_en=raw_en,
        wiktionary_de=raw_de,
        region_hint=hint,
    )


def gloss_lexicon(
    lexicon: Lexicon,
    chapters: Sequence[Sequence[Sequence[Token]]],
    *,
    book_id: str,
    options: GlossingOptions = GlossingOptions(),
    cache: GlossCache | None = None,
    now: datetime | None = None,
    client: Any = None,
    on_status: Any = None,
) -> GlossingResult:
    """Gloss every lemma in `lexicon`, cheapest source first."""
    now = now or datetime.now()

    # Resolved before anything else so that the cache lookup is already scoped
    # to the provider that would answer the misses. Building it costs nothing
    # and touches no network.
    provider = None
    if options.use_model:
        provider = options.provider or build_provider(options.provider_options, client=client)

    result = GlossingResult(
        de_wiktionary_mode=options.de_wiktionary,
        provider_name=provider.name if provider else "",
        provider_model=provider.model if provider else "",
    )
    if not lexicon.records:
        return result

    keys_by_identity: dict[Identity, list[LemmaKey]] = {}
    for key, record in lexicon.records.items():
        keys_by_identity.setdefault((record.lemma, record.pos), []).append(key)
    identities = list(keys_by_identity)

    scope = {
        "provider": provider.name if provider else NO_PROVIDER,
        "model": provider.model if provider else "",
    }

    owned_cache = cache is None
    cache = cache or GlossCache()
    try:
        if options.regloss:
            cache.forget(identities)

        by_identity: dict[Identity, Gloss] = {}
        if options.use_cache:
            for identity, gloss in cache.get_many(identities, **scope).items():
                by_identity[identity] = gloss
            result.cache_hits = len(by_identity)

        outstanding = {i for i in identities if i not in by_identity}
        raw_hits: dict[Identity, list[WiktionaryHit]] = {}
        extract_dir = options.extract_dir or DEFAULT_EXTRACT_DIR

        if outstanding:
            wanted = {lemma for lemma, _ in outstanding}
            take_german = options.de_wiktionary == VERBATIM

            for source, definition in (
                (GlossSource.EN_WIKTIONARY, EN_WIKTIONARY),
                (GlossSource.DE_WIKTIONARY, DE_WIKTIONARY),
            ):
                path = definition.path(extract_dir)
                _require(path, definition.description)
                index = read_extract(path, source=source, wanted_lemmas=wanted)
                for identity, hit in index.items():
                    if identity not in outstanding:
                        continue
                    raw_hits.setdefault(identity, []).append(hit)
                    current = by_identity.get(identity) or Gloss(
                        lemma=identity[0], pos=identity[1]
                    )
                    by_identity[identity] = _apply_hit(
                        current,
                        hit,
                        take_german=take_german or source is not GlossSource.DE_WIKTIONARY,
                    )

        # A lemma goes to the model when either language is still empty. English
        # is secondary, but the same request answers both, so a lemma already in
        # a chunk costs nothing extra to complete.
        #
        # Computed over every identity, not just the ones the cache missed. A
        # gloss cached by an earlier `--gloss-offline` build has no German and
        # must still be sent; scoping this to cache misses would mean an offline
        # build permanently poisoned the book against ever being glossed.
        needs = [
            identity for identity in identities if _wants_model(by_identity.get(identity))
        ]

        # Most-used words first, so a --gloss-limit spends where it pays.
        def book_count(identity: Identity) -> int:
            return max(lexicon.records[key].book_count for key in keys_by_identity[identity])

        needs.sort(key=lambda identity: (-book_count(identity), identity))

        if options.model_limit is not None and len(needs) > options.model_limit:
            result.skipped_by_limit = len(needs) - options.model_limit
            needs = needs[: options.model_limit]

        # Built for every identity, not only the ones being sent: the trial
        # reads this to reproduce production's prompts exactly.
        examples: dict[Identity, str | None] = {}
        for identity in identities:
            record = lexicon.records[keys_by_identity[identity][0]]
            found = example_sentence(record, chapters)
            examples[identity] = found[0] if found else None
            result.context[identity] = _task_for(identity, raw_hits, examples[identity])

        # What the dictionaries alone concluded, before any model touched it.
        # Snapshotted rather than recovered afterwards, because the model's
        # answer is merged into `by_identity` in place and the dictionary scope
        # must not end up holding it.
        from_dictionaries = dict(by_identity)

        if provider is not None and needs:
            tasks = [result.context[identity] for identity in needs]
            result.sent_to_model = len(tasks)
            result.ran_model = True

            written, stats = provider.gloss(tasks, on_status=on_status)
            result.stats = stats
            for identity, gloss in written.items():
                current = by_identity.get(identity)
                by_identity[identity] = current.merged_with(gloss) if current else gloss

            # Only what the model itself said goes in the model scope. Writing
            # the merged gloss there would file English Wiktionary's answer
            # under the model's name, and a later build reading that row could
            # not tell which half the model is accountable for.
            cache.put_many(
                [written[identity] for identity in written],
                now=now,
                provider=provider.name,
                model=provider.model,
                prompt_version=PROMPT_VERSION,
                examples={identity: examples.get(identity) for identity in written},
                book_id=book_id,
            )

        # Everything the Wiktionary pass settled is cached, *including the
        # lemmas it found nothing for*. Caching only the hits meant a rebuild
        # re-streamed both dumps to rediscover the same three thousand misses —
        # a warm build cost the same 68 seconds as a cold one. An empty row is
        # the answer "we looked"; `--regloss` is how you ask again after kaikki
        # refreshes.
        #
        # Written for every outstanding lemma, the model-answered ones included.
        # Before the provider scopes existed, a model-answered lemma was skipped
        # here because its single row already held the merged answer. Now the
        # two live in different scopes, and skipping them would mean each
        # model-answered lemma re-streamed both dumps on the next build — the
        # warm-rebuild fix undone for exactly the lemmas that cost the most.
        cache.put_many(
            [
                from_dictionaries.get(identity) or Gloss(lemma=identity[0], pos=identity[1])
                for identity in outstanding
            ],
            now=now,
            book_id=book_id,
        )

        for identity, gloss in by_identity.items():
            for key in keys_by_identity[identity]:
                result.glosses[key] = gloss
    finally:
        if owned_cache:
            cache.close()

    return result
