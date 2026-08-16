"""The plain-text build report.

Written next to the bundle. Its job is to answer, before anyone spends money on
glossing in Phase 2 or reads a word of the book: how much would this thing
actually teach me, and did the lemmatizer cope?

`built_at` is passed in rather than read from the clock, so the output is
testable.
"""

from __future__ import annotations

from datetime import datetime

from molcajete_prep.bundle import BuildResult, count_classifications
from molcajete_prep.classify import Classification, TeachReason, exceeds_cap

TOP_TEACH_LEMMAS = 20
ZIPF_SAMPLE = 12

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
