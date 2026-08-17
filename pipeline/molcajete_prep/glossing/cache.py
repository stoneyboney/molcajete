"""The persistent gloss cache.

One SQLite file, keyed by `(lemma, pos)` and shared across every book, so the
second book costs almost nothing to build. It is gitignored: it is derived data,
it grows to tens of megabytes, and it holds nothing that a rebuild could not
produce again.

The key is `(lemma, pos)` rather than the lemma alone for the same reason the
lexicon key is: `bajo` the adjective and `bajo` the preposition take different
German glosses, and a cache that conflated them would hand one book's card the
other book's meaning.

**The provider and model are part of the key too**, because "der Bau" from
Sonnet and "der Bau" from a 12B model running on this laptop are two different
claims that happen to agree, and a row that could not tell them apart would let
a local answer masquerade as a remote one on the next build.

**But the Wiktionary rows are deliberately not scoped to a provider.** They
record what the dictionaries said, which no model wrote, so they carry the empty
provider and every provider reads them. That is not tidiness — it is what keeps
a rebuild warm. Caching the Wiktionary *misses* is the thing that stopped a
rebuild re-streaming 3.1 GB of dumps to rediscover the same three thousand
absences, and scoping those rows per provider would have quietly undone it the
moment anyone passed `--gloss-provider ollama`.

A lookup therefore reads two scopes and layers them: the dictionary row first,
the model row filling what it left empty — the same priority order the live pass
applies, so a cached build and a fresh one agree.

**A cached model gloss was disambiguated against one book's sentence.** Book A
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

# The scope of a row no model wrote: the Wiktionary readers, and the empty rows
# that record "we looked and found nothing". Every provider reads these.
NO_PROVIDER = ""

_SCHEMA = """
CREATE TABLE IF NOT EXISTS glosses (
    lemma           TEXT    NOT NULL,
    pos             TEXT    NOT NULL,
    provider        TEXT    NOT NULL DEFAULT '',
    model           TEXT    NOT NULL DEFAULT '',
    de              TEXT,
    en              TEXT,
    de_source       TEXT,
    en_source       TEXT,
    mexicanism      INTEGER NOT NULL DEFAULT 0,
    region_note     TEXT,
    not_spanish     INTEGER NOT NULL DEFAULT 0,
    corrected_lemma TEXT,
    prompt_version  INTEGER,
    example_es      TEXT,
    book_id         TEXT,
    created_at      TEXT    NOT NULL,
    PRIMARY KEY (lemma, pos, provider, model)
);

CREATE TABLE IF NOT EXISTS sources (
    name        TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    sha256      TEXT NOT NULL,
    entry_count INTEGER,
    fetched_at  TEXT NOT NULL
);
"""

# The pre-provider table, kept only so an existing cache can be read forward.
# `model` was an ordinary column there; here it is half of the scope.
_MIGRATE_TO_PROVIDER_KEY = """
CREATE TABLE glosses_migrated (
    lemma           TEXT    NOT NULL,
    pos             TEXT    NOT NULL,
    provider        TEXT    NOT NULL DEFAULT '',
    model           TEXT    NOT NULL DEFAULT '',
    de              TEXT,
    en              TEXT,
    de_source       TEXT,
    en_source       TEXT,
    mexicanism      INTEGER NOT NULL DEFAULT 0,
    region_note     TEXT,
    not_spanish     INTEGER NOT NULL DEFAULT 0,
    corrected_lemma TEXT,
    prompt_version  INTEGER,
    example_es      TEXT,
    book_id         TEXT,
    created_at      TEXT    NOT NULL,
    PRIMARY KEY (lemma, pos, provider, model)
);

INSERT OR REPLACE INTO glosses_migrated
SELECT
    lemma, pos,
    -- Before the port there was one model provider, so a row that names a
    -- model is a Claude row and a row that does not is a dictionary row.
    CASE WHEN COALESCE(model, '') = '' THEN '' ELSE 'claude' END,
    COALESCE(model, ''),
    de, en, de_source, en_source, mexicanism, region_note, not_spanish,
    corrected_lemma, prompt_version, example_es, book_id, created_at
FROM glosses;

DROP TABLE glosses;
ALTER TABLE glosses_migrated RENAME TO glosses;
"""


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

    Writes are last-one-wins on `(lemma, pos, provider, model)`. A later book
    replacing an earlier book's gloss is intentional — the newer row carries the
    newer `example_es`, so the provenance stays truthful — but note that it does
    not retroactively change an already-built bundle.
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
        self._migrate()
        self._connection.commit()

    def _migrate(self) -> None:
        """Carry a pre-provider cache forward rather than making it worthless.

        The alternative was to delete the file and rebuild, which on this
        machine means re-streaming 3.1 GB of Wiktionary dumps to rediscover
        glosses that are already correct. SQLite cannot add a column to a
        primary key, so the table is rebuilt in place.
        """
        columns = {
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(glosses)").fetchall()
        }
        if not columns or "provider" in columns:
            return
        self._connection.executescript(_MIGRATE_TO_PROVIDER_KEY)
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

    def get(
        self,
        lemma: str,
        pos: str,
        *,
        provider: str = NO_PROVIDER,
        model: str = "",
    ) -> Gloss | None:
        found = self.get_many([(lemma, pos)], provider=provider, model=model)
        return found.get((lemma, pos))

    def get_many(
        self,
        identities: Iterable[Identity],
        *,
        provider: str = NO_PROVIDER,
        model: str = "",
    ) -> dict[Identity, Gloss]:
        """Look up many at once, in the dictionary scope and one model's scope.

        Both scopes come back in one query and are layered dictionary-first, so
        a cached lookup reproduces the priority order of a live pass: Wiktionary
        fills what it can, the model fills the rest. Asking for no provider —
        the default — reads only the dictionary rows, which is what an offline
        build wants.

        Chunked because SQLite caps a statement at 999 host parameters by
        default and a book asks for thousands.
        """
        wanted = list(dict.fromkeys(identities))
        scoped = provider != NO_PROVIDER
        by_scope: dict[Identity, dict[str, Gloss]] = {}

        # Four parameters per identity, so the chunk is smaller than it was.
        for start in range(0, len(wanted), 200):
            chunk = wanted[start : start + 200]
            placeholders = ",".join("(?,?)" for _ in chunk)
            flat: list[str] = [value for identity in chunk for value in identity]
            clause = "provider = ?" if not scoped else "(provider = ? OR (provider = ? AND model = ?))"
            scope_values = [NO_PROVIDER] if not scoped else [NO_PROVIDER, provider, model]
            rows = self._connection.execute(
                f"SELECT * FROM glosses WHERE (lemma, pos) IN ({placeholders})"
                f" AND {clause}",
                flat + scope_values,
            ).fetchall()
            for row in rows:
                identity = (row["lemma"], row["pos"])
                slot = "source" if row["provider"] == NO_PROVIDER else "model"
                by_scope.setdefault(identity, {})[slot] = _row_to_gloss(row)

        found: dict[Identity, Gloss] = {}
        for identity, scopes in by_scope.items():
            source, from_model = scopes.get("source"), scopes.get("model")
            if source and from_model:
                found[identity] = source.merged_with(from_model)
            else:
                found[identity] = source or from_model  # type: ignore[assignment]

        return found

    def put(
        self,
        gloss: Gloss,
        *,
        now: datetime,
        provider: str = NO_PROVIDER,
        model: str | None = None,
        prompt_version: int | None = None,
        example_es: str | None = None,
        book_id: str | None = None,
    ) -> None:
        self.put_many(
            [gloss],
            now=now,
            provider=provider,
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
        provider: str = NO_PROVIDER,
        model: str | None = None,
        prompt_version: int | None = None,
        examples: Mapping[Identity, str | None] | None = None,
        book_id: str | None = None,
    ) -> None:
        """Write glosses, replacing any existing row in the same scope.

        The default scope is the dictionary one, because that is the write with
        no model behind it. A provider passes its own name and model, and its
        rows sit alongside every other provider's rather than over them.

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
                provider,
                model or "",
                gloss.de,
                gloss.en,
                gloss.de_source.value if gloss.de_source else None,
                gloss.en_source.value if gloss.en_source else None,
                int(gloss.mexicanism),
                gloss.region_note,
                int(gloss.not_spanish),
                gloss.corrected_lemma,
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
                lemma, pos, provider, model, de, en, de_source, en_source,
                mexicanism, region_note, not_spanish, corrected_lemma,
                prompt_version, example_es, book_id, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            rows,
        )
        self._connection.commit()

    def forget(
        self,
        identities: Iterable[Identity],
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> int:
        """Drop rows so they are fetched again. Backs `--regloss`.

        Every scope by default, dictionary rows included: `--regloss` is what
        you run after kaikki refreshes its dumps, so leaving the Wiktionary rows
        in place would answer half the question from stale data.
        """
        wanted = list(dict.fromkeys(identities))
        if not wanted:
            return 0

        if provider is None:
            statement = "DELETE FROM glosses WHERE lemma = ? AND pos = ?"
            rows: list[tuple] = wanted
        else:
            statement = (
                "DELETE FROM glosses WHERE lemma = ? AND pos = ?"
                " AND provider = ? AND model = ?"
            )
            rows = [(*identity, provider, model or "") for identity in wanted]

        cursor = self._connection.executemany(statement, rows)
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
