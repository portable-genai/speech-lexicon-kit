"""Canonical encoding and digests: the mechanics of proving a run replayed.

Determinism you cannot demonstrate is a claim, not a property. Every consumer of this kit
owes someone an answer to "would you get the same scorecard if you ran it again next quarter,
on another host?", and the cheapest honest answer is a digest over a canonical encoding of
the findings, recorded with the run and compared on replay.

The encoding is fixed here so two repos comparing digests are comparing the same thing:
JSON with sorted keys, no insignificant whitespace, enums as their values, datetimes as
ISO 8601, tuples as arrays, encoded UTF-8. It is deliberately narrow: dataclass instances,
enums, datetimes, scalars and containers. Anything else raises, because falling back to
``str(obj)`` would let an object with a memory address in its repr into the digest and make
the replay fail for a reason that is not a difference in the finding.

Nothing here reads a clock or a file. ``digest`` is a pure function of the value handed to
it.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
from datetime import date, datetime
from typing import Any

__all__ = [
    "ReplayEncodingError",
    "canonical_bytes",
    "canonical_json",
    "digest",
    "to_jsonable",
]

DIGEST_PREFIX = "sha256:"


class ReplayEncodingError(TypeError):
    """Raised when a value has no canonical encoding, rather than being stringified into one."""


def to_jsonable(value: Any) -> Any:
    """Convert ``value`` into JSON-safe Python, refusing anything without a stable encoding."""
    if isinstance(value, enum.Enum):
        return to_jsonable(value.value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        # NaN and the infinities have no JSON representation and would round-trip through
        # non-standard literals, so they can never enter a digest.
        if value != value or value in (float("inf"), float("-inf")):
            raise ReplayEncodingError(f"{value!r} has no canonical JSON encoding")
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_jsonable(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        # Sets have no order, so they are encoded sorted by their own canonical form; two
        # runs that built the same set in a different order therefore digest identically.
        return sorted((to_jsonable(item) for item in value), key=canonical_json)
    raise ReplayEncodingError(
        f"no canonical encoding for {type(value).__name__}; convert it explicitly rather than "
        f"letting an unstable repr into a replay digest"
    )


def canonical_json(value: Any) -> str:
    """Encode ``value`` as canonical JSON: sorted keys, no padding, non-ASCII kept as text.

    Non-ASCII is emitted literally rather than escaped, so a Japanese phrase reads as itself
    in a golden file that a reviewer has to be able to check by eye.
    """
    return json.dumps(
        to_jsonable(value),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_bytes(value: Any) -> bytes:
    """The canonical JSON of ``value`` as UTF-8 bytes: what a digest is actually taken over."""
    return canonical_json(value).encode("utf-8")


def digest(value: Any) -> str:
    """A stable ``sha256:...`` digest over ``value``'s canonical encoding."""
    return DIGEST_PREFIX + hashlib.sha256(canonical_bytes(value)).hexdigest()
