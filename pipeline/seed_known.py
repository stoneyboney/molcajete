#!/usr/bin/env python3
"""Turn an Anki export into a known.json of lemma strings.

    uv run python seed_known.py ~/Desktop/Spanisch.txt --out known.json

Thin shim; the work lives in the `molcajete_prep` package.
"""

import sys

from molcajete_prep.cli_seed import main

if __name__ == "__main__":
    sys.exit(main())
