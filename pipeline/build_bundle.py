#!/usr/bin/env python3
"""Build a Molcajete bundle from a DRM-free EPUB.

    uv run python build_bundle.py sources/book.epub --out ../bundles/

Thin shim; the work lives in `molcajete_book`.
"""

import sys

from molcajete_book.cli import main

if __name__ == "__main__":
    sys.exit(main())
