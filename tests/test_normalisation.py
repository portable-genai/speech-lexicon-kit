"""Locale-sensitive normalisation: the folding rules, and the map back to the source."""

from __future__ import annotations

import pytest

from speech_lexicon_kit.normalisation import (
    ENGLISH_RULES,
    JAPANESE_RULES,
    SUPPORTED_LOCALES,
    LocaleRules,
    NormalisedText,
    UnsupportedLocaleError,
    canonical_locale,
    normalise,
    rules_for,
)


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("en-SG", "en-SG"),
        ("EN-sg", "en-SG"),
        ("ja_jp", "ja-JP"),
        ("JA", "ja"),
        ("zh-hant-hk", "zh-Hant-HK"),
    ],
)
def test_locale_tags_canonicalise(given, expected):
    assert canonical_locale(given) == expected


@pytest.mark.parametrize("given", ["", "e", "english-SG", "en-", "en-SGP", "en SG"])
def test_malformed_locale_tags_are_refused(given):
    with pytest.raises(UnsupportedLocaleError):
        canonical_locale(given)


@pytest.mark.parametrize("locale", SUPPORTED_LOCALES)
def test_every_locale_in_scope_resolves(locale):
    assert isinstance(rules_for(locale), LocaleRules)


def test_any_region_of_a_known_language_resolves():
    # Regions share rules, so a locale nobody listed still normalises correctly rather than
    # refusing for a difference that does not exist.
    assert rules_for("en-NZ") is ENGLISH_RULES
    assert rules_for("ja") is JAPANESE_RULES


@pytest.mark.parametrize("locale", ["ko-KR", "th-TH", "zh-Hans-CN"])
def test_an_unknown_language_refuses_rather_than_borrowing_english(locale):
    # Fail closed: silently applying English word-boundary rules to a language written
    # without spaces would produce hits that look plausible and are wrong.
    with pytest.raises(UnsupportedLocaleError, match="no normalisation rules"):
        rules_for(locale)


def test_english_folds_case_and_punctuation_to_separators():
    assert normalise("This CALL may be recorded, for quality.", "en-SG").text == (
        "this call may be recorded for quality"
    )
    # Punctuation becomes a separator rather than vanishing, so two tokens never weld.
    assert normalise("Re-insurance and co-operate", "en-GB").text == "re insurance and co operate"


def test_english_collapses_runs_and_strips_edges():
    assert normalise("   ...  spaced   out ,,, ", "en-AU").text == "spaced out"


def test_full_width_forms_fold_under_nfkc():
    assert normalise("Ｔｈｅ ｃａｌｌ １２３", "en-US").text == "the call 123"


def test_japanese_removes_separators_entirely():
    # Whitespace in a Japanese transcript is recogniser noise, not a token boundary.
    assert normalise("この お通話は 録音 されます。", "ja-JP").text == "コノオ通話ハ録音サレマス"


def test_japanese_folds_hiragana_to_katakana_and_half_width_kana():
    assert normalise("ｺｰﾋｰ　ﾃﾞｰﾀ", "ja-JP").text == "コーヒーデータ"
    assert normalise("こーひー", "ja-JP").text == normalise("コーヒー", "ja-JP").text


def test_japanese_folds_typographic_dashes_to_the_prolonged_sound_mark():
    target = normalise("コーヒー", "ja-JP").text
    assert normalise("コ‐ヒ‐", "ja-JP").text == target
    assert normalise("コ−ヒ−", "ja-JP").text == target


def test_japanese_keeps_the_prolonged_mark_so_different_words_stay_different():
    # Dropping it would be more forgiving and would also equate two unrelated words, which is
    # the worse failure: a matcher must not invent a hit.
    assert normalise("ビル", "ja-JP").text != normalise("ビール", "ja-JP").text


def test_ascii_hyphen_is_not_folded_in_japanese():
    # It is a numeric separator far more often than a mis-transcribed prolonged mark.
    assert normalise("03-1234-5678", "ja-JP").text == "0312345678"


def test_half_width_voicing_marks_compose_with_their_base():
    # Per-character NFKC would leave a stray voicing mark; clustering is what prevents it.
    assert normalise("ﾃﾞｰﾀ", "ja-JP").text == "データ"


def test_source_spans_resolve_back_to_the_original_text():
    original = "This CALL may be recorded, for quality."
    normalised = normalise(original, "en-SG")
    start = normalised.text.index("recorded")
    span = normalised.source_span(start, start + len("recorded"))
    assert original[span[0] : span[1]] == "recorded"


def test_source_spans_survive_expansion_and_collapse():
    original = "Ｔｈｅ    ｃａｌｌ"
    normalised = normalise(original, "en-SG")
    assert normalised.text == "the call"
    span = normalised.source_span(4, 8)
    assert original[span[0] : span[1]] == "ｃａｌｌ"


def test_an_empty_span_maps_to_a_point_not_an_inverted_range():
    normalised = normalise("hello world", "en-SG")
    start, end = normalised.source_span(3, 3)
    assert start == end


def test_out_of_range_spans_are_refused():
    normalised = normalise("hello", "en-SG")
    with pytest.raises(ValueError, match="out of range"):
        normalised.source_span(0, 99)
    with pytest.raises(ValueError, match="out of range"):
        normalised.source_span(3, 1)


def test_offset_tables_always_match_the_normalised_length():
    with pytest.raises(ValueError, match="one entry per normalised character"):
        NormalisedText(
            text="abc",
            source_starts=(0, 1),
            source_ends=(1, 2),
            source_length=3,
            rules=ENGLISH_RULES,
        )


def test_boundaries_exist_only_where_the_language_has_them():
    english = normalise("great insurance cover", "en-SG")
    assert english.is_boundary(english.text.index("insurance"))
    assert not english.is_boundary(len("great in"))
    japanese = normalise("保険の話", "ja-JP")
    assert all(japanese.is_boundary(position) for position in range(len(japanese.text) + 1))


def test_normalisation_is_a_pure_function_of_text_and_rules():
    text = "Ｔｈｅ call ,, may be RECORDED"
    first = normalise(text, "en-SG")
    second = normalise(text, ENGLISH_RULES)
    assert first == second


def test_rules_can_be_supplied_directly_for_an_unregistered_language():
    # The escape hatch is explicit construction, never an inferred default.
    custom = LocaleRules(language="ko", word_separated=True)
    assert normalise("안녕  하세요", custom).text == "안녕 하세요"
