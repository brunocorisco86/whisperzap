"""Testes automatizados para o Dynamic Prompt Priming e Silero VAD no Whisper."""

import pytest
from src.transcriber.service import build_dynamic_initial_prompt, whisper_service
from src.contacts.models import ContactRecord
from src.memory.database import SessionLocal
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def test_build_dynamic_initial_prompt_with_dictionary_and_contacts():
    """Valida a construção do prompt inicial dinâmico contendo termos do dicionário e contatos favoritos."""
    db = SessionLocal()
    try:
        # Garante contato de teste cadastrado
        c = ContactRecord(
            id="c_test_priming_1",
            name="Valdecir Zootecnista",
            role="Zootecnista C.Vale",
            is_favorite=True,
        )
        db.merge(c)
        db.commit()

        prompt = build_dynamic_initial_prompt(
            speaker="Debora Patel",
            custom_prompt="Verificar sensor do silo 3",
            db=db,
        )

        # 1. Deve conter termos canônicos do dicionário
        assert "C.Vale" in prompt
        assert "Mtech" in prompt or "Silo" in prompt

        # 2. Deve conter o nome do interlocutor e contato relevante
        assert "Debora Patel" in prompt
        assert "Valdecir Zootecnista" in prompt
        assert "Verificar sensor do silo 3" in prompt

        # 3. Não deve ultrapassar 400 caracteres
        assert len(prompt) <= 400
    finally:
        db.close()


def test_whisper_service_initial_prompt_integration(monkeypatch):
    """Testa se o whisper_service repassa o initial_prompt para o backend de transcrição."""
    called_params = {}

    def mock_sync_transcribe(audio_path, language="pt", beam_size=5, initial_prompt=None):
        called_params["language"] = language
        called_params["beam_size"] = beam_size
        called_params["initial_prompt"] = initial_prompt
        return "Transcrição com priming simulada.", "pt", 0.99, 5.0, []

    monkeypatch.setattr(whisper_service, "_sync_transcribe", mock_sync_transcribe)

    # Executa transcrição assíncrona
    import asyncio
    text, lang, prob, dur, segs = asyncio.run(
        whisper_service.transcribe_audio(
            audio_path_or_file="fake_audio.ogg",
            speaker="Bruno Conter",
            custom_prompt="Ajuste do aviário",
        )
    )

    assert text == "Transcrição com priming simulada."
    assert called_params["initial_prompt"] is not None
    assert "C.Vale" in called_params["initial_prompt"]
    assert "Ajuste do aviário" in called_params["initial_prompt"]
