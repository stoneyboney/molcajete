#!/usr/bin/env python
"""Gloss a small sample of a book with Claude, at two settings, and write the
answers out to read before committing to a whole book's worth of API spend.

    uv run python gloss_trial.py sources/noches.epub --out ../bundles/gloss-trial.txt

Writes no bundle and touches no shared cache.
"""

from __future__ import annotations

import sys

from molcajete_book.trial_cli import main

if __name__ == "__main__":
    sys.exit(main())
