"""The plain-text build report.

Written next to the bundle. Its job is to answer, before anyone spends money on
glossing in Phase 2 or reads a word of the book: how much would this thing
actually teach me, and did the lemmatizer cope?

`built_at` is passed in rather than read from the clock, so the output is
testable.
"""

from __future__ import annotations

import random
from datetime import datetime

from molcajete_prep.bundle import BuildResult, count_classifications
from molcajete_prep.classify import Classification, LemmaKey, TeachReason, exceeds_cap
from molcajete_prep.glossing.models import GlossSource

TOP_TEACH_LEMMAS = 20
ZIPF_SAMPLE = 12

# Enough to judge the register of a gloss by eye without reading a wall of them.
GLOSS_SAMPLE = 30

# Fixed, so that rebuilding a book produces a byte-identical report. The sample
# is meant to be re-read across builds and compared.
_SAMPLE_SEED = 20260817

_RULE_LABELS = {
    TeachReason.BOOK_COUNT: "bookCount >= {min_book_count}",
    TeachReason.ZIPF: "zipf >= {zipf_threshold}",
    TeachReason.MEXICANISM: "mexicanism && bookCount >= {mexicanism_min_book_count}",
}


def _percentage(part: int, whole: int) -> str:
    if whole == 0:
        return "  0.0%"
    return f"{100 * part / whole:5.1f}%"


def _row(label: str, count: int, whole: int) -> str:
    return f"  {label:<28} {count:>7,}   ({_percentage(count, whole)})"


def _sample_teach_keys(result: BuildResult, teach_keys: list[LemmaKey]) -> list[LemmaKey]:
    """Thirty lemmas worth actually looking at.

    Stratified rather than uniform, because the three interesting populations
    fail differently. The commonest words are the ones a bad gloss hurts most.
    A uniform draw shows what the long tail looks like. The mexicanisms are the
    claim this app exists to make, and the easiest to get wrong.
    """
    glosses = result.glossing.glosses
    rng = random.Random(_SAMPLE_SEED)
    third = GLOSS_SAMPLE // 3

    by_count = sorted(
        teach_keys, key=lambda key: (-result.lexicon.records[key].book_count, key)
    )
    chosen: list[LemmaKey] = list(by_count[:third])

    flagged = [
        key for key in teach_keys if (g := glosses.get(key)) and g.mexicanism
    ]
    chosen += flagged[:third] if len(flagged) <= third else rng.sample(sorted(flagged), third)

    remaining = sorted(set(teach_keys) - set(chosen))
    if remaining:
        chosen += rng.sample(remaining, min(GLOSS_SAMPLE - len(chosen), len(remaining)))

    # Top up from anything left if a population came up short, so the section is
    # always the same size and always comparable between builds.
    if len(chosen) < GLOSS_SAMPLE:
        leftover = sorted(set(teach_keys) - set(chosen))
        chosen += leftover[: GLOSS_SAMPLE - len(chosen)]

    return sorted(set(chosen), key=lambda key: (-result.lexicon.records[key].book_count, key))


def _render_glosses(result: BuildResult, lines: list[str]) -> None:
    glossing = result.glossing
    glosses = glossing.glosses
    teach_keys = [key for key, value in result.classifications.items() if value.is_teach]
    teach_total = len(teach_keys)

    lines.append("GLOSSES")
    if not result.glossed:
        lines.append("  Not glossed (--no-gloss).")
        lines.append(
            "    Every entry carries mexicanism false, so the "
            "'mexicanism && bookCount' rule taught nothing above."
        )
        lines.append("")
        return

    with_german = sum(1 for key in teach_keys if (g := glosses.get(key)) and g.has_german)
    with_english = sum(1 for key in teach_keys if (g := glosses.get(key)) and g.has_english)

    lines.append(f"  {'Teach-set lemmas':<28} {teach_total:>7,}")
    target = "   <- SPEC §12 target: >95%" if teach_total else ""
    goal_met = teach_total and with_german / teach_total >= 0.95
    lines.append(_row("With German gloss", with_german, teach_total) + (target if not goal_met else target + "  MET"))
    lines.append(_row("With English gloss", with_english, teach_total))
    lines.append("")

    for language, label in (("de", "German"), ("en", "English")):
        lines.append(f"  {label} gloss source:")
        counts = {source: 0 for source in GlossSource}
        none = 0
        for key in teach_keys:
            gloss = glosses.get(key)
            source = getattr(gloss, f"{language}_source", None) if gloss else None
            if source is None:
                none += 1
            else:
                counts[source] += 1
        for source, count in counts.items():
            if count:
                lines.append(f"    {source.value:<32} {count:>7,}")
        lines.append(f"    {'none':<32} {none:>7,}")
    lines.append("")

    flagged = [key for key in teach_keys if (g := glosses.get(key)) and g.mexicanism]
    from_claude = sum(
        1
        for key in flagged
        if (g := glosses[key]) and g.de_source is GlossSource.CLAUDE
    )
    lines.append(
        f"  {'Mexicanism flagged':<28} {len(flagged):>7,}"
        f"   (wiktionary {len(flagged) - from_claude:,} · claude {from_claude:,})"
    )

    if glossing.cache_hits:
        lines.append(
            f"  {'Served from the gloss cache':<28} {glossing.cache_hits:>7,}"
            "   (of the whole lexicon, not just the teach set)"
        )
    else:
        lines.append(f"  {'Served from the gloss cache':<28} {'none':>7}   (first book)")

    if glossing.ran_claude:
        batch = glossing.batch
        lines.append(
            f"  {'Sent to Claude':<28} {glossing.sent_to_claude:>7,}"
            f"   (~${batch.estimated_cost():.2f} at batch rates)"
        )
        rejected = batch.not_spanish
        lines.append(
            f"  {'Rejected as not Spanish':<28} {rejected:>7,}"
            f"   of {len(result.lexicon.records):,} lexicon lemmas"
        )
        lines.append(
            "    (es_core_news_sm invents these. This is the measurement that "
            "would justify"
        )
        lines.append("     comparing against es_core_news_md — see CLAUDE.md.)")
        if batch.truncated:
            lines.append(f"  {'Glosses cut down to fit':<28} {batch.truncated:>7,}")
        if batch.missing or batch.errored:
            lines.append(
                f"  {'Unanswered by the batch':<28} {batch.missing:>7,}"
                f"   ({batch.errored} failed requests)"
            )
        if not batch.cache_worked:
            lines.append(
                "  !! The instruction prompt was never served from cache. It has "
                "probably slipped"
            )
            lines.append(
                "     below the 1024-token minimum, which fails silently and "
                "multiplies the bill."
            )
    if glossing.skipped_by_limit:
        lines.append(
            f"  {'Left ungloszed by --gloss-limit':<28} {glossing.skipped_by_limit:>7,}"
        )
    if glossing.de_wiktionary_mode != "verbatim":
        lines.append(f"  German Wiktionary mode: {glossing.de_wiktionary_mode}")
    lines.append("")

    lines.append(f"SAMPLE OF {GLOSS_SAMPLE} GLOSSES")
    lines.append("  (commonest first, then flagged mexicanisms, then a random draw)")
    if not teach_keys:
        lines.append("  (nothing is taught, so there is nothing to sample)")
        lines.append("")
        return

    for key in _sample_teach_keys(result, teach_keys):
        record = result.lexicon.records[key]
        gloss = glosses.get(key)
        de = (gloss.de if gloss else None) or "—"
        en = (gloss.en if gloss else None) or "—"
        source = "".join(
            "W" if s in (GlossSource.DE_WIKTIONARY, GlossSource.EN_WIKTIONARY)
            else "C" if s is GlossSource.CLAUDE
            else "-"
            for s in ((gloss.de_source if gloss else None), (gloss.en_source if gloss else None))
        )
        note = f"  [{gloss.region_note}]" if gloss and gloss.region_note else ""
        mark = " *" if gloss and gloss.mexicanism else "  "
        lines.append(
            f"  {record.lemma:<18} {record.pos:<6} {source}{mark} "
            f"DE {de:<26} EN {en}{note}"
        )
    lines.append("  Source column: W wiktionary, C claude, - none. * mexicanism.")
    lines.append("")


def render_report(
    result: BuildResult,
    *,
    built_at: datetime,
    bundle_bytes: int | None = None,
) -> str:
    book = result.bundle["book"]
    options = result.options
    counts = count_classifications(result.classifications)
    lexicon_size = len(result.lexicon.records)
    proper_nouns = len(result.lexicon.proper_noun_lemmas)
    total_lemmas = lexicon_size + proper_nouns

    lines: list[str] = []

    lines.append("Molcajete bundle report")
    lines.append(f"Book: {book['title']} — {book['author']} ({book['id']})")
    size = f"  ·  Bundle: {bundle_bytes / 1_000_000:.1f} MB" if bundle_bytes else ""
    lines.append(
        f"Built: {built_at.isoformat(timespec='seconds')}"
        f"  ·  schemaVersion {result.bundle['schemaVersion']}{size}"
    )
    lines.append(
        f"Word tokens: {book['totalTokens']:,}"
        f"  ·  Chapters: {len(result.bundle['chapters']):,}"
    )
    lines.append("")

    lines.append("LEMMAS")
    lines.append(
        f"  {'Total distinct lemmas':<28} {total_lemmas:>7,}"
        f"   (lexicon {lexicon_size:,} + {proper_nouns:,} names)"
    )
    lines.append(_row("Teach", counts[Classification.TEACH], total_lemmas))
    lines.append(_row("Gloss only", counts[Classification.GLOSS_ONLY], total_lemmas))
    lines.append(_row("Skipped (PROPN)", proper_nouns, total_lemmas))
    if counts[Classification.ALREADY_KNOWN]:
        lines.append(
            _row("Already known", counts[Classification.ALREADY_KNOWN], total_lemmas)
        )
    lines.append("")

    lines.append("  Teach breakdown (first matching rule):")
    reason_counts = {reason: 0 for reason in TeachReason}
    for classification in result.classifications.values():
        if classification.reason is not None:
            reason_counts[classification.reason] += 1
    for reason, template in _RULE_LABELS.items():
        label = template.format(
            min_book_count=options.min_book_count,
            zipf_threshold=options.zipf_threshold,
            mexicanism_min_book_count=options.mexicanism_min_book_count,
        )
        note = ""
        if reason is TeachReason.MEXICANISM and reason_counts[reason] == 0:
            note = "   <- always 0 until Phase 2 flags mexicanisms"
        lines.append(f"    {label:<34} {reason_counts[reason]:>7,}{note}")
    lines.append("")

    lines.append(f"TOP {TOP_TEACH_LEMMAS} TEACH LEMMAS BY BOOK COUNT")
    teach_keys = [
        key for key, value in result.classifications.items() if value.is_teach
    ]
    teach_keys.sort(
        key=lambda key: (-result.lexicon.records[key].book_count, key)
    )
    if not teach_keys:
        lines.append("  (nothing would be taught)")
    for position, key in enumerate(teach_keys[:TOP_TEACH_LEMMAS], start=1):
        record = result.lexicon.records[key]
        lines.append(
            f"  {position:>3}  {key}  {record.lemma:<18} {record.pos:<6}"
            f" bookCount {record.book_count:>5,}"
            f"   zipf {record.zipf:>4.2f}"
            f"   first ch. {record.first_chapter}"
        )
    lines.append("")

    _render_glosses(result, lines)

    lines.append("DIAGNOSTICS")
    over_cap = [
        index
        for index, vocabulary in enumerate(result.chapter_vocabulary)
        if exceeds_cap(vocabulary, options)
    ]
    lines.append(
        f"  Chapters whose teach set exceeds the {options.max_cards_per_session}-card cap:"
        f" {len(over_cap)} of {len(result.chapter_vocabulary)}"
    )
    lines.append("    (Phase 4 splits these into segments; not enforced here)")

    unknown_to_wordfreq = sorted(
        record.lemma
        for record in result.lexicon.records.values()
        if record.zipf == 0.0
    )
    lines.append(
        f"  Lemmas with zipf 0.00: {len(unknown_to_wordfreq):,}"
        f" of {lexicon_size:,} — wordfreq has never seen these,"
    )
    lines.append("    so they are probably lemmatization noise rather than vocabulary:")
    sample = ", ".join(repr(lemma) for lemma in unknown_to_wordfreq[:ZIPF_SAMPLE])
    lines.append(f"    {sample or '(none)'}")

    if result.known_lemmas:
        lines.append(f"  Seeded known lemmas: {len(result.known_lemmas):,}")
    else:
        lines.append("  No known-lemma seed applied: these are unseeded worst-case counts.")

    return "\n".join(lines) + "\n"
