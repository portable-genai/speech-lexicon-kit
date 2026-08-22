"""The ports: protocol conformance, request validation, and the no-I/O boundary."""

from __future__ import annotations

import pytest

from speech_lexicon_kit.ports import (
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
from speech_lexicon_kit.transcript import (
    ChannelRole,
    SpeakerSegment,
    SpeakerTurn,
    Transcript,
    TranscriptError,
)

AUDIO = AudioRef(uri="fixture://contact/0001.wav", media_type="audio/wav", channels=2)


class FixtureSpeechToText:
    """The offline adapter shape a consuming repo binds under its local profile."""

    def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:
        turn = SpeakerTurn(
            index=0,
            speaker_id="spk-0",
            role=ChannelRole.AGENT,
            text="this call may be recorded",
        )
        return TranscriptionResult(
            transcript=Transcript(
                transcript_id=request.request_id,
                locale=request.locale,
                turns=(turn,),
                engine="fixture",
            )
        )


class FixtureTextToSpeech:
    def synthesize(self, request: SpeechSynthesisRequest) -> SynthesisResult:
        return SynthesisResult(
            request_id=request.request_id,
            audio=AudioRef(uri="fixture://out/0001.mp3", media_type=request.audio_encoding),
            voice=request.voice,
        )


class FixtureDiarizer:
    def diarize(self, request: DiarizationRequest) -> DiarizationResult:
        return DiarizationResult(
            request_id=request.request_id,
            segments=(SpeakerSegment(speaker_id="spk-0", start_ms=0, end_ms=1000),),
        )


class NotAnAdapter:
    def do_something_else(self) -> None: ...


def test_the_fixture_adapters_satisfy_their_ports():
    assert isinstance(FixtureSpeechToText(), SpeechToTextPort)
    assert isinstance(FixtureTextToSpeech(), TextToSpeechPort)
    assert isinstance(FixtureDiarizer(), DiarizationPort)


def test_an_unrelated_object_does_not():
    assert not isinstance(NotAnAdapter(), SpeechToTextPort)
    assert not isinstance(NotAnAdapter(), TextToSpeechPort)
    assert not isinstance(NotAnAdapter(), DiarizationPort)


def test_a_bound_adapter_round_trips_a_request():
    request = TranscriptionRequest(
        request_id="T-EXAMPLE-001",
        audio=AUDIO,
        locale="en-SG",
        diarize=True,
        expected_speakers=2,
        channel_roles=(
            ChannelRoleBinding(channel=0, role=ChannelRole.AGENT, speaker_id="spk-agent"),
            ChannelRoleBinding(channel=1, role=ChannelRole.CUSTOMER),
        ),
    )
    result = FixtureSpeechToText().transcribe(request)
    assert result.transcript.transcript_id == "T-EXAMPLE-001"
    assert result.truncated is False


def test_truncation_is_a_flag_not_a_prose_warning():
    # A consumer has to branch on it: a scorecard over a partial transcript can report a
    # disclosure absent that was merely never transcribed.
    result = TranscriptionResult(
        transcript=Transcript(transcript_id="T-EXAMPLE-002", locale="en-SG", turns=()),
        truncated=True,
        warnings=("audio ended mid-turn",),
    )
    assert result.truncated


def test_audio_is_a_reference_so_the_kit_performs_no_io():
    assert not hasattr(AUDIO, "bytes")
    assert AUDIO.uri.startswith("fixture://")


def test_audio_refs_validate_their_own_shape():
    with pytest.raises(TranscriptError, match="uri must be non-empty"):
        AudioRef(uri="  ", media_type="audio/wav")
    with pytest.raises(TranscriptError, match="media_type must be non-empty"):
        AudioRef(uri="fixture://a.wav", media_type="")
    with pytest.raises(TranscriptError, match="channels must be >= 1"):
        AudioRef(uri="fixture://a.wav", media_type="audio/wav", channels=0)
    with pytest.raises(TranscriptError, match="sample_rate_hz must be positive"):
        AudioRef(uri="fixture://a.wav", media_type="audio/wav", sample_rate_hz=0)


def test_a_channel_may_not_be_bound_to_two_roles():
    with pytest.raises(TranscriptError, match="more than one role"):
        TranscriptionRequest(
            request_id="T-EXAMPLE-003",
            audio=AUDIO,
            locale="en-SG",
            channel_roles=(
                ChannelRoleBinding(channel=0, role=ChannelRole.AGENT),
                ChannelRoleBinding(channel=0, role=ChannelRole.CUSTOMER),
            ),
        )


def test_transcription_requests_validate_their_own_shape():
    with pytest.raises(TranscriptError, match="request_id must be non-empty"):
        TranscriptionRequest(request_id=" ", audio=AUDIO, locale="en-SG")
    with pytest.raises(TranscriptError, match="locale must be non-empty"):
        TranscriptionRequest(request_id="T-EXAMPLE-004", audio=AUDIO, locale="")
    with pytest.raises(TranscriptError, match="expected_speakers must be >= 1"):
        TranscriptionRequest(
            request_id="T-EXAMPLE-004", audio=AUDIO, locale="en-SG", expected_speakers=0
        )


def test_synthesis_requests_validate_their_own_shape():
    with pytest.raises(TranscriptError, match="text must be non-empty"):
        SpeechSynthesisRequest(request_id="S-EXAMPLE-001", text="  ", locale="ja-JP")
    with pytest.raises(TranscriptError, match="speaking_rate must be positive"):
        SpeechSynthesisRequest(
            request_id="S-EXAMPLE-001", text="brief", locale="ja-JP", speaking_rate=0
        )


def test_synthesis_returns_a_reference_so_the_kit_never_persists_a_voice():
    result = FixtureTextToSpeech().synthesize(
        SpeechSynthesisRequest(
            request_id="S-EXAMPLE-002",
            text="Your shift handover brief is ready.",
            locale="en-AU",
            voice="example-voice-1",
        )
    )
    assert isinstance(result.audio, AudioRef)
    assert result.voice == "example-voice-1"


def test_diarization_requests_validate_their_own_shape():
    with pytest.raises(TranscriptError, match="request_id must be non-empty"):
        DiarizationRequest(request_id="", audio=AUDIO)
    with pytest.raises(TranscriptError, match="expected_speakers must be >= 1"):
        DiarizationRequest(request_id="D-EXAMPLE-001", audio=AUDIO, expected_speakers=0)


def test_no_module_in_the_package_imports_a_clock_io_or_network_library():
    # The stdlib-only, no-clock, no-I/O promise is what lets this install on an air-gapped
    # host and replay byte for byte, so it is asserted rather than merely documented. Reading
    # the imports statically also catches "from time import monotonic", which inspecting the
    # imported module's namespace would miss.
    import ast
    from pathlib import Path

    import speech_lexicon_kit

    forbidden = {
        "asyncio",
        "http",
        "httpx",
        "os",
        "pathlib",
        "random",
        "requests",
        "secrets",
        "shutil",
        "socket",
        "sqlite3",
        "subprocess",
        "tempfile",
        "time",
        "urllib",
        "uuid",
    }
    sources = sorted(Path(speech_lexicon_kit.__file__).parent.glob("*.py"))
    assert sources, "the package should have modules to inspect"
    for source in sources:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module.split(".")[0])
        leaked = forbidden.intersection(imported)
        assert not leaked, f"{source.name} imports {sorted(leaked)}"
