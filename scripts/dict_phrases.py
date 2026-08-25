"""Generate multi-word dictionary phrases for brainwallet seed lists."""

from __future__ import annotations

import itertools
from typing import Iterator

# Top-N most common words used as the pool for each phrase length.
# Pools are frequency-ordered word lists (see fetch_dictionaries.py).
DEFAULT_PHRASE_TOP_N: dict[int, int] = {
    2: 500,
    3: 80,
    4: 35,
    5: 18,
}

DEFAULT_PHRASE_LENGTHS: tuple[int, ...] = (2, 3, 4, 5)


def iter_dictionary_phrases(
    words: list[str],
    *,
    phrase_lengths: tuple[int, ...] = DEFAULT_PHRASE_LENGTHS,
    top_n_by_length: dict[int, int] | None = None,
) -> Iterator[str]:
    """Yield space-separated word phrases from the top of a frequency-ordered list."""
    limits = top_n_by_length or DEFAULT_PHRASE_TOP_N
    for length in phrase_lengths:
        pool_size = limits.get(length, 0)
        if pool_size <= 0 or length < 2:
            continue
        pool = words[:pool_size]
        if len(pool) < length:
            continue
        for combo in itertools.product(pool, repeat=length):
            yield " ".join(combo)


def estimate_phrase_count(top_n_by_length: dict[int, int] | None = None) -> int:
    limits = top_n_by_length or DEFAULT_PHRASE_TOP_N
    total = 0
    for length, pool_size in limits.items():
        if pool_size >= length:
            total += pool_size**length
    return total
