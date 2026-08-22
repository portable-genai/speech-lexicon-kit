"""speech-lexicon-kit: the shared speech kernel for hexagonal agent repos.

One versioned source of truth for the speech layer that a contact-centre copilot, a
conversation-QA scorecard, a proactive-outreach service, a scam-interdiction warning, a
comms-surveillance investigator, a meeting-capture tool and an ops shift brief would
otherwise each re-implement and drift on:

* **The ports** (:mod:`speech_lexicon_kit.ports`) - ``SpeechToTextPort``,
  ``TextToSpeechPort`` and ``DiarizationPort`` as runtime-checkable protocols, with request
  and result types that carry only what changes a result.
* **The transcript types** (:mod:`speech_lexicon_kit.transcript`) - ``Transcript``,
  ``SpeakerTurn``, ``WordOffset``, ``ChannelRole``, ``RedactionSpan`` and ``SpeakerSegment``,
  frozen and validated, so a citation of "turn 7, characters 12 to 34" means the same thing
  in every repo.
* **Locale-sensitive normalisation** (:mod:`speech_lexicon_kit.normalisation`) - deterministic
  folding with an exact map back to the source text, fail-closed on an unknown language.
* **Phrase matching** (:mod:`speech_lexicon_kit.matching`) - lexicon hits with spans, speaker,
  role and audio timing. The kit carries the matching; the PHRASES stay in the consuming repo,
  because a required wording is reviewed vertical policy and must not need a release of a
  shared package to change.
* **Ordered-phrase adherence** (:mod:`speech_lexicon_kit.adherence`) - presence, order and
  timing, with ``PENDING`` for a conversation still in progress and ``UNVERIFIABLE`` for a
  deadline that cannot be checked.
* **Replay mechanics** (:mod:`speech_lexicon_kit.replay`) - the canonical encoding and digest
  that turn "this is deterministic" into something a test can assert.

**Pure standard library. No clock. No I/O.** Any function that needs a time takes ``as_of``
from the caller, and audio is referenced by URI for an adapter to resolve. Nothing here opens
a file, a socket or a credential.
"""

from __future__ import annotations

from . import adherence, matching, normalisation, ports, redaction, replay, transcript
from .adherence import (
    AdherenceError,
    AdherenceOutcome,
    AdherenceReport,
    PhraseSequenceRequirement,
    SequenceAdherence,
    StepEvidence,
    evaluate_requirements,
    evaluate_sequence,
    ordered_hit_chain,
    present_entry_ids,
)
from .matching import (
    DEFAULT_MAX_GAP_CHARS,
    Lexicon,
    LexiconEntry,
    LexiconError,
    LexiconHit,
    LocaleMismatchError,
    MatchMode,
    PhraseSpec,
    TextMatch,
    find_hits,
    find_matches,
)
from .normalisation import (
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
from .ports import (
    AudioRef,
    ChannelRoleBinding,
    DiarizationPort,
    DiarizationRequest,
    DiarizationResult,
    SpeechSynthesisRequest,
    SpeechToTextPort,
    SynthesisResult,
    TextToSpeechPort,
    TranscriptionRequest,
    TranscriptionResult,
)
from .redaction import RedactedText, apply_redactions, redact_transcript
from .replay import (
    ReplayEncodingError,
    canonical_bytes,
    canonical_json,
    digest,
    to_jsonable,
)
from .transcript import (
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

__version__ = "0.0.1"

__all__ = [
    "DEFAULT_MAX_GAP_CHARS",
    "ENGLISH_RULES",
    "JAPANESE_RULES",
    "SUPPORTED_LOCALES",
    "AdherenceError",
    "AdherenceOutcome",
    "AdherenceReport",
    "AudioRef",
    "ChannelRole",
    "ChannelRoleBinding",
    "DiarizationPort",
    "DiarizationRequest",
    "DiarizationResult",
    "Lexicon",
    "LexiconEntry",
    "LexiconError",
    "LexiconHit",
    "LocaleMismatchError",
    "LocaleRules",
    "MatchMode",
    "NormalisedText",
    "PhraseSequenceRequirement",
    "PhraseSpec",
    "RedactedText",
    "RedactionSpan",
    "ReplayEncodingError",
    "SequenceAdherence",
    "SpeakerSegment",
    "SpeakerTurn",
    "SpeechSynthesisRequest",
    "SpeechToTextPort",
    "StepEvidence",
    "SynthesisResult",
    "TextMatch",
    "TextToSpeechPort",
    "Transcript",
    "TranscriptError",
    "TranscriptionRequest",
    "TranscriptionResult",
    "UnsupportedLocaleError",
    "WordOffset",
    "__version__",
    "adherence",
    "apply_redactions",
    "canonical_bytes",
    "canonical_json",
    "canonical_locale",
    "digest",
    "evaluate_requirements",
    "evaluate_sequence",
    "find_hits",
    "find_matches",
    "matching",
    "merge_diarization",
    "normalisation",
    "normalise",
    "ordered_hit_chain",
    "ports",
    "present_entry_ids",
    "redact_transcript",
    "redaction",
    "replay",
    "rules_for",
    "span_timing",
    "to_jsonable",
    "transcript",
]
