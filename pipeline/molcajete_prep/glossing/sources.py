"""Fetching and streaming the kaikki.org Wiktionary extracts.

kaikki.org publishes wiktextract output per Wiktionary *edition*, not per target
language. There is no "Spanish words from English Wiktionary" download: the
English edition is one 22.9 GB dump covering hundreds of languages, and Spanish
is a slice of it. The per-language postprocessed files that do exist
(`kaikki.org-dictionary-Spanish.jsonl`) are marked DEPRECATED on kaikki.org and
scheduled for removal, so this module reads the whole-edition dumps instead. A
one-time download beats a source that disappears and breaks the third book
silently.

Both dumps are streamed, never loaded: `iter_spanish_records` decompresses line
by line and hands back one dict at a time. A cheap byte test on the raw line
skips the ~99% of the English dump that is not Spanish before paying for
`json.loads`.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import sys
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from molcajete_prep.glossing.cache import DEFAULT_CACHE_DIR, GlossCache

KAIKKI = "https://kaikki.org/dictionary/"

# wiktextract writes `"lang_code": "es"`, but a formatter change would silently
# empty every gloss, so the compact spelling is accepted too. The test is a
# pre-filter only: English entries carry Spanish *translations* inline and match
# it, so `iter_spanish_records` re-checks the parsed top-level field.
_SPANISH_MARKERS = (b'"lang_code": "es"', b'"lang_code":"es"')


@dataclass(frozen=True)
class Source:
    """One downloadable extract."""

    name: str
    url: str
    filename: str
    description: str

    def path(self, directory: Path) -> Path:
        return directory / self.filename


EN_WIKTIONARY = Source(
    name="en-wiktionary",
    url=KAIKKI + "raw-wiktextract-data.jsonl.gz",
    filename="en-wiktextract.jsonl.gz",
    description="English Wiktionary, all languages (2.6 GB compressed)",
)

DE_WIKTIONARY = Source(
    name="de-wiktionary",
    url=KAIKKI + "downloads/de/de-extract.jsonl.gz",
    filename="de-wiktextract.jsonl.gz",
    description="German Wiktionary, all languages (288 MB compressed)",
)

SOURCES = (EN_WIKTIONARY, DE_WIKTIONARY)
DEFAULT_EXTRACT_DIR = DEFAULT_CACHE_DIR / "kaikki"


class SourceUnavailableError(RuntimeError):
    """An extract could not be downloaded.

    Raised loudly rather than skipped: a silent fallthrough would produce a
    bundle with no glosses and a report claiming Wiktionary simply had poor
    coverage.
    """


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _report_progress(downloaded: int, total: int, name: str) -> None:
    if total <= 0:
        print(f"\r  {name}: {downloaded / 1e6:,.0f} MB", end="", file=sys.stderr)
        return
    share = 100 * downloaded / total
    print(
        f"\r  {name}: {downloaded / 1e6:,.0f} / {total / 1e6:,.0f} MB ({share:4.1f}%)",
        end="",
        file=sys.stderr,
    )


def download(source: Source, directory: Path, *, quiet: bool = False) -> Path:
    """Download one extract, writing through a temporary file.

    The temporary file matters: an interrupted download that left a truncated
    `.jsonl.gz` in place would look complete on the next run and yield a partial
    lexicon with no error.
    """
    directory.mkdir(parents=True, exist_ok=True)
    destination = source.path(directory)
    partial = destination.with_suffix(destination.suffix + ".part")

    try:
        with urllib.request.urlopen(source.url) as response:  # noqa: S310 - fixed https URL
            total = int(response.headers.get("Content-Length") or 0)
            downloaded = 0
            with partial.open("wb") as handle:
                while chunk := response.read(1024 * 1024):
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if not quiet and downloaded % (32 * 1024 * 1024) < 1024 * 1024:
                        _report_progress(downloaded, total, source.name)
    except urllib.error.HTTPError as error:
        partial.unlink(missing_ok=True)
        raise SourceUnavailableError(
            f"{source.name}: {source.url} returned HTTP {error.code}. "
            "kaikki.org reorganizes its download paths from time to time — check "
            f"{KAIKKI}rawdata.html for the current filename."
        ) from error
    except urllib.error.URLError as error:
        partial.unlink(missing_ok=True)
        raise SourceUnavailableError(
            f"{source.name}: could not reach {source.url} ({error.reason})"
        ) from error

    if not quiet:
        print(file=sys.stderr)
    shutil.move(partial, destination)
    return destination


def fetch(
    source: Source,
    *,
    directory: Path = DEFAULT_EXTRACT_DIR,
    cache: GlossCache | None = None,
    now: datetime | None = None,
    force: bool = False,
    quiet: bool = False,
) -> Path:
    """Ensure `source` is on disk, and record what was fetched.

    Re-running is a no-op: an extract already present with the checksum recorded
    in the cache is left alone. `force` re-downloads regardless, which is how a
    weekly kaikki refresh gets picked up.
    """
    destination = source.path(directory)
    now = now or datetime.now()

    if destination.exists() and not force:
        recorded = cache.source(source.name) if cache else None
        if recorded and recorded["sha256"] == _sha256(destination):
            if not quiet:
                print(f"  {source.name}: already present, skipping", file=sys.stderr)
            return destination

    if not quiet:
        print(f"  {source.name}: {source.description}", file=sys.stderr)
    download(source, directory, quiet=quiet)

    if cache is not None:
        cache.record_source(
            source.name,
            url=source.url,
            sha256=_sha256(destination),
            entry_count=None,
            now=now,
        )
    return destination


def looks_spanish(line: bytes) -> bool:
    """Cheap pre-filter over a raw line, before paying for `json.loads`.

    Conservative in the right direction: it never rejects a Spanish record, and
    the false positives it does admit — English entries whose translation lists
    mention Spanish — are dropped by the parsed check that follows.
    """
    return any(marker in line for marker in _SPANISH_MARKERS)


def iter_spanish_records(path: Path) -> Iterator[dict]:
    """Stream the Spanish entries out of a whole-edition extract.

    Malformed lines are skipped rather than fatal. These dumps are machine
    generated from a wiki that anyone can edit, and one unparseable line in
    twenty million should not cost a book its glosses.
    """
    with gzip.open(path, "rb") as handle:
        for line in handle:
            if not looks_spanish(line):
                continue
            try:
                record = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            if record.get("lang_code") == "es" and record.get("word"):
                yield record


def main(argv: list[str] | None = None) -> int:
    """`python -m molcajete_prep.glossing.sources --fetch`"""
    import argparse

    parser = argparse.ArgumentParser(
        prog="molcajete_prep.glossing.sources",
        description="Download the kaikki.org Wiktionary extracts the glossing pass reads.",
    )
    parser.add_argument("--fetch", action="store_true", help="download any missing extract")
    parser.add_argument(
        "--force", action="store_true", help="re-download even if already present"
    )
    parser.add_argument(
        "--dir", default=str(DEFAULT_EXTRACT_DIR), help="where to keep the extracts"
    )
    args = parser.parse_args(argv)

    directory = Path(args.dir)
    with GlossCache() as cache:
        for source in SOURCES:
            destination = source.path(directory)
            if not args.fetch:
                state = "present" if destination.exists() else "MISSING"
                print(f"{source.name:<16} {state:<8} {destination}")
                continue
            fetch(source, directory=directory, cache=cache, force=args.force)

    if not args.fetch:
        print("\nRun with --fetch to download anything missing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
