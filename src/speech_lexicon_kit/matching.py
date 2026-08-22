"""Deterministic phrase matching over normalised text, producing lexicon hits.

The kit carries the MATCHING, never the phrases. A required-disclosure wording, a scam cue
list, a market-abuse lexicon and a meeting-commitment cue set are all vertical policy owned
and reviewed by the consuming repo; putting any of them here would make a compliance wording
change a release of a shared package. What every consumer does share is the question "does
this exact wording, allowing for how a recogniser mangles it, appear in this turn, and where
exactly?" - and that answer must be identical in all of them.

Two shapes come out:

* :class:`TextMatch` - a match in a plain string, for the channels that are not audio at all
  (chat, email, a messaging archive under surveillance).
* :class:`LexiconHit` - the same match located in a transcript: turn index, speaker, role, the
  character span in the ORIGINAL turn text and the audio window derived from word offsets.

Both are ordered deterministically and carry the normalised form that actually matched, so a
reviewer can see why a hit fired without re-running the matcher.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum

from .normalisation import LocaleRules, NormalisedText, canonical_locale, normalise, rules_for
from .transcript import ChannelRole, SpeakerTurn, Transcript, span_timing

__all__ = [
    "Lexicon",
    "LexiconEntry",
    "LexiconError",
    "LexiconHit",
    "LocaleMismatchError",
    "MatchMode",
    "PhraseSpec",
    "TextMatch",
    "find_hits",
    "find_matches",
]

DEFAULT_MAX_GAP_CHARS = 40
"""Default separation allowed between the segments of an ordered-segment phrase."""


class LexiconError(ValueError):
    """Raised when a lexicon, entry or phrase violates one of its invariants."""


class LocaleMismatchError(ValueError):
    """Raised when a lexicon is applied to a transcript written in another language."""


class MatchMode(StrEnum):
    """How a phrase's wording must appear.

    ``CONTIGUOUS`` is the strict form and the right default for a required disclosure, where
    the wording is prescribed. ``ORDERED_SEGMENTS`` allows the phrase's whitespace-separated
    segments to appear in order with limited filler between them, which is what a live
    conversation does to a scripted sentence ("we may record this call" spoken as "we may
    need to record this call"). It is a relaxation, so it is opt-in per phrase and its
    tolerance is a number the adopter sets rather than one this package hides.
    """

    CONTIGUOUS = "contiguous"
    ORDERED_SEGMENTS = "ordered_segments"


@dataclass(frozen=True, slots=True)
class PhraseSpec:
    """One wording that satisfies an entry."""

    phrase_id: str
    text: str
    mode: MatchMode = MatchMode.CONTIGUOUS
    max_gap_chars: int = DEFAULT_MAX_GAP_CHARS

    def __post_init__(self) -> None:
        if not self.phrase_id.strip():
            raise LexiconError("PhraseSpec.phrase_id must be non-empty")
        if not self.text.strip():
            raise LexiconError(f"phrase {self.phrase_id!r}: text must be non-empty")
        if self.max_gap_chars < 0:
            raise LexiconError(
                f"phrase {self.phrase_id!r}: max_gap_chars must be >= 0, got {self.max_gap_chars}"
            )


@dataclass(frozen=True, slots=True)
class LexiconEntry:
    """One concept, and every wording that counts as having expressed it.

    Multiple phrases are alternatives: a hit on any of them is a hit on the entry. That is how
    "acceptable paraphrases" are expressed without the matcher needing to know what a
    paraphrase is.
    """

    entry_id: str
    phrases: tuple[PhraseSpec, ...]
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.entry_id.strip():
            raise LexiconError("LexiconEntry.entry_id must be non-empty")
        if not self.phrases:
            raise LexiconError(
                f"entry {self.entry_id!r}: at least one phrase is required. An entry with no "
                f"wording can never be satisfied and would silently read as absent."
            )
        seen: set[str] = set()
        for phrase in self.phrases:
            if phrase.phrase_id in seen:
                raise LexiconError(
                    f"entry {self.entry_id!r}: duplicate phrase id {phrase.phrase_id!r}"
                )
            seen.add(phrase.phrase_id)


@dataclass(frozen=True, slots=True)
class Lexicon:
    """A set of entries compiled for one locale.

    The locale is part of the lexicon rather than the call, because a phrase list is written
    for a language: the same list cannot be correct under both English token-boundary matching
    and Japanese character-run matching. Construction validates that every phrase survives
    normalisation to a non-empty needle, so a phrase made entirely of punctuation is rejected
    here rather than matching at every position at run time.
    """

    lexicon_id: str
    locale: str
    entries: tuple[LexiconEntry, ...]
    version: str = "v1"

    def __post_init__(self) -> None:
        if not self.lexicon_id.strip():
            raise LexiconError("Lexicon.lexicon_id must be non-empty")
        if not self.entries:
            raise LexiconError(f"lexicon {self.lexicon_id!r}: at least one entry is required")
        object.__setattr__(self, "locale", canonical_locale(self.locale))
        seen: set[str] = set()
        for entry in self.entries:
            if entry.entry_id in seen:
                raise LexiconError(
                    f"lexicon {self.lexicon_id!r}: duplicate entry id {entry.entry_id!r}"
                )
            seen.add(entry.entry_id)
        _compile(self)

    @property
    def language(self) -> str:
        return self.locale.split("-", 1)[0]

    @property
    def entry_ids(self) -> tuple[str, ...]:
        return tuple(entry.entry_id for entry in self.entries)

    def rules(self) -> LocaleRules:
        return rules_for(self.locale)


@dataclass(frozen=True, slots=True)
class TextMatch:
    """A phrase found in a plain string, cited by character span in the ORIGINAL text."""

    entry_id: str
    phrase_id: str
    char_start: int
    char_end: int
    matched_text: str
    normalised_text: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LexiconHit:
    """A phrase found in a transcript turn: who said it, where, and when."""

    lexicon_id: str
    entry_id: str
    phrase_id: str
    turn_index: int
    speaker_id: str
    role: ChannelRole
    char_start: int
    char_end: int
    matched_text: str
    normalised_text: str
    start_ms: int | None = None
    end_ms: int | None = None
    tags: tuple[str, ...] = ()

    @property
    def position(self) -> tuple[int, int, int]:
        """The ordering key: turn, then character span. Total and stable."""
        return (self.turn_index, self.char_start, self.char_end)

    def strictly_after(self, other: LexiconHit) -> bool:
        """True when this hit begins after ``other`` ends, without overlapping it."""
        if self.turn_index != other.turn_index:
            return self.turn_index > other.turn_index
        return self.char_start >= other.char_end


@dataclass(frozen=True, slots=True)
class _CompiledPhrase:
    entry_id: str
    phrase_id: str
    segments: tuple[str, ...]
    max_gap_chars: int
    tags: tuple[str, ...]


def _compile(lexicon: Lexicon) -> tuple[_CompiledPhrase, ...]:
    """Normalise every phrase once, validating that each yields a usable needle."""
    rules = rules_for(lexicon.locale)
    compiled: list[_CompiledPhrase] = []
    for entry in lexicon.entries:
        for phrase in entry.phrases:
            if phrase.mode is MatchMode.CONTIGUOUS:
                raw_segments = [phrase.text]
            else:
                raw_segments = phrase.text.split()
            segments = tuple(
                normalised
                for normalised in (normalise(part, rules).text for part in raw_segments)
                if normalised
            )
            if not segments:
                raise LexiconError(
                    f"lexicon {lexicon.lexicon_id!r} entry {entry.entry_id!r} phrase "
                    f"{phrase.phrase_id!r}: {phrase.text!r} normalises to nothing under "
                    f"{lexicon.locale} rules, so it would match everywhere"
                )
            compiled.append(
                _CompiledPhrase(
                    entry_id=entry.entry_id,
                    phrase_id=phrase.phrase_id,
                    segments=segments,
                    max_gap_chars=phrase.max_gap_chars,
                    tags=entry.tags,
                )
            )
    return tuple(compiled)


def _next_occurrence(norm: NormalisedText, needle: str, start: int) -> tuple[int, int] | None:
    """First occurrence of ``needle`` at or after ``start`` that lands on token boundaries."""
    position = start
    while True:
        found = norm.text.find(needle, position)
        if found < 0:
            return None
        end = found + len(needle)
        if norm.is_boundary(found) and norm.is_boundary(end):
            return (found, end)
        position = found + 1


def _find_spans(norm: NormalisedText, phrase: _CompiledPhrase) -> list[tuple[int, int]]:
    """Every non-overlapping span of ``phrase`` in ``norm``, left to right.

    For an ordered-segment phrase the search is leftmost-then-earliest: the first segment
    anchors as early as possible, each later segment takes the earliest boundary-valid
    occurrence within the allowed gap, and a failure restarts the whole phrase one character
    past the previous anchor. That rule is arbitrary in the way any tie-break is arbitrary,
    and total in the way a replayable one has to be.
    """
    spans: list[tuple[int, int]] = []
    scan = 0
    limit = len(norm.text)
    while scan <= limit:
        first = _next_occurrence(norm, phrase.segments[0], scan)
        if first is None:
            break
        cursor = first[1]
        complete = True
        for segment in phrase.segments[1:]:
            following = _next_occurrence(norm, segment, cursor)
            if following is None or following[0] - cursor > phrase.max_gap_chars:
                complete = False
                break
            cursor = following[1]
        if complete:
            spans.append((first[0], cursor))
            scan = cursor
        else:
            scan = first[0] + 1
    return spans


def find_matches(text: str, lexicon: Lexicon) -> tuple[TextMatch, ...]:
    """Find every lexicon phrase in ``text``, cited by span in the ORIGINAL string.

    Matches from different entries may overlap, because two concepts can legitimately be
    expressed by overlapping wording; matches of a single phrase never do. The result is
    sorted by ``(char_start, char_end, entry_id, phrase_id)``, which is a total order over the
    output and therefore replayable.
    """
    norm = normalise(text, rules_for(lexicon.locale))
    matches: list[TextMatch] = []
    for phrase in _compile(lexicon):
        for start, end in _find_spans(norm, phrase):
            source_start, source_end = norm.source_span(start, end)
            matches.append(
                TextMatch(
                    entry_id=phrase.entry_id,
                    phrase_id=phrase.phrase_id,
                    char_start=source_start,
                    char_end=source_end,
                    matched_text=text[source_start:source_end],
                    normalised_text=norm.text[start:end],
                    tags=phrase.tags,
                )
            )
    matches.sort(key=lambda m: (m.char_start, m.char_end, m.entry_id, m.phrase_id))
    return tuple(matches)


def _turn_applies(transcript: Transcript, turn: SpeakerTurn, lexicon: Lexicon) -> bool:
    return canonical_locale(transcript.locale_for(turn)).split("-", 1)[0] == lexicon.language


def find_hits(
    transcript: Transcript,
    lexicon: Lexicon,
    *,
    roles: Collection[ChannelRole] | None = None,
) -> tuple[LexiconHit, ...]:
    """Find every lexicon phrase in ``transcript``, as hits carrying speaker, span and timing.

    Only turns whose effective language matches the lexicon's are searched, which is how a
    code-switched conversation gets each of its languages scored by the lexicon written for
    it. If NO turn is in the lexicon's language the call raises rather than returning an empty
    tuple: silence would be indistinguishable from a genuine absence, and "no disclosure
    found" is a consequential finding that must never be an artefact of a misconfigured pair.

    ``roles`` restricts the search (a required agent disclosure is not satisfied by the
    customer saying it). The result is sorted by turn, then character span, then entry and
    phrase id.
    """
    applicable = [turn for turn in transcript.turns if _turn_applies(transcript, turn, lexicon)]
    if not applicable:
        raise LocaleMismatchError(
            f"lexicon {lexicon.lexicon_id!r} is written for {lexicon.locale} but no turn of "
            f"transcript {transcript.transcript_id!r} ({transcript.locale}) is in that "
            f"language; scoring it would report a false absence"
        )
    wanted = frozenset(roles) if roles is not None else None
    hits: list[LexiconHit] = []
    for turn in applicable:
        if wanted is not None and turn.role not in wanted:
            continue
        for match in find_matches(turn.text, lexicon):
            start_ms, end_ms = span_timing(turn, match.char_start, match.char_end)
            hits.append(
                LexiconHit(
                    lexicon_id=lexicon.lexicon_id,
                    entry_id=match.entry_id,
                    phrase_id=match.phrase_id,
                    turn_index=turn.index,
                    speaker_id=turn.speaker_id,
                    role=turn.role,
                    char_start=match.char_start,
                    char_end=match.char_end,
                    matched_text=match.matched_text,
                    normalised_text=match.normalised_text,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    tags=match.tags,
                )
            )
    hits.sort(key=lambda h: (h.turn_index, h.char_start, h.char_end, h.entry_id, h.phrase_id))
    return tuple(hits)
