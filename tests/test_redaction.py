"""Redaction application: right-to-left masking, refused overlaps, dropped offsets."""

from __future__ import annotations

import pytest

from speech_lexicon_kit.redaction import apply_redactions, redact_transcript
from speech_lexicon_kit.transcript import (
    ChannelRole,
    RedactionSpan,
    SpeakerTurn,
    Transcript,
    TranscriptError,
    WordOffset,
)

TEXT = "Call me on 555-0100 or write to rowan@example.test"


def _span(start: int, end: int, info_type: str, replacement: str = "[REDACTED]") -> RedactionSpan:
    return RedactionSpan(
        turn_index=0, char_start=start, char_end=end, info_type=info_type, replacement=replacement
    )


def test_masking_two_spans_leaves_both_correct():
    # The right-to-left order is the point: a left-to-right pass would shift the second span.
    redacted = apply_redactions(
        TEXT, [_span(11, 19, "PHONE"), _span(32, 50, "EMAIL", replacement="[EMAIL]")]
    )
    assert redacted.text == "Call me on [REDACTED] or write to [EMAIL]"


def test_a_shorter_replacement_does_not_corrupt_the_next_span():
    redacted = apply_redactions(
        TEXT, [_span(11, 19, "PHONE", replacement="*"), _span(32, 50, "EMAIL", replacement="*")]
    )
    assert redacted.text == "Call me on * or write to *"


def test_spans_are_applied_in_a_stable_order_regardless_of_input_order():
    forwards = apply_redactions(TEXT, [_span(11, 19, "PHONE"), _span(32, 50, "EMAIL")])
    backwards = apply_redactions(TEXT, [_span(32, 50, "EMAIL"), _span(11, 19, "PHONE")])
    assert forwards == backwards
    assert [span.char_start for span in forwards.applied] == [11, 32]


def test_overlapping_spans_are_refused_rather_than_merged():
    # Two detectors disagreeing about where an identifier starts is a real condition for the
    # caller to resolve, and unioning them would hide it.
    with pytest.raises(TranscriptError, match="spans overlap"):
        apply_redactions(TEXT, [_span(11, 19, "PHONE"), _span(15, 25, "OTHER")])


def test_a_span_past_the_end_is_refused():
    with pytest.raises(TranscriptError, match="runs past"):
        apply_redactions("short", [_span(0, 99, "PHONE")])


def test_a_zero_length_span_is_recorded_and_changes_nothing():
    redacted = apply_redactions(TEXT, [_span(5, 5, "PHONE", replacement="")])
    assert redacted.text == TEXT
    assert redacted.redacted_characters == 0


def test_no_spans_is_the_identity():
    assert apply_redactions(TEXT, []).text == TEXT


def test_redacted_characters_counts_the_source_not_the_replacement():
    redacted = apply_redactions(TEXT, [_span(11, 19, "PHONE", replacement="*")])
    assert redacted.redacted_characters == 8


def _transcript(spans: tuple[RedactionSpan, ...] = ()) -> Transcript:
    return Transcript(
        transcript_id="T-EXAMPLE-001",
        locale="en-SG",
        turns=(
            SpeakerTurn(
                index=0,
                speaker_id="spk-0",
                role=ChannelRole.CUSTOMER,
                text=TEXT,
                words=(WordOffset(text="Call", char_start=0, char_end=4, start_ms=0, end_ms=200),),
            ),
            SpeakerTurn(index=1, speaker_id="spk-1", role=ChannelRole.AGENT, text="Noted."),
        ),
        redactions=spans,
    )


def test_redacting_a_transcript_masks_only_the_cited_turns():
    transcript = _transcript((_span(11, 19, "PHONE"),))
    redacted = redact_transcript(transcript)
    assert redacted.turn(0).text == "Call me on [REDACTED] or write to rowan@example.test"
    assert redacted.turn(1).text == "Noted."


def test_word_offsets_are_dropped_from_masked_turns_only():
    # They index the original text; keeping them against shifted text would mis-cite words.
    redacted = redact_transcript(_transcript((_span(11, 19, "PHONE"),)))
    assert redacted.turn(0).words == ()
    assert redact_transcript(_transcript(())).turn(0).words != ()


def test_the_redacted_copy_carries_no_spans_because_they_describe_the_original():
    redacted = redact_transcript(_transcript((_span(11, 19, "PHONE", replacement="*"),)))
    assert redacted.redactions == ()


def test_explicit_spans_override_the_transcripts_own():
    transcript = _transcript((_span(11, 19, "PHONE"),))
    redacted = redact_transcript(transcript, [_span(32, 50, "EMAIL")])
    assert redacted.turn(0).text == "Call me on 555-0100 or write to [REDACTED]"


def test_a_span_citing_a_turn_that_does_not_exist_is_refused():
    transcript = _transcript(())
    stray = RedactionSpan(turn_index=9, char_start=0, char_end=1, info_type="PHONE")
    with pytest.raises(TranscriptError, match="cites turn 9"):
        redact_transcript(transcript, [stray])


def test_transcript_identity_and_timing_survive_redaction():
    transcript = _transcript((_span(11, 19, "PHONE"),))
    redacted = redact_transcript(transcript)
    assert redacted.transcript_id == transcript.transcript_id
    assert redacted.locale == transcript.locale
    assert redacted.turn(0).start_ms == transcript.turn(0).start_ms
