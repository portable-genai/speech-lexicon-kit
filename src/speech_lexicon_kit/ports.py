"""The speech ports: speech-to-text, text-to-speech and diarization, as protocols.

A port is a declaration, not an implementation. These three are `typing.Protocol` and
`runtime_checkable`, so a consuming repo binds a managed adapter under its cloud profile, a
deterministic fixture adapter for the offline gate and a fail-fast placeholder on premises,
and the domain code depends on none of them.

Audio is referenced by URI, never read here. That is what keeps the promise on the tin: this
package performs no I/O, opens no file and holds no credential, so it installs and imports on
an air-gapped host and the offline test profile needs no network. Resolving a URI is the
adapter's job, because that is where the credential, the region and the retention policy
live.

The request objects carry the settings that change a RESULT rather than a transport detail:
the locale, whether word offsets are wanted, how many speakers to expect, and which audio
channel belongs to which role. Anything that only affects how the call is made (endpoint,
timeout, retries) belongs to the adapter's own configuration and is deliberately absent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .transcript import ChannelRole, SpeakerSegment, Transcript, TranscriptError

__all__ = [
    "AudioRef",
    "ChannelRoleBinding",
    "DiarizationPort",
    "DiarizationRequest",
    "DiarizationResult",
    "SpeechSynthesisRequest",
    "SpeechToTextPort",
    "SynthesisResult",
    "TextToSpeechPort",
    "TranscriptionRequest",
    "TranscriptionResult",
]


@dataclass(frozen=True, slots=True)
class AudioRef:
    """A reference to audio the adapter will resolve. Never the bytes themselves."""

    uri: str
    media_type: str
    sample_rate_hz: int | None = None
    channels: int = 1
    duration_ms: int | None = None

    def __post_init__(self) -> None:
        if not self.uri.strip():
            raise TranscriptError("AudioRef.uri must be non-empty")
        if not self.media_type.strip():
            raise TranscriptError("AudioRef.media_type must be non-empty")
        if self.channels < 1:
            raise TranscriptError(f"AudioRef.channels must be >= 1, got {self.channels}")
        if self.sample_rate_hz is not None and self.sample_rate_hz <= 0:
            raise TranscriptError("AudioRef.sample_rate_hz must be positive when given")
        if self.duration_ms is not None and self.duration_ms < 0:
            raise TranscriptError("AudioRef.duration_ms must be non-negative when given")


@dataclass(frozen=True, slots=True)
class ChannelRoleBinding:
    """Which role occupies an audio channel, declared by the caller rather than inferred.

    Stereo contact-centre capture puts the agent on one channel and the customer on the other,
    and that fact is known from the telephony configuration. Declaring it is exact; inferring
    it from a diarizer is a guess, and role is consequential (a required agent disclosure is
    not satisfied by the customer saying it).
    """

    channel: int
    role: ChannelRole
    speaker_id: str = ""

    def __post_init__(self) -> None:
        if self.channel < 0:
            raise TranscriptError(f"ChannelRoleBinding.channel must be >= 0, got {self.channel}")


@dataclass(frozen=True, slots=True)
class TranscriptionRequest:
    """What to transcribe, in what language, and what to return with it."""

    request_id: str
    audio: AudioRef
    locale: str
    diarize: bool = False
    expected_speakers: int | None = None
    word_offsets: bool = True
    channel_roles: tuple[ChannelRoleBinding, ...] = ()

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise TranscriptError("TranscriptionRequest.request_id must be non-empty")
        if not self.locale.strip():
            raise TranscriptError("TranscriptionRequest.locale must be non-empty")
        if self.expected_speakers is not None and self.expected_speakers < 1:
            raise TranscriptError("TranscriptionRequest.expected_speakers must be >= 1 when given")
        seen: set[int] = set()
        for binding in self.channel_roles:
            if binding.channel in seen:
                raise TranscriptError(
                    f"TranscriptionRequest {self.request_id!r}: channel {binding.channel} is "
                    f"bound to more than one role"
                )
            seen.add(binding.channel)


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    """A transcript plus what the recogniser could not do.

    ``truncated`` is separate from ``warnings`` because it is consequential: a scorecard built
    on a partial transcript may report a disclosure absent that was simply never transcribed,
    so a consumer must be able to branch on it without parsing prose.
    """

    transcript: Transcript
    truncated: bool = False
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SpeechSynthesisRequest:
    """Text to speak, and the voice settings that change the audio produced."""

    request_id: str
    text: str
    locale: str
    voice: str = ""
    audio_encoding: str = "audio/mpeg"
    speaking_rate: float | None = None
    pitch: float | None = None
    ssml: bool = False

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise TranscriptError("SpeechSynthesisRequest.request_id must be non-empty")
        if not self.text.strip():
            raise TranscriptError("SpeechSynthesisRequest.text must be non-empty")
        if not self.locale.strip():
            raise TranscriptError("SpeechSynthesisRequest.locale must be non-empty")
        if self.speaking_rate is not None and self.speaking_rate <= 0:
            raise TranscriptError(
                "SpeechSynthesisRequest.speaking_rate must be positive when given"
            )


@dataclass(frozen=True, slots=True)
class SynthesisResult:
    """Where the synthesised audio landed, and what produced it.

    Like the input side, the audio is a reference. An adapter that holds bytes in memory
    writes them wherever its retention policy says and returns the URI, so this package never
    becomes the thing that persisted a customer's voice.
    """

    request_id: str
    audio: AudioRef
    voice: str = ""
    characters_billed: int | None = None

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise TranscriptError("SynthesisResult.request_id must be non-empty")


@dataclass(frozen=True, slots=True)
class DiarizationRequest:
    """Audio to segment by speaker, with the speaker count if it is known."""

    request_id: str
    audio: AudioRef
    expected_speakers: int | None = None
    locale: str | None = None

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise TranscriptError("DiarizationRequest.request_id must be non-empty")
        if self.expected_speakers is not None and self.expected_speakers < 1:
            raise TranscriptError("DiarizationRequest.expected_speakers must be >= 1 when given")


@dataclass(frozen=True, slots=True)
class DiarizationResult:
    """Speaker segments in start order, as the diarizer resolved them."""

    request_id: str
    segments: tuple[SpeakerSegment, ...]
    warnings: tuple[str, ...] = ()


@runtime_checkable
class SpeechToTextPort(Protocol):
    """Turn recorded or streamed audio into a :class:`~speech_lexicon_kit.transcript.Transcript`."""

    def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:
        """Transcribe ``request.audio``, or raise. Never return a partial result silently."""
        ...


@runtime_checkable
class TextToSpeechPort(Protocol):
    """Turn text into audio: the outbound brief, the spoken warning, the callback message."""

    def synthesize(self, request: SpeechSynthesisRequest) -> SynthesisResult:
        """Synthesise ``request.text`` and return a reference to the audio produced."""
        ...


@runtime_checkable
class DiarizationPort(Protocol):
    """Attribute stretches of audio to speakers, separately from recognising the words."""

    def diarize(self, request: DiarizationRequest) -> DiarizationResult:
        """Segment ``request.audio`` by speaker."""
        ...
