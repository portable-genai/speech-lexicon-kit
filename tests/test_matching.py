"""Phrase matching: boundaries, ordering, citations and the fail-closed locale pairing."""

from __future__ import annotations

import pytest

from speech_lexicon_kit.matching import (
    Lexicon,
    LexiconEntry,
    LexiconError,
    LocaleMismatchError,
    MatchMode,
    PhraseSpec,
    find_hits,
    find_matches,
)
from speech_lexicon_kit.normalisation import UnsupportedLocaleError
from speech_lexicon_kit.transcript import (
    ChannelRole,
    SpeakerTurn,
    Transcript,
    WordOffset,
)


def _lexicon(*entries: LexiconEntry, locale: str = "en-SG") -> Lexicon:
    return Lexicon(lexicon_id="example-pack", locale=locale, entries=entries)


def _entry(entry_id: str, *phrases: PhraseSpec, tags: tuple[str, ...] = ()) -> LexiconEntry:
    return LexiconEntry(entry_id=entry_id, phrases=phrases, tags=tags)


def _transcript(*turns: SpeakerTurn, locale: str = "en-SG") -> Transcript:
    return Transcript(transcript_id="T-EXAMPLE-001", locale=locale, turns=turns)


def _turn(index: int, text: str, role: ChannelRole = ChannelRole.AGENT, **kwargs) -> SpeakerTurn:
    return SpeakerTurn(index=index, speaker_id=f"spk-{index}", role=role, text=text, **kwargs)


def test_a_match_cites_the_original_text_not_the_normalised_one():
    lexicon = _lexicon(_entry("notice", PhraseSpec("exact", "this call may be recorded")))
    text = "Hello. THIS  call, may be recorded for quality."
    match = find_matches(text, lexicon)[0]
    assert text[match.char_start : match.char_end] == "THIS  call, may be recorded"
    assert match.normalised_text == "this call may be recorded"


def test_english_matching_respects_token_boundaries():
    lexicon = _lexicon(_entry("insurance", PhraseSpec("exact", "insurance")))
    assert find_matches("Reinsurance is not insurance.", lexicon) != ()
    assert len(find_matches("Reinsurance is not insurance.", lexicon)) == 1
    assert find_matches("Reinsurances everywhere", lexicon) == ()


def test_japanese_matching_has_no_boundaries_to_respect():
    lexicon = _lexicon(_entry("check", PhraseSpec("exact", "本人確認")), locale="ja-JP")
    assert len(find_matches("続けるまえに、本人確認をさせていただきます。", lexicon)) == 1


def test_ordered_segments_tolerate_filler_up_to_the_declared_gap():
    lexicon = _lexicon(
        _entry(
            "notice",
            PhraseSpec("loose", "call recorded", mode=MatchMode.ORDERED_SEGMENTS, max_gap_chars=14),
        )
    )
    assert find_matches("this call may be recorded", lexicon) != ()
    # Beyond the tolerance the adopter set, it is not a match.
    assert find_matches("this call, after a much longer aside, was recorded", lexicon) == ()


def test_ordered_segments_are_not_a_bag_of_words():
    lexicon = _lexicon(
        _entry("notice", PhraseSpec("loose", "call recorded", mode=MatchMode.ORDERED_SEGMENTS))
    )
    assert find_matches("recorded the call", lexicon) == ()


def test_repeated_phrases_produce_non_overlapping_matches():
    lexicon = _lexicon(_entry("ack", PhraseSpec("exact", "yes")))
    matches = find_matches("Yes, yes, yes.", lexicon)
    assert len(matches) == 3
    assert [m.char_start for m in matches] == [0, 5, 10]


def test_matches_from_different_entries_may_overlap():
    lexicon = _lexicon(
        _entry("wide", PhraseSpec("exact", "not financial advice")),
        _entry("narrow", PhraseSpec("exact", "financial advice")),
    )
    assert len(find_matches("This is not financial advice.", lexicon)) == 2


def test_matches_are_totally_ordered():
    lexicon = _lexicon(
        _entry("b_entry", PhraseSpec("exact", "advice")),
        _entry("a_entry", PhraseSpec("exact", "advice")),
    )
    matches = find_matches("advice advice", lexicon)
    assert [(m.char_start, m.entry_id) for m in matches] == [
        (0, "a_entry"),
        (0, "b_entry"),
        (7, "a_entry"),
        (7, "b_entry"),
    ]


def test_hits_carry_speaker_role_and_audio_timing():
    lexicon = _lexicon(_entry("notice", PhraseSpec("exact", "recorded"), tags=("disclosure",)))
    turn = _turn(
        0,
        "this call is recorded",
        words=(WordOffset(text="recorded", char_start=13, char_end=21, start_ms=900, end_ms=1400),),
    )
    hit = find_hits(_transcript(turn), lexicon)[0]
    assert (hit.speaker_id, hit.role, hit.start_ms, hit.end_ms) == (
        "spk-0",
        ChannelRole.AGENT,
        900,
        1400,
    )
    assert hit.tags == ("disclosure",)
    assert hit.lexicon_id == "example-pack"


def test_role_filtering_is_what_makes_a_required_disclosure_required_of_someone():
    lexicon = _lexicon(_entry("notice", PhraseSpec("exact", "recorded")))
    transcript = _transcript(
        _turn(0, "is this recorded", role=ChannelRole.CUSTOMER),
        _turn(1, "yes it is recorded", role=ChannelRole.AGENT),
    )
    hits = find_hits(transcript, lexicon, roles=[ChannelRole.AGENT])
    assert [hit.turn_index for hit in hits] == [1]


def test_a_lexicon_in_a_language_no_turn_speaks_refuses_rather_than_reporting_absence():
    # Zero hits would be indistinguishable from a genuine compliance failure.
    lexicon = _lexicon(_entry("check", PhraseSpec("exact", "本人確認")), locale="ja-JP")
    with pytest.raises(LocaleMismatchError, match="false absence"):
        find_hits(_transcript(_turn(0, "hello there")), lexicon)


def test_a_code_switched_turn_is_scored_by_its_own_language():
    lexicon = _lexicon(_entry("notice", PhraseSpec("exact", "may be recorded")))
    transcript = _transcript(
        _turn(0, "この通話は録音されます"),
        _turn(1, "This call may be recorded.", language="en-SG"),
        locale="ja-JP",
    )
    hits = find_hits(transcript, lexicon)
    assert [hit.turn_index for hit in hits] == [1]


def test_hits_are_ordered_by_turn_then_span():
    lexicon = _lexicon(_entry("ack", PhraseSpec("exact", "yes")))
    transcript = _transcript(_turn(0, "yes and yes"), _turn(1, "yes"))
    hits = find_hits(transcript, lexicon)
    assert [hit.position for hit in hits] == [(0, 0, 3), (0, 8, 11), (1, 0, 3)]


def test_strictly_after_refuses_overlap_within_a_turn():
    lexicon = _lexicon(
        _entry("wide", PhraseSpec("exact", "not financial advice")),
        _entry("narrow", PhraseSpec("exact", "financial advice")),
    )
    wide, narrow = find_hits(_transcript(_turn(0, "not financial advice")), lexicon)
    assert not narrow.strictly_after(wide)
    assert not wide.strictly_after(narrow)


def test_a_phrase_that_normalises_to_nothing_is_refused_at_construction():
    # It would otherwise match at every position and read as universally satisfied.
    with pytest.raises(LexiconError, match="normalises to nothing"):
        _lexicon(_entry("empty", PhraseSpec("punct", "!!! ...")))


def test_structural_lexicon_mistakes_are_refused():
    with pytest.raises(LexiconError, match="at least one phrase"):
        LexiconEntry(entry_id="empty", phrases=())
    with pytest.raises(LexiconError, match="duplicate phrase id"):
        _entry("e", PhraseSpec("same", "one"), PhraseSpec("same", "two"))
    with pytest.raises(LexiconError, match="duplicate entry id"):
        _lexicon(_entry("dup", PhraseSpec("a", "one")), _entry("dup", PhraseSpec("a", "two")))
    with pytest.raises(LexiconError, match="at least one entry"):
        Lexicon(lexicon_id="empty", locale="en-SG", entries=())
    with pytest.raises(LexiconError, match="max_gap_chars"):
        PhraseSpec("bad", "text", max_gap_chars=-1)


def test_a_lexicon_for_an_unsupported_language_is_refused_at_construction():
    with pytest.raises(UnsupportedLocaleError):
        _lexicon(_entry("e", PhraseSpec("a", "안녕")), locale="ko-KR")


def test_lexicon_locale_is_canonicalised_at_construction():
    assert _lexicon(_entry("e", PhraseSpec("a", "hello")), locale="EN_sg").locale == "en-SG"


def test_matching_is_replayable_within_a_run():
    lexicon = _lexicon(
        _entry("notice", PhraseSpec("exact", "recorded")),
        _entry("ack", PhraseSpec("loose", "yes ok", mode=MatchMode.ORDERED_SEGMENTS)),
    )
    transcript = _transcript(_turn(0, "yes ok, recorded"), _turn(1, "recorded again"))
    assert find_hits(transcript, lexicon) == find_hits(transcript, lexicon)
