"""Testes unitários para o serviço de transcrição Whisper."""

import pytest
from unittest.mock import AsyncMock, patch
from src.transcriber.schemas import TranscriptionResponse, TranscriptionSegment
from src.transcriber.service import whisper_service


def test_transcription_schemas():
    """Valida serialização dos schemas de transcrição."""
    segment = TranscriptionSegment(id=0, start=0.0, end=2.5, text="Olá mundo")
    assert segment.id == 0
    assert segment.text == "Olá mundo"

    response = TranscriptionResponse(
        audio_id="audio_test_123",
        language="pt",
        language_probability=0.99,
        duration=2.5,
        text="Olá mundo",
        segments=[segment],
        processing_time_ms=150.0,
    )
    assert response.audio_id == "audio_test_123"
    assert response.duration == 2.5
    assert len(response.segments) == 1


@pytest.mark.asyncio
async def test_transcribe_audio_mocked():
    """Valida o método transcribe_audio com mock."""
    mock_segments = [TranscriptionSegment(id=0, start=0.0, end=1.5, text="Teste de áudio")]
    with patch.object(
        whisper_service,
        "transcribe_audio",
        new_callable=AsyncMock,
        return_value=("Teste de áudio", "pt", 0.98, 1.5, mock_segments),
    ):
        text, lang, prob, dur, segments = await whisper_service.transcribe_audio("dummy.ogg")
        assert text == "Teste de áudio"
        assert lang == "pt"
        assert prob == 0.98
        assert dur == 1.5
        assert len(segments) == 1
