#!/usr/bin/env python3
"""Write a synthetic Anki export of the commonest Spanish words.

    uv run python make_test_deck.py --count 1000

For exercising `seed_known.py` and the app's import without touching a real
deck. Thin shim; the word list and the work live in the `molcajete_prep`
package, because nothing about either is book-shaped.
"""

import sys

from molcajete_prep.make_test_deck import main

if __name__ == "__main__":
    sys.exit(main())
