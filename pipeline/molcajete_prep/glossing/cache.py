"""The persistent gloss cache.

One SQLite file, keyed by `(lemma, pos)` and shared across every book, so the
second book costs almost nothing to build. It is gitignored: it is derived data,
it grows to tens of megabytes, and it holds nothing that a rebuild could not
produce again.

The key is `(lemma, pos)` rather than the lemma alone for the same reason the
lexicon key is: `bajo` the adjective and `bajo` the preposition take different
German glosses, and a cache that conflated them would hand one book's card the
other book's meaning.

**A cached Claude gloss was disambiguated against one book's sentence.** Book A
uses `banco` for the riverbank, book B for the bench, and reusing A's gloss in B
is wrong. Reuse is still the default — that is what makes book two cheap — so
the row records the sentence and the book that produced it, the report counts
how many of a build's glosses came from cache rather than fresh, and `--regloss`
forces the pass to run again. The trade is visible rather than silent.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path

from molcajete_prep.glossing.models import Gloss, GlossSource

# pipeline/molcajete_prep/glossing/cache.py -> pipeline/
_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR = _PIPELINE_ROOT / "cache"
DEFAULT_CACHE_PATH = DEFAULT_CACHE_DIR / "glosses.sqlite3"

Identity = tuple[str, str]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS glosses (
    lemma           TEXT    NOT NULL,
    pos             TEXT    NOT NULL,
    de              TEXT,
    en              TEXT,
    de_source       TEXT,
    en_source       TEXT,
    mexicanism      INTEGER NOT NULL DEFAULT 0,
    region_note     TEXT,
    not_spanish     INTEGER NOT NULL DEFAULT 0,
    corrected_lemma TEXT,
    model           TEXT,
    prompt_version  INTEGER,
    example_es      TEXT,
    book_id         TEXT,
    created_at      TEXT    NOT NULL,
    PRIMARY KEY (lemma, pos)
);

CREATE TABLE IF NOT EXISTS sources (
    name        TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    sha256      TEXT NOT NULL,
    entry_count INTEGER,
    fetched_at  TEXT NOT NULL
);
"""

_COLUMNS = (
    "lemma",
    "pos",
    "de",
    "en",
    "de_source",
    "en_source",
    "mexicanism",
    "region_note",
    "not_spanish",
    "corrected_lemma",
)


def _source_of(value: str | None) -> GlossSource | None:
    return GlossSource(value) if value else None


def _row_to_gloss(row: sqlite3.Row) -> Gloss:
    return Gloss(
        lemma=row["lemma"],
        pos=row["pos"],
        de=row["de"],
        en=row["en"],
        de_source=_source_of(row["de_source"]),
        en_source=_source_of(row["en_source"]),
        mexicanism=bool(row["mexicanism"]),
        region_note=row["region_note"],
        not_spanish=bool(row["not_spanish"]),
        corrected_lemma=row["corrected_lemma"],
    )


class GlossCache:
    """A gloss store that outlives one book.

    Writes are last-one-wins on `(lemma, pos)`. A later book replacing an
    earlier book's gloss is intentional — the newer row carries the newer
    `example_es`, so the provenance stays truthful — but note that it does not
    retroactively change an already-built bundle.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        # Resolved here rather than as a default argument so that the module
        # global can be redirected — the test suite points it at a temporary
        # file so a test run can never read or write the real cache.
        self.path = Path(DEFAULT_CACHE_PATH if path is None else path)
        if self.path.name != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(_SCHEMA)
        self._connection.commit()

    @classmethod
    def in_memory(cls) -> GlossCache:
        """A cache that vanishes when the process does.

        Used by the trial script: a 200-lemma sample run at experimental
        settings must not seed the store that every later book reads from.
        """
        return cls(":memory:")

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> GlossCache:
        return self

    def __exit__(self, *exception: object) -> None:
        self.close()

    # -- glosses ---------------------------------------------------------

    def get(self, lemma: str, pos: str) -> Gloss | None:
        row = self._connection.execute(
            "SELECT * FROM glosses WHERE lemma = ? AND pos = ?", (lemma, pos)
        ).fetchone()
        return _row_to_gloss(row) if row else None

    def get_many(self, identities: Iterable[Identity]) -> dict[Identity, Gloss]:
        """Look up many at once.

        Chunked because SQLite caps a statement at 999 host parameters by
        default and a book asks for thousands.
        """
        wanted = list(dict.fromkeys(identities))
        found: dict[Identity, Gloss] = {}

        for start in range(0, len(wanted), 400):
            chunk = wanted[start : start + 400]
            placeholders = ",".join("(?,?)" for _ in chunk)
            flat = [value for identity in chunk for value in identity]
            rows = self._connection.execute(
                f"SELECT * FROM glosses WHERE (lemma, pos) IN ({placeholders})", flat
            ).fetchall()
            for row in rows:
                found[(row["lemma"], row["pos"])] = _row_to_gloss(row)

        return found

    def put(
        self,
        gloss: Gloss,
        *,
        now: datetime,
        model: str | None = None,
        prompt_version: int | None = None,
        example_es: str | None = None,
        book_id: str | None = None,
    ) -> None:
        self.put_many(
            [gloss],
            now=now,
            model=model,
            prompt_version=prompt_version,
            examples={(gloss.lemma, gloss.pos): example_es} if example_es else None,
            book_id=book_id,
        )

    def put_many(
        self,
        glosses: Sequence[Gloss],
        *,
        now: datetime,
        model: str | None = None,
        prompt_version: int | None = None,
        examples: Mapping[Identity, str | None] | None = None,
        book_id: str | None = None,
    ) -> None:
        """Write glosses, replacing any existing row for the same identity.

        `now` is passed in rather than read from the clock so tests can assert
        on the stored timestamp, matching how the report takes `built_at`.
        """
        if not glosses:
            return

        timestamp = now.isoformat(timespec="seconds")
        examples = examples or {}
        rows = [
            (
                gloss.lemma,
                gloss.pos,
                gloss.de,
                gloss.en,
                gloss.de_source.value if gloss.de_source else None,
                gloss.en_source.value if gloss.en_source else None,
                int(gloss.mexicanism),
                gloss.region_note,
                int(gloss.not_spanish),
                gloss.corrected_lemma,
                model,
                prompt_version,
                examples.get((gloss.lemma, gloss.pos)),
                book_id,
                timestamp,
            )
            for gloss in glosses
        ]

        self._connection.executemany(
            """
            INSERT OR REPLACE INTO glosses (
                lemma, pos, de, en, de_source, en_source, mexicanism,
                region_note, not_spanish, corrected_lemma, model,
                prompt_version, example_es, book_id, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            rows,
        )
        self._connection.commit()

    def forget(self, identities: Iterable[Identity]) -> int:
        """Drop rows so they are fetched again. Backs `--regloss`."""
        wanted = list(dict.fromkeys(identities))
        if not wanted:
            return 0
        cursor = self._connection.executemany(
            "DELETE FROM glosses WHERE lemma = ? AND pos = ?", wanted
        )
        self._connection.commit()
        return cursor.rowcount

    def count(self) -> int:
        return self._connection.execute("SELECT COUNT(*) FROM glosses").fetchone()[0]

    # -- source extracts -------------------------------------------------

    def record_source(
        self,
        name: str,
        *,
        url: str,
        sha256: str,
        entry_count: int | None,
        now: datetime,
    ) -> None:
        self._connection.execute(
            """
            INSERT OR REPLACE INTO sources (name, url, sha256, entry_count, fetched_at)
            VALUES (?,?,?,?,?)
            """,
            (name, url, sha256, entry_count, now.isoformat(timespec="seconds")),
        )
        self._connection.commit()

    def source(self, name: str) -> sqlite3.Row | None:
        return self._connection.execute(
            "SELECT * FROM sources WHERE name = ?", (name,)
        ).fetchone()
