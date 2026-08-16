#!/usr/bin/env python3
"""Build a Molcajete bundle from a DRM-free EPUB.

    uv run python build_bundle.py sources/book.epub --out ../bundles/

Thin shim; the work lives in `molcajete_prep`.
"""

import sys

from molcajete_prep.cli import main

if __name__ == "__main__":
    sys.exit(main())
