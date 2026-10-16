"""Opt-in development timing for the annotation portal.

Timing is disabled by default and records only operation names and durations.
It never logs credentials, participant IDs, comment text, or query parameters.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager


LOGGER = logging.getLogger("component2.annotation_portal.timing")


def enabled() -> bool:
    return os.getenv("COMPONENT2_DEV_TIMING", "").strip().lower() in {"1", "true", "yes", "on"}


@contextmanager
def measure(operation: str) -> Iterator[None]:
    if not enabled():
        yield
        return

    started = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - started) * 1000
        LOGGER.info("component2_timing operation=%s duration_ms=%.1f", operation, duration_ms)
