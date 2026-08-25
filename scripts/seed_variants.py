"""Shared passphrase variant expansion for brainwallet seed generators."""

from __future__ import annotations

from typing import Iterator

MAX_CANDIDATE_LEN = 4096


def expand_variants(
    text: str,
    *,
    nopunct: str | None = None,
    nospaces: str | None = None,
) -> Iterator[str]:
    """Expand one seed into case, reversed, and word-order variants."""
    bases: list[str] = []
    text = text.strip()
    if text:
        bases.append(text)
    if nopunct:
        cleaned = nopunct.strip()
        if cleaned and cleaned not in bases:
            bases.append(cleaned)
    if nospaces:
        compact = nospaces.strip()
        if compact and compact not in bases:
            bases.append(compact)

    seen: set[str] = set()

    def emit(value: str) -> Iterator[str]:
        candidate = value.strip()
        if not candidate or len(candidate) > MAX_CANDIDATE_LEN or candidate in seen:
            return
        seen.add(candidate)
        yield candidate

    for base in bases:
        forms = [
            base,
            base.lower(),
            base.upper(),
            base[::-1],
            base.lower()[::-1],
            base.upper()[::-1],
        ]
        if " " in base:
            reversed_words = " ".join(reversed(base.split()))
            forms.extend(
                [
                    reversed_words,
                    reversed_words.lower(),
                    reversed_words.upper(),
                    reversed_words[::-1],
                    reversed_words.lower()[::-1],
                    reversed_words.upper()[::-1],
                ]
            )
        for form in forms:
            yield from emit(form)


def expand_many(values: Iterator[str]) -> Iterator[str]:
    seen: set[str] = set()
    for value in values:
        for candidate in expand_variants(value):
            if candidate not in seen:
                seen.add(candidate)
                yield candidate
