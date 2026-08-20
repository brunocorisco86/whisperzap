"""Testes de integração para os endpoints HTTP da API FastAPI."""

import io
import pytest
import httpx
from unittest.mock import AsyncMock, patch
from src.main import app
from src.transcriber.schemas import TranscriptionSegment


@pytest.mark.asyncio
async def test_health_endpoint():
    """Valida o endpoint GET /health."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "whisper_model" in data


@pytest.mark.asyncio
async def test_ai_revise_endpoint_with_mock_provider():
    """Valida o endpoint POST /ai/revise usando o provedor mock."""
    with patch("src.ai_gateway.router.get_ai_provider") as mock_get_provider:
        from src.ai_gateway.providers.mock import MockProvider
        mock_get_provider.return_value = MockProvider()

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "text": "entao preciso falar com joao",
                "context": "Contexto do projeto avícola",
            }
            response = await client.post("/ai/revise", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert "text_revised" in data
            assert data["provider"] == "mock"
            assert data["text_revised"] == "Entao preciso falar com joao."


@pytest.mark.asyncio
async def test_ai_revise_endpoint_empty_text():
    """Valida erro 422 para texto vazio em POST /ai/revise."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/ai/revise", json={"text": "   "})
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_transcribe_endpoint():
    """Valida o endpoint POST /transcribe com upload multipart."""
    mock_segments = [
        TranscriptionSegment(id=0, start=0.0, end=1.0, text="Mensagem de teste")
    ]
    with patch("src.transcriber.router.whisper_service.transcribe_audio", new_callable=AsyncMock) as mock_transcribe:
        mock_transcribe.return_value = ("Mensagem de teste", "pt", 0.99, 1.0, mock_segments, None)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            fake_audio_file = io.BytesIO(b"fake audio bytes for testing")
            files = {"file": ("test_voice.ogg", fake_audio_file, "audio/ogg")}

            response = await client.post("/transcribe", files=files)
            assert response.status_code == 200
            data = response.json()
            assert data["text"] == "Mensagem de teste"
            assert data["language"] == "pt"
            assert data["duration"] == 1.0
            assert len(data["segments"]) == 1


@pytest.mark.asyncio
async def test_transcribe_base64_endpoint():
    """Valida o endpoint POST /transcribe/base64 com string base64 válida."""
    import base64
    mock_segments = [
        TranscriptionSegment(id=0, start=0.0, end=1.0, text="Mensagem base64")
    ]
    with patch("src.transcriber.router.whisper_service.transcribe_audio", new_callable=AsyncMock) as mock_transcribe:
        mock_transcribe.return_value = ("Mensagem base64", "pt", 0.99, 1.0, mock_segments, None)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            fake_b64 = base64.b64encode(b"A" * 64).decode("utf-8")
            response = await client.post("/transcribe/base64", json={"base64": fake_b64, "language": "pt"})
            assert response.status_code == 200
            data = response.json()
            assert data["text"] == "Mensagem base64"


@pytest.mark.asyncio
async def test_transcribe_base64_endpoint_empty():
    """Valida erro 400 ao enviar base64 vazio."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/transcribe/base64", json={"base64": "", "language": "pt"})
        assert response.status_code == 400
        assert "Payload base64 vazio" in response.json()["detail"]
