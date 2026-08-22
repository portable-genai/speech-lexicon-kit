"""The transcript value types: the shape every speech consumer agrees on.

A transcript is the unit of evidence a conversation-QA scorecard, a live agent-assist
copilot, a comms-surveillance case and a meeting-minutes extractor all cite. They otherwise
each invent their own turn record, and the citations stop lining up the moment two of them
have to agree.

Five types make up the kernel:

* :class:`ChannelRole` - who is speaking, as a taxonomy rather than a free string.
* :class:`WordOffset` - one token's character span in the turn text plus its audio timing,
  which is what makes a character-level citation resolvable back to a moment in the audio.
* :class:`RedactionSpan` - a character range to mask before anything leaves the deterministic
  layer. Redaction is declared as a span over the ORIGINAL text so a hit computed on the
  original still cites the same coordinates.
* :class:`SpeakerTurn` - one contiguous stretch of one speaker.
* :class:`Transcript` - the turns plus the locale that decides how they normalise.

Everything is frozen, validated at construction and pure stdlib. There is no clock here: a
transcript records ``started_at`` / ``ended_at`` as data supplied by the caller, and nothing
in this package reads the wall clock to decide anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

__all__ = [
    "ChannelRole",
    "RedactionSpan",
    "SpeakerSegment",
    "SpeakerTurn",
    "Transcript",
    "TranscriptError",
    "WordOffset",
    "merge_diarization",
    "span_timing",
]


class TranscriptError(ValueError):
    """Raised when a transcript value object violates one of its invariants."""


class ChannelRole(StrEnum):
    """Who a turn belongs to, as a closed taxonomy.

    Deliberately broader than a contact centre's agent/customer pair: a meeting-capture or a
    communications-surveillance consumer has participants and third parties rather than an
    agent, and forcing those into ``AGENT`` would make a role filter mean different things in
    different repos. ``UNKNOWN`` is the honest default before diarization has resolved a
    speaker; it is never treated as any other role.
    """

    AGENT = "agent"
    CUSTOMER = "customer"
    PARTICIPANT = "participant"
    THIRD_PARTY = "third_party"
    SYSTEM = "system"
    UNKNOWN = "unknown"

    @classmethod
    def _missing_(cls, value: object) -> ChannelRole | None:
        if isinstance(value, str):
            lowered = value.strip().lower()
            for member in cls:
                if member.value == lowered:
                    return member
        return None


def _check_ms(name: str, value: int | None) -> None:
    if value is not None and value < 0:
        raise TranscriptError(f"{name} must be a non-negative millisecond offset, got {value}")


def _check_span(name: str, start: int, end: int) -> None:
    if start < 0:
        raise TranscriptError(f"{name} start must be non-negative, got {start}")
    if end < start:
        raise TranscriptError(f"{name} end ({end}) must not precede its start ({start})")


@dataclass(frozen=True, slots=True)
class WordOffset:
    """One recognised token: where it sits in the turn text, and when it was said.

    ``char_start`` / ``char_end`` are a half-open range into the turn's ORIGINAL ``text``,
    which is what lets a match found in normalised space be reported back as an audio
    timestamp without the consumer re-deriving the alignment.
    """

    text: str
    char_start: int
    char_end: int
    start_ms: int | None = None
    end_ms: int | None = None
    confidence: float | None = None

    def __post_init__(self) -> None:
        _check_span("WordOffset", self.char_start, self.char_end)
        _check_ms("WordOffset.start_ms", self.start_ms)
        _check_ms("WordOffset.end_ms", self.end_ms)
        if self.start_ms is not None and self.end_ms is not None and self.end_ms < self.start_ms:
            raise TranscriptError(
                f"WordOffset.end_ms ({self.end_ms}) must not precede start_ms ({self.start_ms})"
            )
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise TranscriptError(f"WordOffset.confidence must be in [0, 1], got {self.confidence}")


@dataclass(frozen=True, slots=True)
class RedactionSpan:
    """A character range in a turn's original text that must be masked.

    Carrying the ``info_type`` (and not the value) is the point: the span is safe to log, the
    text it covers is not. ``replacement`` is what the masker writes; keeping it on the span
    means a redacted transcript can be reproduced byte for byte from the spans alone.
    """

    turn_index: int
    char_start: int
    char_end: int
    info_type: str
    replacement: str = "[REDACTED]"

    def __post_init__(self) -> None:
        if self.turn_index < 0:
            raise TranscriptError(f"RedactionSpan.turn_index must be >= 0, got {self.turn_index}")
        _check_span("RedactionSpan", self.char_start, self.char_end)
        if not self.info_type.strip():
            raise TranscriptError("RedactionSpan.info_type must be a non-empty label")

    @property
    def length(self) -> int:
        return self.char_end - self.char_start


@dataclass(frozen=True, slots=True)
class SpeakerTurn:
    """One contiguous stretch of speech from one speaker.

    ``index`` is the turn's position in its transcript and is validated to equal that
    position, so a citation of "turn 7" resolves without a lookup table and two runs over the
    same audio cannot disagree about what turn 7 was.

    ``language`` overrides the transcript locale for this turn only, for the code-switching
    case (an English disclosure read inside a Japanese call). It is a declaration by the
    ingesting adapter, never inferred here.
    """

    index: int
    speaker_id: str
    role: ChannelRole
    text: str
    start_ms: int | None = None
    end_ms: int | None = None
    channel: int | None = None
    words: tuple[WordOffset, ...] = ()
    language: str | None = None

    def __post_init__(self) -> None:
        if self.index < 0:
            raise TranscriptError(f"SpeakerTurn.index must be >= 0, got {self.index}")
        if not self.speaker_id.strip():
            raise TranscriptError("SpeakerTurn.speaker_id must be non-empty")
        _check_ms("SpeakerTurn.start_ms", self.start_ms)
        _check_ms("SpeakerTurn.end_ms", self.end_ms)
        if self.start_ms is not None and self.end_ms is not None and self.end_ms < self.start_ms:
            raise TranscriptError(
                f"SpeakerTurn {self.index}: end_ms ({self.end_ms}) precedes "
                f"start_ms ({self.start_ms})"
            )
        if self.channel is not None and self.channel < 0:
            raise TranscriptError(f"SpeakerTurn.channel must be >= 0, got {self.channel}")
        limit = len(self.text)
        for word in self.words:
            if word.char_end > limit:
                raise TranscriptError(
                    f"SpeakerTurn {self.index}: word offset [{word.char_start}, {word.char_end}) "
                    f"runs past the {limit}-character turn text"
                )

    def slice_text(self, char_start: int, char_end: int) -> str:
        """Return the original substring for a character span (bounds validated)."""
        _check_span("SpeakerTurn.slice_text", char_start, char_end)
        if char_end > len(self.text):
            raise TranscriptError(
                f"SpeakerTurn {self.index}: span end {char_end} runs past the turn text"
            )
        return self.text[char_start:char_end]


@dataclass(frozen=True, slots=True)
class Transcript:
    """A whole conversation: ordered turns plus the locale that governs normalisation.

    ``locale`` is required and is not defaulted, because guessing it is the one mistake this
    package exists to prevent: normalisation is locale-sensitive, so an unstated locale is an
    unstated matching rule.

    ``ended_at`` being ``None`` means the conversation is still open. That distinction is
    consequential rather than cosmetic: an adherence primitive may only call a required phrase
    ABSENT once the conversation can no longer produce it.
    """

    transcript_id: str
    locale: str
    turns: tuple[SpeakerTurn, ...]
    started_at: datetime | None = None
    ended_at: datetime | None = None
    audio_duration_ms: int | None = None
    engine: str = ""
    redactions: tuple[RedactionSpan, ...] = field(default=())

    def __post_init__(self) -> None:
        if not self.transcript_id.strip():
            raise TranscriptError("Transcript.transcript_id must be non-empty")
        if not self.locale.strip():
            raise TranscriptError("Transcript.locale must be non-empty (normalisation needs it)")
        for position, turn in enumerate(self.turns):
            if turn.index != position:
                raise TranscriptError(
                    f"Transcript {self.transcript_id}: turn at position {position} declares "
                    f"index {turn.index}; indices must match position so a citation resolves"
                )
        _check_ms("Transcript.audio_duration_ms", self.audio_duration_ms)
        if self.started_at is not None and self.started_at.tzinfo is None:
            raise TranscriptError("Transcript.started_at must be timezone-aware")
        if self.ended_at is not None and self.ended_at.tzinfo is None:
            raise TranscriptError("Transcript.ended_at must be timezone-aware")
        if (
            self.started_at is not None
            and self.ended_at is not None
            and self.ended_at < self.started_at
        ):
            raise TranscriptError("Transcript.ended_at must not precede started_at")
        turn_count = len(self.turns)
        for span in self.redactions:
            if span.turn_index >= turn_count:
                raise TranscriptError(
                    f"Transcript {self.transcript_id}: redaction cites turn {span.turn_index} "
                    f"but the transcript has {turn_count} turns"
                )
            if span.char_end > len(self.turns[span.turn_index].text):
                raise TranscriptError(
                    f"Transcript {self.transcript_id}: redaction on turn {span.turn_index} "
                    f"runs past that turn's text"
                )

    @property
    def is_open(self) -> bool:
        """True while the conversation may still produce more turns."""
        return self.ended_at is None

    def turn(self, index: int) -> SpeakerTurn:
        """Return the turn at ``index`` (which equals its position, by invariant)."""
        if not 0 <= index < len(self.turns):
            raise TranscriptError(
                f"Transcript {self.transcript_id}: no turn {index} "
                f"(the transcript has {len(self.turns)})"
            )
        return self.turns[index]

    def locale_for(self, turn: SpeakerTurn) -> str:
        """The locale governing one turn: its own ``language`` if set, else the transcript's."""
        return turn.language or self.locale


@dataclass(frozen=True, slots=True)
class SpeakerSegment:
    """A diarizer's verdict: this stretch of audio belongs to this speaker."""

    speaker_id: str
    start_ms: int
    end_ms: int
    channel: int | None = None
    role: ChannelRole = ChannelRole.UNKNOWN

    def __post_init__(self) -> None:
        if not self.speaker_id.strip():
            raise TranscriptError("SpeakerSegment.speaker_id must be non-empty")
        _check_ms("SpeakerSegment.start_ms", self.start_ms)
        _check_ms("SpeakerSegment.end_ms", self.end_ms)
        if self.end_ms < self.start_ms:
            raise TranscriptError(
                f"SpeakerSegment.end_ms ({self.end_ms}) precedes start_ms ({self.start_ms})"
            )

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


def span_timing(turn: SpeakerTurn, char_start: int, char_end: int) -> tuple[int | None, int | None]:
    """Resolve a character span in ``turn`` to an ``(start_ms, end_ms)`` audio window.

    The window is taken from the word offsets that OVERLAP the span, so a match that begins
    mid-token still reports the moment that token was spoken. Returns ``(None, None)`` when the
    turn carries no timed word covering the span: an unknown timing is reported as unknown and
    never silently substituted with the turn's own bounds, because an adherence deadline
    checked against a made-up timestamp is worse than one reported as unverifiable.
    """
    _check_span("span_timing", char_start, char_end)
    starts: list[int] = []
    ends: list[int] = []
    for word in turn.words:
        overlaps = word.char_start < char_end and word.char_end > char_start
        if char_end == char_start:
            overlaps = word.char_start <= char_start < word.char_end
        if not overlaps:
            continue
        if word.start_ms is not None:
            starts.append(word.start_ms)
        if word.end_ms is not None:
            ends.append(word.end_ms)
    return (min(starts) if starts else None, max(ends) if ends else None)


def merge_diarization(
    turns: tuple[SpeakerTurn, ...],
    segments: tuple[SpeakerSegment, ...],
) -> tuple[SpeakerTurn, ...]:
    """Assign each turn the speaker and role of the segment it overlaps most.

    Every consumer that combines a recogniser with a separate diarizer writes this join, and
    each writes a different tie-break, so the same audio yields different speaker labels in
    two repos. The rule here is fixed and total: the largest overlap in milliseconds wins;
    ties go to the earliest segment, then to the lexicographically smaller speaker id. A turn
    with no timing, or with no overlapping segment, is returned unchanged rather than guessed
    at.
    """
    if not segments:
        return turns
    ordered = sorted(segments, key=lambda s: (s.start_ms, s.end_ms, s.speaker_id))
    merged: list[SpeakerTurn] = []
    for turn in turns:
        if turn.start_ms is None or turn.end_ms is None:
            merged.append(turn)
            continue
        best: SpeakerSegment | None = None
        best_overlap = 0
        for segment in ordered:
            overlap = min(turn.end_ms, segment.end_ms) - max(turn.start_ms, segment.start_ms)
            if overlap > best_overlap:
                best, best_overlap = segment, overlap
        if best is None:
            merged.append(turn)
            continue
        role = best.role if best.role is not ChannelRole.UNKNOWN else turn.role
        merged.append(
            SpeakerTurn(
                index=turn.index,
                speaker_id=best.speaker_id,
                role=role,
                text=turn.text,
                start_ms=turn.start_ms,
                end_ms=turn.end_ms,
                channel=turn.channel if turn.channel is not None else best.channel,
                words=turn.words,
                language=turn.language,
            )
        )
    return tuple(merged)
