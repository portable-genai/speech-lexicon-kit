"""The canonical encoding and digest: what "byte-identical" is actually measured with."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

import pytest

from speech_lexicon_kit.replay import (
    ReplayEncodingError,
    canonical_bytes,
    canonical_json,
    digest,
    to_jsonable,
)


class Colour(StrEnum):
    RED = "red"


@dataclass(frozen=True, slots=True)
class Inner:
    label: str
    score: float


@dataclass(frozen=True, slots=True)
class Outer:
    name: str
    when: datetime
    colour: Colour
    parts: tuple[Inner, ...]
    optional: str | None = None


SAMPLE = Outer(
    name="example",
    when=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
    colour=Colour.RED,
    parts=(Inner(label="a", score=0.5), Inner(label="b", score=1.0)),
)


def test_dataclasses_encode_field_by_field():
    assert to_jsonable(SAMPLE) == {
        "name": "example",
        "when": "2026-03-01T12:00:00+00:00",
        "colour": "red",
        "parts": [{"label": "a", "score": 0.5}, {"label": "b", "score": 1.0}],
        "optional": None,
    }


def test_enums_encode_as_their_value_not_the_member():
    assert to_jsonable(Colour.RED) == "red"
    assert canonical_json(Colour.RED) == '"red"'


def test_dates_and_datetimes_encode_as_iso_8601():
    assert to_jsonable(date(2026, 3, 1)) == "2026-03-01"


def test_tuples_and_lists_encode_alike_so_a_refactor_does_not_move_a_digest():
    assert canonical_json((1, 2)) == canonical_json([1, 2])


def test_keys_are_sorted_so_field_order_never_moves_a_digest():
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_sets_encode_in_a_stable_order():
    assert canonical_json({"z", "a", "m"}) == canonical_json({"m", "z", "a"})


def test_non_ascii_stays_readable_so_a_golden_file_can_be_reviewed_by_eye():
    assert canonical_json({"phrase": "録音されます"}) == '{"phrase":"録音されます"}'
    assert "録音" in canonical_bytes({"phrase": "録音されます"}).decode("utf-8")


def test_a_digest_is_stable_and_prefixed():
    first = digest(SAMPLE)
    assert first.startswith("sha256:")
    assert first == digest(SAMPLE)


def test_a_digest_moves_when_any_field_moves():
    changed = Outer(
        name="example",
        when=SAMPLE.when,
        colour=Colour.RED,
        parts=(Inner(label="a", score=0.5), Inner(label="b", score=1.000001)),
        optional=None,
    )
    assert digest(changed) != digest(SAMPLE)


def test_an_unencodable_object_raises_rather_than_being_stringified():
    # str(obj) would let a memory address into a digest and make replay fail for a reason
    # that is not a difference in the finding.
    class Opaque:
        pass

    with pytest.raises(ReplayEncodingError, match="no canonical encoding"):
        canonical_json(Opaque())


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_floats_are_refused(value):
    with pytest.raises(ReplayEncodingError, match="no canonical JSON encoding"):
        canonical_json({"score": value})


def test_booleans_are_not_confused_with_integers():
    assert canonical_json({"flag": True}) == '{"flag":true}'
