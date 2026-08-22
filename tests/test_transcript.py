"""The transcript value types: invariants, timing resolution and the diarization join."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from speech_lexicon_kit.transcript import (
    ChannelRole,
    RedactionSpan,
    SpeakerSegment,
    SpeakerTurn,
    Transcript,
    TranscriptError,
    WordOffset,
    merge_diarization,
    span_timing,
)


def _turn(index: int = 0, text: str = "hello there", **kwargs) -> SpeakerTurn:
    defaults = {"speaker_id": "spk-1", "role": ChannelRole.AGENT}
    return SpeakerTurn(index=index, text=text, **(defaults | kwargs))


def test_roles_are_a_closed_taxonomy_that_accepts_wire_strings():
    assert ChannelRole("agent") is ChannelRole.AGENT
    assert ChannelRole("AGENT") is ChannelRole.AGENT
    assert ChannelRole.CUSTOMER == "customer"
    with pytest.raises(ValueError):
        ChannelRole("supervisor")


def test_word_offsets_reject_impossible_spans_and_timings():
    with pytest.raises(TranscriptError, match="must not precede its start"):
        WordOffset(text="x", char_start=5, char_end=2)
    with pytest.raises(TranscriptError, match="non-negative"):
        WordOffset(text="x", char_start=0, char_end=1, start_ms=-1)
    with pytest.raises(TranscriptError, match="must not precede start_ms"):
        WordOffset(text="x", char_start=0, char_end=1, start_ms=900, end_ms=100)
    with pytest.raises(TranscriptError, match=r"confidence must be in \[0, 1\]"):
        WordOffset(text="x", char_start=0, char_end=1, confidence=1.5)


def test_a_word_offset_may_not_run_past_its_turn():
    with pytest.raises(TranscriptError, match="runs past"):
        _turn(text="short", words=(WordOffset(text="short", char_start=0, char_end=99),))


def test_turn_indices_must_equal_their_position():
    # A citation of "turn 7" has to resolve without a lookup table, in every repo.
    with pytest.raises(TranscriptError, match="indices must match position"):
        Transcript(
            transcript_id="T-EXAMPLE-001",
            locale="en-SG",
            turns=(_turn(index=0), _turn(index=5)),
        )


def test_a_transcript_needs_a_locale_because_matching_is_locale_sensitive():
    with pytest.raises(TranscriptError, match="locale must be non-empty"):
        Transcript(transcript_id="T-EXAMPLE-001", locale="  ", turns=(_turn(),))


def test_naive_timestamps_are_refused():
    with pytest.raises(TranscriptError, match="timezone-aware"):
        Transcript(
            transcript_id="T-EXAMPLE-001",
            locale="en-SG",
            turns=(_turn(),),
            started_at=datetime(2026, 3, 1, 12, 0),
        )


def test_a_transcript_is_open_until_it_ends():
    open_transcript = Transcript(transcript_id="T-EXAMPLE-002", locale="en-SG", turns=(_turn(),))
    assert open_transcript.is_open
    closed = Transcript(
        transcript_id="T-EXAMPLE-002",
        locale="en-SG",
        turns=(_turn(),),
        started_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        ended_at=datetime(2026, 3, 1, 12, 4, tzinfo=UTC),
    )
    assert not closed.is_open


def test_redactions_must_land_inside_the_turn_they_cite():
    with pytest.raises(TranscriptError, match="cites turn"):
        Transcript(
            transcript_id="T-EXAMPLE-003",
            locale="en-SG",
            turns=(_turn(),),
            redactions=(RedactionSpan(turn_index=4, char_start=0, char_end=1, info_type="EMAIL"),),
        )
    with pytest.raises(TranscriptError, match="runs past"):
        Transcript(
            transcript_id="T-EXAMPLE-003",
            locale="en-SG",
            turns=(_turn(text="short"),),
            redactions=(RedactionSpan(turn_index=0, char_start=0, char_end=99, info_type="EMAIL"),),
        )


def test_a_redaction_span_carries_a_label_not_a_value():
    with pytest.raises(TranscriptError, match="non-empty label"):
        RedactionSpan(turn_index=0, char_start=0, char_end=3, info_type="  ")


def test_a_turn_may_override_the_transcript_locale_for_code_switching():
    transcript = Transcript(
        transcript_id="T-EXAMPLE-004",
        locale="ja-JP",
        turns=(_turn(index=0), _turn(index=1, language="en-SG")),
    )
    assert transcript.locale_for(transcript.turn(0)) == "ja-JP"
    assert transcript.locale_for(transcript.turn(1)) == "en-SG"


def test_missing_turns_raise_rather_than_index_error():
    transcript = Transcript(transcript_id="T-EXAMPLE-005", locale="en-SG", turns=(_turn(),))
    with pytest.raises(TranscriptError, match="no turn 3"):
        transcript.turn(3)


def test_span_timing_uses_every_overlapping_word():
    turn = _turn(
        text="please confirm your date of birth",
        words=(
            WordOffset(text="please", char_start=0, char_end=6, start_ms=100, end_ms=400),
            WordOffset(text="confirm", char_start=7, char_end=14, start_ms=400, end_ms=900),
            WordOffset(text="birth", char_start=28, char_end=33, start_ms=1800, end_ms=2200),
        ),
    )
    assert span_timing(turn, 0, 14) == (100, 900)
    # A span starting mid-token still reports when that token was spoken.
    assert span_timing(turn, 9, 12) == (400, 900)


def test_span_timing_reports_unknown_rather_than_guessing():
    # Substituting the turn's own bounds would make an unverifiable deadline look checked.
    turn = _turn(text="no offsets here", start_ms=0, end_ms=5000)
    assert span_timing(turn, 0, 5) == (None, None)


def test_merge_diarization_assigns_the_largest_overlap():
    turns = (
        _turn(index=0, text="first", start_ms=0, end_ms=1000, role=ChannelRole.UNKNOWN),
        _turn(index=1, text="second", start_ms=1000, end_ms=2000, role=ChannelRole.UNKNOWN),
    )
    segments = (
        SpeakerSegment(speaker_id="spk-a", start_ms=0, end_ms=900, role=ChannelRole.AGENT),
        SpeakerSegment(speaker_id="spk-b", start_ms=900, end_ms=2100, role=ChannelRole.CUSTOMER),
    )
    merged = merge_diarization(turns, segments)
    assert [(t.speaker_id, t.role) for t in merged] == [
        ("spk-a", ChannelRole.AGENT),
        ("spk-b", ChannelRole.CUSTOMER),
    ]


def test_merge_diarization_leaves_untimed_or_unmatched_turns_alone():
    turns = (
        _turn(index=0, text="untimed", speaker_id="spk-original"),
        _turn(
            index=1,
            text="timed but far away",
            speaker_id="spk-original",
            start_ms=90_000,
            end_ms=91_000,
        ),
    )
    segments = (SpeakerSegment(speaker_id="spk-a", start_ms=0, end_ms=900),)
    merged = merge_diarization(turns, segments)
    assert [t.speaker_id for t in merged] == ["spk-original", "spk-original"]


def test_merge_diarization_is_a_no_op_without_segments():
    turns = (_turn(index=0, start_ms=0, end_ms=100),)
    assert merge_diarization(turns, ()) is turns


def test_merge_diarization_keeps_a_known_turn_role_over_an_unknown_segment_role():
    turns = (_turn(index=0, text="hi", role=ChannelRole.AGENT, start_ms=0, end_ms=1000),)
    segments = (SpeakerSegment(speaker_id="spk-a", start_ms=0, end_ms=1000),)
    assert merge_diarization(turns, segments)[0].role is ChannelRole.AGENT


def test_speaker_segments_reject_inverted_windows():
    with pytest.raises(TranscriptError, match="precedes start_ms"):
        SpeakerSegment(speaker_id="spk-a", start_ms=900, end_ms=100)
