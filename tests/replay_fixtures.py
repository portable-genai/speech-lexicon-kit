"""The golden-replay fixture set: synthetic conversations in every locale in scope.

This module builds the inputs and computes the outputs; the pinned expectations live in
``tests/golden/replay.json``. Both the pytest proof and ``scripts/run_replay.py`` import from
here so the eval and the test can never drift apart.

Everything in here is invented. The speakers are made-up names, the reference numbers are
obviously fictional, and the phrases are generic wordings written for this fixture: no real
institution's disclosure script appears in this package, which is also the reason none of it
belongs in the kit's own source.

The English cases share one script across every English region on purpose. English regions
resolve to the same normalisation rules, so their digests MUST come out identical, and the
Japanese one MUST NOT. That pair of assertions is what "the locales in scope" means here.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from speech_lexicon_kit import (
    SUPPORTED_LOCALES,
    ChannelRole,
    Lexicon,
    LexiconEntry,
    MatchMode,
    PhraseSequenceRequirement,
    PhraseSpec,
    SpeakerTurn,
    Transcript,
    WordOffset,
    canonical_locale,
    digest,
    evaluate_requirements,
    find_hits,
    normalise,
    rules_for,
    to_jsonable,
)

GOLDEN_PATH = Path(__file__).resolve().parent / "golden" / "replay.json"
GOLDEN_SCHEMA = "speech-lexicon-kit/golden-replay/v1"

# The whole point of taking as_of from the caller: pin it, and the run replays. A real caller
# passes datetime.now(UTC); the replay passes this, forever.
AS_OF = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
CONTACT_START = datetime(2026, 3, 1, 11, 59, 50, tzinfo=UTC)

_Word = tuple[str, int, int]
_TurnSpec = tuple[str, ChannelRole, str, int, int, tuple[_Word, ...]]


def _turn(index: int, spec: _TurnSpec) -> SpeakerTurn:
    """Build a turn, locating each word's character span by scanning left to right."""
    speaker_id, role, text, start_ms, end_ms, words = spec
    offsets: list[WordOffset] = []
    cursor = 0
    for token, word_start_ms, word_end_ms in words:
        found = text.index(token, cursor)
        offsets.append(
            WordOffset(
                text=token,
                char_start=found,
                char_end=found + len(token),
                start_ms=word_start_ms,
                end_ms=word_end_ms,
            )
        )
        cursor = found + len(token)
    return SpeakerTurn(
        index=index,
        speaker_id=speaker_id,
        role=role,
        text=text,
        start_ms=start_ms,
        end_ms=end_ms,
        words=tuple(offsets),
    )


# The last turn of each script deliberately carries NO word offsets, so the golden pins the
# UNVERIFIABLE outcome: a timing constraint over an untimed hit must not read as met.
_EN_TURNS: tuple[_TurnSpec, ...] = (
    (
        "spk-agent-1",
        ChannelRole.AGENT,
        "Good morning, you are speaking with Rowan at the Example Service Desk. "
        "This call may be recorded for quality and training.",
        0,
        7000,
        (("Good", 0, 400), ("This", 4000, 4300), ("recorded", 5200, 5800)),
    ),
    (
        "spk-customer-1",
        ChannelRole.CUSTOMER,
        "Morning. I would like to check my policy.",
        7000,
        9000,
        (("policy", 8400, 8900),),
    ),
    (
        "spk-agent-1",
        ChannelRole.AGENT,
        "Certainly. Before we continue, may I confirm your date of birth?",
        9000,
        13000,
        (("confirm", 10500, 11000), ("birth", 12300, 12800)),
    ),
    (
        "spk-customer-1",
        ChannelRole.CUSTOMER,
        "It is the fourth of April, nineteen ninety.",
        13000,
        15000,
        (("fourth", 13400, 13900),),
    ),
    (
        "spk-agent-1",
        ChannelRole.AGENT,
        "Thank you. Please note that this is general information and not financial advice.",
        15000,
        20000,
        (("Please", 15400, 15900), ("advice", 19100, 19600)),
    ),
    (
        "spk-agent-1",
        ChannelRole.AGENT,
        "Is there anything else today? Thank you for calling.",
        20000,
        24000,
        (),
    ),
)

_JA_TURNS: tuple[_TurnSpec, ...] = (
    (
        "spk-agent-1",
        ChannelRole.AGENT,
        "おはようございます。この通話は品質向上のため録音されます。",
        0,
        7000,
        (("おはよう", 0, 600), ("録音", 5200, 5800)),
    ),
    (
        "spk-customer-1",
        ChannelRole.CUSTOMER,
        "はい、わかりました。契約の内容を確認したいのですが。",
        7000,
        9000,
        (("契約", 8400, 8900),),
    ),
    (
        "spk-agent-1",
        ChannelRole.AGENT,
        "続けるまえに、本人確認をさせていただきます。",
        9000,
        13000,
        (("本人確認", 10500, 11000),),
    ),
    (
        "spk-customer-1",
        ChannelRole.CUSTOMER,
        "生年月日は千九百九十年四月四日です。",
        13000,
        15000,
        (("生年月日", 13400, 13900),),
    ),
    (
        "spk-agent-1",
        ChannelRole.AGENT,
        "ありがとうございます。こちらは一般的なご案内であり、投資助言ではありません。",
        15000,
        20000,
        (("ご案内", 17100, 17600), ("投資助言", 19100, 19600)),
    ),
    (
        "spk-agent-1",
        ChannelRole.AGENT,
        "本日はお電話ありがとうございました。",
        20000,
        24000,
        (),
    ),
)

_TURNS_BY_LANGUAGE: dict[str, tuple[_TurnSpec, ...]] = {"en": _EN_TURNS, "ja": _JA_TURNS}

_EN_ENTRIES: tuple[LexiconEntry, ...] = (
    LexiconEntry(
        entry_id="recording_notice",
        phrases=(
            PhraseSpec("exact", "this call may be recorded"),
            PhraseSpec("loose", "call recorded", mode=MatchMode.ORDERED_SEGMENTS, max_gap_chars=14),
        ),
        tags=("disclosure",),
    ),
    LexiconEntry(
        entry_id="identity_check",
        phrases=(PhraseSpec("exact", "confirm your date of birth"),),
        tags=("verification",),
    ),
    LexiconEntry(
        entry_id="advice_disclaimer",
        phrases=(PhraseSpec("exact", "not financial advice"),),
        tags=("disclosure",),
    ),
    LexiconEntry(
        entry_id="closing",
        phrases=(PhraseSpec("exact", "thank you for calling"),),
        tags=("courtesy",),
    ),
    LexiconEntry(
        entry_id="product_reference",
        phrases=(PhraseSpec("exact", "policy"),),
        tags=("topic",),
    ),
    # Never spoken in the script: the ABSENT outcome has to be pinned too.
    LexiconEntry(
        entry_id="callback_offer",
        phrases=(PhraseSpec("exact", "arrange a callback"),),
        tags=("courtesy",),
    ),
)

_JA_ENTRIES: tuple[LexiconEntry, ...] = (
    LexiconEntry(
        entry_id="recording_notice",
        phrases=(
            PhraseSpec("exact", "録音されます"),
            PhraseSpec(
                "loose",
                "この通話は 録音されます",
                mode=MatchMode.ORDERED_SEGMENTS,
                max_gap_chars=14,
            ),
        ),
        tags=("disclosure",),
    ),
    LexiconEntry(
        entry_id="identity_check",
        phrases=(PhraseSpec("exact", "本人確認"),),
        tags=("verification",),
    ),
    LexiconEntry(
        entry_id="advice_disclaimer",
        phrases=(PhraseSpec("exact", "投資助言ではありません"),),
        tags=("disclosure",),
    ),
    LexiconEntry(
        entry_id="closing",
        phrases=(PhraseSpec("exact", "ありがとうございました"),),
        tags=("courtesy",),
    ),
    LexiconEntry(
        entry_id="product_reference",
        phrases=(PhraseSpec("exact", "ご案内"),),
        tags=("topic",),
    ),
    LexiconEntry(
        entry_id="callback_offer",
        phrases=(PhraseSpec("exact", "折り返しお電話"),),
        tags=("courtesy",),
    ),
)

_ENTRIES_BY_LANGUAGE: dict[str, tuple[LexiconEntry, ...]] = {"en": _EN_ENTRIES, "ja": _JA_ENTRIES}

# Probe strings chosen because each one is a place two hand-rolled normalisers would disagree:
# casing and punctuation, hyphenation, full-width forms, half-width kana with voicing marks,
# typographic dashes standing in for the prolonged sound mark, and the pair that proves the
# prolonged mark is kept rather than dropped.
_PROBES: dict[str, tuple[tuple[str, str], ...]] = {
    "en": (
        ("casing_and_punctuation", "This CALL may be recorded, for quality."),
        ("hyphenation", "Re-insurance  and   co-operate; 12,345"),
        ("full_width", "Ｔｈｅ ｃａｌｌ"),
        ("accents", "Café naïve résumé"),
        ("edges", "   ...  spaced out ,,, "),
    ),
    "ja": (
        ("half_width_kana", "ｺｰﾋｰ　ﾃﾞｰﾀ ＡＢＣ１２３"),
        ("spacing_and_kana", "この お通話は 品質のため 録音 されます。"),
        ("dash_hyphen", "コ‐ヒ‐"),
        ("dash_minus", "コ−ヒ−"),
        ("prolonged_kept", "ビル と ビール"),
    ),
}

_REQUIREMENTS: tuple[PhraseSequenceRequirement, ...] = (
    # Present, in order, inside the window: SATISFIED.
    PhraseSequenceRequirement(
        requirement_id="R1-opening-sequence",
        step_entry_ids=("recording_notice", "identity_check", "advice_disclaimer"),
        role=ChannelRole.AGENT,
        deadline_ms=25_000,
    ),
    # The same steps in the wrong order: OUT_OF_ORDER, not ABSENT.
    PhraseSequenceRequirement(
        requirement_id="R2-inverted-sequence",
        step_entry_ids=("advice_disclaimer", "recording_notice"),
        role=ChannelRole.AGENT,
    ),
    # Never spoken, on a closed transcript: ABSENT.
    PhraseSequenceRequirement(
        requirement_id="R3-callback-offer",
        step_entry_ids=("callback_offer",),
        role=ChannelRole.AGENT,
    ),
    # Spoken in an untimed turn under a deadline: UNVERIFIABLE.
    PhraseSequenceRequirement(
        requirement_id="R4-closing-in-time",
        step_entry_ids=("closing",),
        role=ChannelRole.AGENT,
        deadline_ms=30_000,
    ),
    # In order but wider than the allowed span: LATE.
    PhraseSequenceRequirement(
        requirement_id="R5-tight-window",
        step_entry_ids=("recording_notice", "advice_disclaimer"),
        role=ChannelRole.AGENT,
        within_ms=5_000,
    ),
    # Said by the agent, demanded of the customer: ABSENT, which is the role filter working.
    PhraseSequenceRequirement(
        requirement_id="R6-customer-must-disclose",
        step_entry_ids=("advice_disclaimer",),
        role=ChannelRole.CUSTOMER,
    ),
)

# On the OPEN transcript only the first two turns exist, so the identity check has not happened
# yet. With the deadline still ahead of AS_OF that is PENDING, not a breach.
_LIVE_REQUIREMENTS: tuple[PhraseSequenceRequirement, ...] = (
    PhraseSequenceRequirement(
        requirement_id="L1-identity-check-pending",
        step_entry_ids=("identity_check",),
        role=ChannelRole.AGENT,
        deadline_ms=120_000,
    ),
    PhraseSequenceRequirement(
        requirement_id="L2-identity-check-overdue",
        step_entry_ids=("identity_check",),
        role=ChannelRole.AGENT,
        deadline_ms=5_000,
    ),
)


def language_of(locale: str) -> str:
    return canonical_locale(locale).split("-", 1)[0]


def lexicon_for(locale: str) -> Lexicon:
    """The fixture lexicon for a locale. Its id is per-LANGUAGE, so regions digest alike."""
    language = language_of(locale)
    return Lexicon(
        lexicon_id=f"replay-{language}",
        locale=locale,
        entries=_ENTRIES_BY_LANGUAGE[language],
        version="v1",
    )


def closed_transcript_for(locale: str) -> Transcript:
    """A completed contact: every outcome except PENDING is decidable on it."""
    language = language_of(locale)
    specs = _TURNS_BY_LANGUAGE[language]
    return Transcript(
        transcript_id=f"T-REPLAY-{language.upper()}-001",
        locale=locale,
        turns=tuple(_turn(index, spec) for index, spec in enumerate(specs)),
        started_at=CONTACT_START,
        ended_at=datetime(2026, 3, 1, 12, 0, 14, tzinfo=UTC),
        audio_duration_ms=24_000,
        engine="fixture",
    )


def live_transcript_for(locale: str) -> Transcript:
    """A contact still in progress: ended_at is None, so absence is not yet a finding."""
    language = language_of(locale)
    specs = _TURNS_BY_LANGUAGE[language][:2]
    return Transcript(
        transcript_id=f"T-REPLAY-{language.upper()}-002",
        locale=locale,
        turns=tuple(_turn(index, spec) for index, spec in enumerate(specs)),
        started_at=CONTACT_START,
        ended_at=None,
        engine="fixture",
    )


_DETAIL_SECTIONS = (
    "normalisation",
    "closed_hits",
    "closed_adherence",
    "live_hits",
    "live_adherence",
)


def case_payload(locale: str) -> dict[str, Any]:
    """Run the whole kernel over one locale and return its jsonable result."""
    language = language_of(locale)
    lexicon = lexicon_for(locale)

    # The probe records the readable normalised form plus a digest of the WHOLE NormalisedText,
    # offset tables included. The digest is what pins the source mapping; the text is what lets
    # a reviewer check the pin by eye rather than trusting a hash.
    probes = {
        label: {"text": normalised.text, "digest": digest(normalised)}
        for label, normalised in (
            (label, normalise(text, rules_for(locale))) for label, text in _PROBES[language]
        )
    }

    closed = closed_transcript_for(locale)
    closed_hits = find_hits(closed, lexicon)
    closed_report = evaluate_requirements(closed, closed_hits, _REQUIREMENTS, as_of=AS_OF)

    live = live_transcript_for(locale)
    live_hits = find_hits(live, lexicon)
    live_report = evaluate_requirements(live, live_hits, _LIVE_REQUIREMENTS, as_of=AS_OF)

    payload: dict[str, Any] = {
        "language": language,
        "normalisation": probes,
        "closed_hits": to_jsonable(closed_hits),
        "closed_adherence": to_jsonable(closed_report),
        "live_hits": to_jsonable(live_hits),
        "live_adherence": to_jsonable(live_report),
    }
    payload["case_digest"] = digest(payload)
    return payload


def replay_payload() -> dict[str, Any]:
    """The full replay across every locale in scope, plus the overall digest.

    Split deliberately in two. ``cases`` carries one digest per LOCALE, which is what proves
    every locale in scope reproduces; ``details`` carries the full readable evidence once per
    LANGUAGE, because six English regions producing byte-identical output is the finding, and
    writing that output out six times would be noise dressed as evidence. The per-locale
    digest still covers every byte of the detail, so nothing is pinned less tightly.
    """
    cases: dict[str, Any] = {}
    details: dict[str, Any] = {}
    for locale in SUPPORTED_LOCALES:
        case = case_payload(locale)
        language = case["language"]
        detail = {section: case[section] for section in _DETAIL_SECTIONS}
        if language in details and details[language] != detail:
            raise AssertionError(
                f"{locale}: same language {language!r} produced different output; the fixture "
                f"has become locale-dependent in a way the golden cannot express"
            )
        details[language] = detail
        cases[locale] = {"language": language, "case_digest": case["case_digest"]}
    return {
        "schema": GOLDEN_SCHEMA,
        "as_of": AS_OF.isoformat(),
        "locales": list(SUPPORTED_LOCALES),
        "cases": cases,
        "details": details,
        "overall_digest": digest(
            {locale: case["case_digest"] for locale, case in sorted(cases.items())}
        ),
    }


def load_golden(path: Path = GOLDEN_PATH) -> dict[str, Any]:
    """Read the pinned expectations."""
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def write_golden(payload: dict[str, Any], path: Path = GOLDEN_PATH) -> None:
    """Rewrite the pinned expectations. Only ever run deliberately."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def compare(expected: dict[str, Any], actual: dict[str, Any]) -> tuple[str, ...]:
    """Return one line per difference between a pinned payload and a fresh run.

    Reports the schema, the locale set, each per-locale digest and the overall digest
    separately, so a drift report names WHICH locale moved rather than just that something
    did. An empty result is the only pass.
    """
    problems: list[str] = []
    if expected.get("schema") != actual["schema"]:
        problems.append(f"schema: expected {expected.get('schema')!r}, got {actual['schema']!r}")
    if expected.get("as_of") != actual["as_of"]:
        problems.append(f"as_of: expected {expected.get('as_of')!r}, got {actual['as_of']!r}")
    expected_locales = list(expected.get("locales", []))
    if expected_locales != actual["locales"]:
        problems.append(f"locales: expected {expected_locales}, got {actual['locales']}")
    expected_cases: dict[str, Any] = expected.get("cases", {})
    for locale, case in actual["cases"].items():
        pinned = expected_cases.get(locale)
        if pinned is None:
            problems.append(f"{locale}: no pinned case")
            continue
        if pinned.get("case_digest") != case["case_digest"]:
            problems.append(
                f"{locale}: digest drift, expected {pinned.get('case_digest')}, "
                f"got {case['case_digest']}"
            )
    for locale in expected_cases:
        if locale not in actual["cases"]:
            problems.append(f"{locale}: pinned but no longer produced")

    expected_details: dict[str, Any] = expected.get("details", {})
    for language, detail in actual["details"].items():
        pinned_detail = expected_details.get(language)
        if pinned_detail is None:
            problems.append(f"{language}: no pinned detail")
            continue
        for section in _DETAIL_SECTIONS:
            if pinned_detail.get(section) != detail[section]:
                problems.append(f"{language}: section {section!r} differs")
    if expected.get("overall_digest") != actual["overall_digest"]:
        problems.append(
            f"overall digest: expected {expected.get('overall_digest')}, "
            f"got {actual['overall_digest']}"
        )
    return tuple(problems)
