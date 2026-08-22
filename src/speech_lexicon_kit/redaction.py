"""Applying redaction spans: mask before anything leaves the deterministic layer.

This package does not DETECT personal data; that is a jurisdiction-aware pattern pack's job,
and duplicating it here would give two sources of truth for what an identifier looks like.
What lives here is the mechanical half nobody should write twice: given spans, produce the
masked text, and do it in an order that cannot corrupt an offset.

Two invariants make the result usable as evidence:

* **Spans are over the ORIGINAL text.** Matching runs on the original, so a hit and a
  redaction cite the same coordinate system and a reviewer can line them up. Masking is
  applied right to left so that replacing one span never shifts the next one's offsets.
* **Overlaps are refused, not merged.** Two detectors disagreeing about where an identifier
  starts is a real condition, and quietly unioning their spans hides it. The caller resolves
  it, because the caller knows which detector is authoritative.

Redaction changes lengths, so a span in redacted text no longer matches the original
coordinates. :class:`RedactedText` therefore keeps the spans it applied, which is enough to
reproduce the masking byte for byte, and consumers are expected to compute hits on the
original and narrate from the redacted copy.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .transcript import RedactionSpan, SpeakerTurn, Transcript, TranscriptError

__all__ = [
    "RedactedText",
    "apply_redactions",
    "redact_transcript",
]


@dataclass(frozen=True, slots=True)
class RedactedText:
    """Masked text plus the spans that produced it (which is the whole recipe to replay it)."""

    text: str
    applied: tuple[RedactionSpan, ...]

    @property
    def redacted_characters(self) -> int:
        return sum(span.length for span in self.applied)


def _ordered_disjoint(
    spans: Iterable[RedactionSpan],
    limit: int,
    context: str,
) -> tuple[RedactionSpan, ...]:
    ordered = sorted(spans, key=lambda s: (s.char_start, s.char_end, s.info_type))
    previous: RedactionSpan | None = None
    for span in ordered:
        if span.char_end > limit:
            raise TranscriptError(
                f"{context}: redaction [{span.char_start}, {span.char_end}) runs past the "
                f"{limit}-character text"
            )
        if previous is not None and span.char_start < previous.char_end:
            raise TranscriptError(
                f"{context}: redaction spans overlap ([{previous.char_start}, "
                f"{previous.char_end}) and [{span.char_start}, {span.char_end})). Resolve which "
                f"detector is authoritative rather than merging them here."
            )
        previous = span
    return tuple(ordered)


def apply_redactions(text: str, spans: Iterable[RedactionSpan]) -> RedactedText:
    """Mask every span in ``text``, right to left so no offset is invalidated mid-pass.

    Zero-length spans are kept in the record but change nothing, which keeps a detector that
    reports an empty match from being an error at this layer.
    """
    ordered = _ordered_disjoint(spans, len(text), "apply_redactions")
    masked = text
    for span in reversed(ordered):
        masked = masked[: span.char_start] + span.replacement + masked[span.char_end :]
    return RedactedText(text=masked, applied=ordered)


def redact_transcript(
    transcript: Transcript,
    spans: Iterable[RedactionSpan] | None = None,
) -> Transcript:
    """Return a copy of ``transcript`` with each turn's text masked.

    Word offsets are dropped from any turn that was masked: they index the original text, and
    keeping them against shifted text would produce citations that point at the wrong words.
    Losing them is the honest outcome, and a consumer that needs both keeps the original
    alongside, which is exactly what the hit-then-narrate order does.

    For the same reason the returned copy carries NO redaction spans. A replacement of a
    different length shifts every later offset, so the spans that produced this text describe
    the original and not the copy. The caller already holds them (they are the argument, or
    the source transcript's own ``redactions``), so nothing is lost by refusing to restate
    them against coordinates they no longer fit.
    """
    chosen = tuple(spans) if spans is not None else transcript.redactions
    by_turn: dict[int, list[RedactionSpan]] = {}
    for span in chosen:
        if span.turn_index >= len(transcript.turns):
            raise TranscriptError(
                f"redact_transcript: span cites turn {span.turn_index} but transcript "
                f"{transcript.transcript_id!r} has {len(transcript.turns)} turns"
            )
        by_turn.setdefault(span.turn_index, []).append(span)

    turns: list[SpeakerTurn] = []
    for turn in transcript.turns:
        turn_spans = by_turn.get(turn.index)
        if not turn_spans:
            turns.append(turn)
            continue
        redacted = apply_redactions(turn.text, turn_spans)
        turns.append(
            SpeakerTurn(
                index=turn.index,
                speaker_id=turn.speaker_id,
                role=turn.role,
                text=redacted.text,
                start_ms=turn.start_ms,
                end_ms=turn.end_ms,
                channel=turn.channel,
                words=(),
                language=turn.language,
            )
        )
    return Transcript(
        transcript_id=transcript.transcript_id,
        locale=transcript.locale,
        turns=tuple(turns),
        started_at=transcript.started_at,
        ended_at=transcript.ended_at,
        audio_duration_ms=transcript.audio_duration_ms,
        engine=transcript.engine,
        redactions=(),
    )
