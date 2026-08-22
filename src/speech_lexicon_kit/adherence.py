"""Ordered-phrase adherence: did the required things get said, in the required order, in time?

Presence is the easy half and the half everyone gets right. The hard half is that a scripted
sequence has an ORDER (the recording notice before the customer starts giving personal
details, not after) and a WINDOW (early in the contact, not in the closing seconds), and that
a conversation still in progress has not yet failed anything.

The primitives here answer that with five outcomes and no verdict of their own beyond the
literal question asked:

* ``SATISFIED`` - every step present, in order, inside every declared window.
* ``LATE`` - present and in order, but outside a declared window.
* ``OUT_OF_ORDER`` - every step present, but no ordering of the hits satisfies the sequence.
* ``ABSENT`` - a step never happened and the conversation can no longer produce it.
* ``PENDING`` - a step has not happened yet, but the conversation is still open and its
  deadline has not passed as of the caller's ``as_of``.
* ``UNVERIFIABLE`` - the sequence is present and ordered but a declared timing constraint
  cannot be checked, because the transcript carries no word timings.

The last two are why this module exists rather than being three lines in each consumer.
``PENDING`` is what makes the primitives usable by a live copilot as well as a post-contact
scorecard: without it, every requirement is a breach for the first second of every call.
``UNVERIFIABLE`` is the fail-closed direction for the timing question: an unchecked deadline
must not be reported as a met one.

There is NO CLOCK here. ``as_of`` is supplied by the caller on every evaluation and recorded
on the result, so a replay of the same transcript with the same ``as_of`` is byte-identical.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .matching import LexiconHit
from .transcript import ChannelRole, Transcript

__all__ = [
    "AdherenceError",
    "AdherenceOutcome",
    "AdherenceReport",
    "PhraseSequenceRequirement",
    "SequenceAdherence",
    "StepEvidence",
    "evaluate_requirements",
    "evaluate_sequence",
    "ordered_hit_chain",
    "present_entry_ids",
]


class AdherenceError(ValueError):
    """Raised when a requirement or an evaluation argument violates its invariants."""


class AdherenceOutcome(StrEnum):
    """The verdict on one ordered-phrase requirement. Only ``SATISFIED`` is a pass."""

    SATISFIED = "satisfied"
    LATE = "late"
    OUT_OF_ORDER = "out_of_order"
    ABSENT = "absent"
    PENDING = "pending"
    UNVERIFIABLE = "unverifiable"


@dataclass(frozen=True, slots=True)
class PhraseSequenceRequirement:
    """A required sequence of lexicon entries, with optional timing constraints.

    ``step_entry_ids`` names entries, not phrases, so any accepted wording of a step satisfies
    it. Repeating an entry id requires it to occur that many times, each occurrence strictly
    after the previous step.

    ``within_ms`` bounds the span from the first step's start to the last step's end.
    ``deadline_ms`` bounds the last step's end relative to the start of the audio. Both are
    millisecond offsets inside the recording, never wall-clock times, so they replay.
    """

    requirement_id: str
    step_entry_ids: tuple[str, ...]
    role: ChannelRole | None = None
    within_ms: int | None = None
    deadline_ms: int | None = None

    def __post_init__(self) -> None:
        if not self.requirement_id.strip():
            raise AdherenceError("PhraseSequenceRequirement.requirement_id must be non-empty")
        if not self.step_entry_ids:
            raise AdherenceError(
                f"requirement {self.requirement_id!r}: at least one step is required. An empty "
                f"sequence is vacuously satisfied and would prove nothing."
            )
        for entry_id in self.step_entry_ids:
            if not entry_id.strip():
                raise AdherenceError(
                    f"requirement {self.requirement_id!r}: step entry ids must be non-empty"
                )
        for name in ("within_ms", "deadline_ms"):
            value: int | None = getattr(self, name)
            if value is not None and value < 0:
                raise AdherenceError(
                    f"requirement {self.requirement_id!r}: {name} must be >= 0, got {value}"
                )


@dataclass(frozen=True, slots=True)
class StepEvidence:
    """One position in a required sequence, and the hit that satisfied it (or none)."""

    position: int
    entry_id: str
    hit: LexiconHit | None = None

    @property
    def satisfied(self) -> bool:
        return self.hit is not None


@dataclass(frozen=True, slots=True)
class SequenceAdherence:
    """The full evidence for one requirement: verdict, per-step hits and timings."""

    requirement_id: str
    outcome: AdherenceOutcome
    steps: tuple[StepEvidence, ...]
    missing_entry_ids: tuple[str, ...]
    as_of: datetime
    first_ms: int | None = None
    last_ms: int | None = None
    elapsed_ms: int | None = None

    @property
    def satisfied(self) -> bool:
        """A pass is only a pass. LATE, PENDING and UNVERIFIABLE are all not-satisfied."""
        return self.outcome is AdherenceOutcome.SATISFIED


@dataclass(frozen=True, slots=True)
class AdherenceReport:
    """Every requirement evaluated against one transcript at one ``as_of``."""

    transcript_id: str
    as_of: datetime
    results: tuple[SequenceAdherence, ...]

    @property
    def all_satisfied(self) -> bool:
        """True only when every requirement is SATISFIED, and never for an empty set.

        An empty requirement set is not evidence of compliance, so it fails closed: a
        scorecard configured with no requirements must not report a clean contact.
        """
        return bool(self.results) and all(result.satisfied for result in self.results)

    @property
    def unsatisfied(self) -> tuple[SequenceAdherence, ...]:
        return tuple(result for result in self.results if not result.satisfied)


def _require_aware(as_of: datetime) -> None:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise AdherenceError(
            "as_of must be timezone-aware; a naive timestamp compares differently on every host"
        )


def present_entry_ids(
    hits: Iterable[LexiconHit],
    *,
    role: ChannelRole | None = None,
) -> tuple[str, ...]:
    """The distinct entry ids with at least one hit, sorted. The presence half, on its own."""
    return tuple(sorted({hit.entry_id for hit in hits if role is None or hit.role is role}))


def ordered_hit_chain(
    hits: Iterable[LexiconHit],
    step_entry_ids: Sequence[str],
) -> tuple[LexiconHit, ...] | None:
    """The earliest chain of hits realising ``step_entry_ids`` in order, or ``None``.

    Each step takes the earliest hit of its entry that begins after the previous step ends,
    which is the standard greedy subsequence match: if any ordering exists, the earliest-first
    one does, so ``None`` is proof that no ordering exists rather than an artefact of the
    search. Steps may not overlap, so one utterance cannot satisfy two positions at once.
    """
    ordered = sorted(hits, key=lambda h: (h.position, h.entry_id, h.phrase_id))
    chain: list[LexiconHit] = []
    for entry_id in step_entry_ids:
        previous = chain[-1] if chain else None
        chosen: LexiconHit | None = None
        for hit in ordered:
            if hit.entry_id != entry_id:
                continue
            if previous is not None and not hit.strictly_after(previous):
                continue
            chosen = hit
            break
        if chosen is None:
            return None
        chain.append(chosen)
    return tuple(chain)


def _shortfall(
    hits: Sequence[LexiconHit],
    step_entry_ids: Sequence[str],
) -> tuple[str, ...]:
    """Step entries with fewer hits than the sequence requires, in first-required order."""
    available = Counter(hit.entry_id for hit in hits)
    required = Counter(step_entry_ids)
    missing = [
        entry_id
        for entry_id in dict.fromkeys(step_entry_ids)
        if available[entry_id] < required[entry_id]
    ]
    return tuple(missing)


def _still_pending(
    transcript: Transcript,
    requirement: PhraseSequenceRequirement,
    as_of: datetime,
) -> bool:
    """True when the conversation may still satisfy the requirement as of ``as_of``.

    A closed transcript is never pending. An open one is pending until its deadline has
    elapsed; with no declared deadline it stays pending, because "not yet" is the honest
    reading of a missing phrase in a call that is still running.
    """
    if not transcript.is_open:
        return False
    if requirement.deadline_ms is None or transcript.started_at is None:
        return True
    elapsed_ms = (as_of - transcript.started_at).total_seconds() * 1000.0
    return elapsed_ms < requirement.deadline_ms


def _breaches_a_window(
    requirement: PhraseSequenceRequirement,
    *,
    last_ms: int | None,
    elapsed_ms: int | None,
) -> bool:
    """True when a satisfied chain sits outside a declared window.

    Both bounds are checked, and either one alone is enough: ``within_ms`` bounds how long the
    sequence took, ``deadline_ms`` bounds when it had to be finished by. A caller declaring
    both means both.
    """
    within = requirement.within_ms
    if within is not None and elapsed_ms is not None and elapsed_ms > within:
        return True
    deadline = requirement.deadline_ms
    return deadline is not None and last_ms is not None and last_ms > deadline


def evaluate_sequence(
    transcript: Transcript,
    hits: Iterable[LexiconHit],
    requirement: PhraseSequenceRequirement,
    *,
    as_of: datetime,
) -> SequenceAdherence:
    """Evaluate one ordered-phrase requirement against a transcript's hits.

    Pure: the only time it knows is the ``as_of`` handed to it, and it is used for exactly one
    decision, whether an unsatisfied step on an OPEN transcript is still pending. Every other
    comparison is between millisecond offsets inside the recording.
    """
    _require_aware(as_of)
    relevant = [
        hit
        for hit in hits
        if hit.entry_id in set(requirement.step_entry_ids)
        and (requirement.role is None or hit.role is requirement.role)
    ]
    missing = _shortfall(relevant, requirement.step_entry_ids)
    chain = ordered_hit_chain(relevant, requirement.step_entry_ids)

    if chain is None:
        outcome = (
            AdherenceOutcome.PENDING
            if _still_pending(transcript, requirement, as_of)
            else (AdherenceOutcome.ABSENT if missing else AdherenceOutcome.OUT_OF_ORDER)
        )
        steps = tuple(
            StepEvidence(position=index, entry_id=entry_id)
            for index, entry_id in enumerate(requirement.step_entry_ids)
        )
        return SequenceAdherence(
            requirement_id=requirement.requirement_id,
            outcome=outcome,
            steps=steps,
            missing_entry_ids=missing,
            as_of=as_of,
        )

    steps = tuple(
        StepEvidence(position=index, entry_id=hit.entry_id, hit=hit)
        for index, hit in enumerate(chain)
    )
    first_ms = chain[0].start_ms
    last_ms = chain[-1].end_ms
    elapsed_ms = last_ms - first_ms if first_ms is not None and last_ms is not None else None

    timed = requirement.within_ms is not None or requirement.deadline_ms is not None
    if timed and (first_ms is None or last_ms is None):
        outcome = AdherenceOutcome.UNVERIFIABLE
    elif _breaches_a_window(requirement, last_ms=last_ms, elapsed_ms=elapsed_ms):
        outcome = AdherenceOutcome.LATE
    else:
        outcome = AdherenceOutcome.SATISFIED

    return SequenceAdherence(
        requirement_id=requirement.requirement_id,
        outcome=outcome,
        steps=steps,
        missing_entry_ids=(),
        as_of=as_of,
        first_ms=first_ms,
        last_ms=last_ms,
        elapsed_ms=elapsed_ms,
    )


def evaluate_requirements(
    transcript: Transcript,
    hits: Iterable[LexiconHit],
    requirements: Iterable[PhraseSequenceRequirement],
    *,
    as_of: datetime,
) -> AdherenceReport:
    """Evaluate every requirement, returning results sorted by requirement id.

    Duplicate requirement ids are rejected: two results under one id make the report
    ambiguous, and an ambiguous compliance record is not a record.
    """
    _require_aware(as_of)
    materialised = tuple(hits)
    seen: set[str] = set()
    results: list[SequenceAdherence] = []
    for requirement in requirements:
        if requirement.requirement_id in seen:
            raise AdherenceError(f"duplicate requirement id {requirement.requirement_id!r}")
        seen.add(requirement.requirement_id)
        results.append(evaluate_sequence(transcript, materialised, requirement, as_of=as_of))
    results.sort(key=lambda result: result.requirement_id)
    return AdherenceReport(
        transcript_id=transcript.transcript_id,
        as_of=as_of,
        results=tuple(results),
    )
