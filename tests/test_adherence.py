"""Ordered-phrase adherence: the six outcomes, and the fail-closed direction of each."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from speech_lexicon_kit.adherence import (
    AdherenceError,
    AdherenceOutcome,
    PhraseSequenceRequirement,
    evaluate_requirements,
    evaluate_sequence,
    ordered_hit_chain,
    present_entry_ids,
)
from speech_lexicon_kit.matching import LexiconHit
from speech_lexicon_kit.transcript import ChannelRole, SpeakerTurn, Transcript

STARTED = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
AS_OF = datetime(2026, 3, 1, 12, 5, 0, tzinfo=UTC)


def _hit(
    entry_id: str,
    turn_index: int,
    char_start: int = 0,
    *,
    role: ChannelRole = ChannelRole.AGENT,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> LexiconHit:
    return LexiconHit(
        lexicon_id="example-pack",
        entry_id=entry_id,
        phrase_id="exact",
        turn_index=turn_index,
        speaker_id=f"spk-{turn_index}",
        role=role,
        char_start=char_start,
        char_end=char_start + 5,
        matched_text="xxxxx",
        normalised_text="xxxxx",
        start_ms=start_ms,
        end_ms=end_ms,
    )


def _transcript(*, closed: bool = True, turns: int = 3) -> Transcript:
    return Transcript(
        transcript_id="T-EXAMPLE-001",
        locale="en-SG",
        turns=tuple(
            SpeakerTurn(index=i, speaker_id=f"spk-{i}", role=ChannelRole.AGENT, text="text")
            for i in range(turns)
        ),
        started_at=STARTED,
        ended_at=datetime(2026, 3, 1, 12, 1, tzinfo=UTC) if closed else None,
    )


def _evaluate(hits, requirement, *, closed=True, as_of=AS_OF):
    return evaluate_sequence(_transcript(closed=closed), hits, requirement, as_of=as_of)


def test_present_in_order_and_in_time_is_satisfied():
    hits = [_hit("a", 0, start_ms=0, end_ms=500), _hit("b", 1, start_ms=1000, end_ms=1500)]
    result = _evaluate(hits, PhraseSequenceRequirement("R1", ("a", "b"), deadline_ms=5_000))
    assert result.outcome is AdherenceOutcome.SATISFIED
    assert result.satisfied
    assert (result.first_ms, result.last_ms, result.elapsed_ms) == (0, 1500, 1500)


def test_present_but_reversed_is_out_of_order_not_absent():
    hits = [_hit("b", 0), _hit("a", 1)]
    result = _evaluate(hits, PhraseSequenceRequirement("R1", ("a", "b")))
    assert result.outcome is AdherenceOutcome.OUT_OF_ORDER
    assert result.missing_entry_ids == ()


def test_a_missing_step_on_a_closed_transcript_is_absent():
    result = _evaluate([_hit("a", 0)], PhraseSequenceRequirement("R1", ("a", "b")))
    assert result.outcome is AdherenceOutcome.ABSENT
    assert result.missing_entry_ids == ("b",)


def test_a_missing_step_on_an_open_transcript_is_pending_not_a_breach():
    # Without this, a live copilot reports a breach in the first second of every call.
    result = _evaluate(
        [_hit("a", 0)],
        PhraseSequenceRequirement("R1", ("a", "b"), deadline_ms=600_000),
        closed=False,
    )
    assert result.outcome is AdherenceOutcome.PENDING
    assert not result.satisfied


def test_an_open_transcript_past_its_deadline_is_absent_again():
    result = _evaluate(
        [_hit("a", 0)],
        PhraseSequenceRequirement("R1", ("a", "b"), deadline_ms=1_000),
        closed=False,
    )
    assert result.outcome is AdherenceOutcome.ABSENT


def test_an_open_transcript_with_no_deadline_stays_pending():
    result = _evaluate([], PhraseSequenceRequirement("R1", ("a",)), closed=False)
    assert result.outcome is AdherenceOutcome.PENDING


def test_a_closed_transcript_is_never_pending():
    result = _evaluate([], PhraseSequenceRequirement("R1", ("a",), deadline_ms=600_000))
    assert result.outcome is AdherenceOutcome.ABSENT


def test_a_span_wider_than_the_window_is_late():
    hits = [_hit("a", 0, start_ms=0, end_ms=100), _hit("b", 1, start_ms=9_000, end_ms=9_500)]
    result = _evaluate(hits, PhraseSequenceRequirement("R1", ("a", "b"), within_ms=5_000))
    assert result.outcome is AdherenceOutcome.LATE


def test_a_step_finishing_past_the_deadline_is_late():
    hits = [_hit("a", 0, start_ms=0, end_ms=100), _hit("b", 1, start_ms=9_000, end_ms=9_500)]
    result = _evaluate(hits, PhraseSequenceRequirement("R1", ("a", "b"), deadline_ms=5_000))
    assert result.outcome is AdherenceOutcome.LATE


def test_a_timing_constraint_over_untimed_hits_is_unverifiable_not_satisfied():
    # The fail-closed direction: an unchecked deadline must never read as a met one.
    hits = [_hit("a", 0), _hit("b", 1)]
    result = _evaluate(hits, PhraseSequenceRequirement("R1", ("a", "b"), deadline_ms=5_000))
    assert result.outcome is AdherenceOutcome.UNVERIFIABLE
    assert not result.satisfied


def test_untimed_hits_without_a_timing_constraint_are_simply_satisfied():
    hits = [_hit("a", 0), _hit("b", 1)]
    result = _evaluate(hits, PhraseSequenceRequirement("R1", ("a", "b")))
    assert result.outcome is AdherenceOutcome.SATISFIED


def test_the_role_filter_means_who_said_it_matters():
    hits = [_hit("a", 0, role=ChannelRole.CUSTOMER)]
    result = _evaluate(hits, PhraseSequenceRequirement("R1", ("a",), role=ChannelRole.AGENT))
    assert result.outcome is AdherenceOutcome.ABSENT


def test_a_repeated_step_needs_a_second_occurrence():
    single = _evaluate([_hit("a", 0)], PhraseSequenceRequirement("R1", ("a", "a")))
    assert single.outcome is AdherenceOutcome.ABSENT
    assert single.missing_entry_ids == ("a",)
    twice = _evaluate([_hit("a", 0), _hit("a", 1)], PhraseSequenceRequirement("R1", ("a", "a")))
    assert twice.outcome is AdherenceOutcome.SATISFIED


def test_one_utterance_cannot_satisfy_two_positions():
    overlapping = [_hit("a", 0, char_start=0), _hit("b", 0, char_start=2)]
    result = _evaluate(overlapping, PhraseSequenceRequirement("R1", ("a", "b")))
    assert result.outcome is AdherenceOutcome.OUT_OF_ORDER


def test_the_chain_is_the_earliest_one_and_none_means_no_chain_exists():
    hits = [_hit("a", 0), _hit("a", 2), _hit("b", 1)]
    chain = ordered_hit_chain(hits, ("a", "b"))
    assert chain is not None
    assert [(hit.entry_id, hit.turn_index) for hit in chain] == [("a", 0), ("b", 1)]
    assert ordered_hit_chain(hits, ("b", "b")) is None


def test_presence_on_its_own_is_available_and_sorted():
    hits = [_hit("z", 0), _hit("a", 1), _hit("a", 2, role=ChannelRole.CUSTOMER)]
    assert present_entry_ids(hits) == ("a", "z")
    assert present_entry_ids(hits, role=ChannelRole.CUSTOMER) == ("a",)


def test_step_evidence_is_reported_position_by_position():
    hits = [_hit("a", 0), _hit("b", 1)]
    result = _evaluate(hits, PhraseSequenceRequirement("R1", ("a", "b")))
    assert [(step.position, step.entry_id, step.satisfied) for step in result.steps] == [
        (0, "a", True),
        (1, "b", True),
    ]
    unmet = _evaluate([_hit("a", 0)], PhraseSequenceRequirement("R1", ("a", "b")))
    assert [step.satisfied for step in unmet.steps] == [False, False]


def test_an_empty_requirement_set_is_never_all_satisfied():
    # all(()) is true and is not evidence.
    report = evaluate_requirements(_transcript(), [], [], as_of=AS_OF)
    assert not report.all_satisfied


def test_a_report_is_sorted_and_lists_what_failed():
    hits = [_hit("a", 0)]
    report = evaluate_requirements(
        _transcript(),
        hits,
        [
            PhraseSequenceRequirement("R2", ("b",)),
            PhraseSequenceRequirement("R1", ("a",)),
        ],
        as_of=AS_OF,
    )
    assert [result.requirement_id for result in report.results] == ["R1", "R2"]
    assert [result.requirement_id for result in report.unsatisfied] == ["R2"]
    assert not report.all_satisfied
    assert report.as_of == AS_OF


def test_duplicate_requirement_ids_are_refused():
    with pytest.raises(AdherenceError, match="duplicate requirement id"):
        evaluate_requirements(
            _transcript(),
            [],
            [PhraseSequenceRequirement("R1", ("a",)), PhraseSequenceRequirement("R1", ("b",))],
            as_of=AS_OF,
        )


def test_a_naive_as_of_is_refused():
    with pytest.raises(AdherenceError, match="timezone-aware"):
        _evaluate([], PhraseSequenceRequirement("R1", ("a",)), as_of=datetime(2026, 3, 1, 12, 0))


def test_an_empty_sequence_is_refused_rather_than_vacuously_satisfied():
    with pytest.raises(AdherenceError, match="at least one step"):
        PhraseSequenceRequirement("R1", ())


def test_negative_timing_bounds_are_refused():
    with pytest.raises(AdherenceError, match="within_ms must be >= 0"):
        PhraseSequenceRequirement("R1", ("a",), within_ms=-1)
    with pytest.raises(AdherenceError, match="deadline_ms must be >= 0"):
        PhraseSequenceRequirement("R1", ("a",), deadline_ms=-1)


def test_as_of_is_recorded_so_a_replay_can_reproduce_the_verdict():
    result = _evaluate([], PhraseSequenceRequirement("R1", ("a",)))
    assert result.as_of == AS_OF


def test_the_same_inputs_and_as_of_give_the_same_result():
    hits = [_hit("a", 0, start_ms=0, end_ms=10), _hit("b", 1, start_ms=20, end_ms=30)]
    requirement = PhraseSequenceRequirement("R1", ("a", "b"), deadline_ms=5_000)
    assert _evaluate(hits, requirement) == _evaluate(hits, requirement)
