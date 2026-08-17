"""Progress reporting for a batch that can legitimately run for an hour."""

from __future__ import annotations

import sys


def print_batch_status(batch: object) -> None:
    """Keep a long batch from looking like a hang.

    Most batches finish inside an hour and the API's ceiling is 24, so silence
    is the wrong default: it is indistinguishable from a wedged script.
    """
    counts = getattr(batch, "request_counts", None)
    processing = getattr(counts, "processing", "?")
    succeeded = getattr(counts, "succeeded", "?")
    print(
        f"  glossing: {getattr(batch, 'processing_status', '?')} — "
        f"{processing} processing, {succeeded} done",
        file=sys.stderr,
    )
