"""Running the three sources in order, and folding the answers together.

    cache  ->  en.wiktionary  ->  de.wiktionary  ->  Claude  ->  cache

Each stage fills only what the stage before it left empty, so a source's
priority is simply its position. English glosses come from English Wiktionary
because that is where they exist; German mostly comes from Claude, because
German Wiktionary holds about 6,600 Spanish entries against a book's nine
thousand lemmas.

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
from molcajete_prep.glossing.cache import GlossCache
from molcajete_prep.glossing.claude import BatchStats, GlossTask, ModelSettings
from molcajete_prep.glossing.claude import run as run_claude
from molcajete_prep.glossing.models import Gloss, GlossSource
from molcajete_prep.glossing.prompts import PROMPT_VERSION
from molcajete_prep.glossing.sources import (
    DE_WIKTIONARY,
    DEFAULT_EXTRACT_DIR,
    EN_WIKTIONARY,
    SourceUnavailableError,
)
from molcajete_prep.glossing.wiktionary import WiktionaryHit, read_extract
from molcajete_prep.lexicon import Lexicon, example_sentence
from molcajete_prep.nlp import Token

Identity = tuple[str, str]

# How German Wiktionary's text is treated.
VERBATIM = "verbatim"
CONTEXT_ONLY = "context-only"


@dataclass(frozen=True)
class GlossingOptions:
    """How much of the pass to run, and how much to trust.

    `de_wiktionary` exists because sizing alone cannot catch a *short*
    definition: German Wiktionary glosses `lunes` as "der erste Wochentag",
    which fits a card and reads like a riddle. `verbatim` keeps such glosses;
    `context-only` demotes every German Wiktionary gloss to Claude context and
    lets the model write all the German. The trial measures which is right; this
    flag makes acting on the answer a one-word change.
    """

    use_claude: bool = True
    use_cache: bool = True
    regloss: bool = False
    claude_limit: int | None = None
    de_wiktionary: str = VERBATIM
    settings: ModelSettings = field(default_factory=ModelSettings)

    # None means "wherever the extracts normally live". Resolved at call time
    # rather than baked in as a default, so the test suite can redirect it and
    # a forgotten `gloss=False` fails loudly instead of streaming 22.9 GB.
    extract_dir: Path | None = None


@dataclass
class GlossingResult:
    """The glosses, keyed by lexicon key, plus how they were come by."""

    glosses: dict[LemmaKey, Gloss] = field(default_factory=dict)
    cache_hits: int = 0
    sent_to_claude: int = 0
    skipped_by_limit: int = 0
    batch: BatchStats = field(default_factory=BatchStats)
    ran_claude: bool = False
    de_wiktionary_mode: str = VERBATIM

    def gloss_for(self, key: LemmaKey) -> Gloss | None:
        return self.glosses.get(key)

    def mexicanism_by_key(self) -> dict[LemmaKey, bool]:
        """What SPEC §5 needs from this pass, and the reason it runs first."""
        return {key: gloss.mexicanism for key, gloss in self.glosses.items()}


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
    result = GlossingResult(de_wiktionary_mode=options.de_wiktionary)
    if not lexicon.records:
        return result

    keys_by_identity: dict[Identity, list[LemmaKey]] = {}
    for key, record in lexicon.records.items():
        keys_by_identity.setdefault((record.lemma, record.pos), []).append(key)
    identities = list(keys_by_identity)

    owned_cache = cache is None
    cache = cache or GlossCache()
    try:
        if options.regloss:
            cache.forget(identities)

        by_identity: dict[Identity, Gloss] = {}
        if options.use_cache:
            for identity, gloss in cache.get_many(identities).items():
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

        # A lemma goes to Claude when either language is still empty. English is
        # secondary, but the same request answers both, so a lemma already in a
        # chunk costs nothing extra to complete.
        needs = [
            identity
            for identity in outstanding
            if not (
                by_identity.get(identity)
                and by_identity[identity].has_german
                and by_identity[identity].has_english
            )
        ]

        # Most-used words first, so a --gloss-limit spends where it pays.
        def book_count(identity: Identity) -> int:
            return max(lexicon.records[key].book_count for key in keys_by_identity[identity])

        needs.sort(key=lambda identity: (-book_count(identity), identity))

        if options.claude_limit is not None and len(needs) > options.claude_limit:
            result.skipped_by_limit = len(needs) - options.claude_limit
            needs = needs[: options.claude_limit]

        if options.use_claude and needs:
            examples: dict[Identity, str | None] = {}
            for identity in needs:
                record = lexicon.records[keys_by_identity[identity][0]]
                found = example_sentence(record, chapters)
                examples[identity] = found[0] if found else None

            tasks = [_task_for(identity, raw_hits, examples[identity]) for identity in needs]
            result.sent_to_claude = len(tasks)
            result.ran_claude = True

            written, stats = run_claude(
                tasks, options.settings, client=client, on_status=on_status
            )
            result.batch = stats
            for identity, gloss in written.items():
                current = by_identity.get(identity)
                by_identity[identity] = current.merged_with(gloss) if current else gloss

            cache.put_many(
                [by_identity[identity] for identity in written],
                now=now,
                model=options.settings.model,
                prompt_version=PROMPT_VERSION,
                examples={identity: examples.get(identity) for identity in written},
                book_id=book_id,
            )

        # Everything Wiktionary alone settled is worth caching too: the next book
        # then skips the 22.9 GB stream for those lemmas entirely.
        wiktionary_only = [
            by_identity[identity]
            for identity in outstanding
            if identity in by_identity and identity not in (needs if options.use_claude else [])
        ]
        cache.put_many(wiktionary_only, now=now, book_id=book_id)

        for identity, gloss in by_identity.items():
            for key in keys_by_identity[identity]:
                result.glosses[key] = gloss
    finally:
        if owned_cache:
            cache.close()

    return result
