"""Testes unitários para configurações do sistema."""

from src.config import Settings


def test_settings_default_values():
    """Valida se os valores padrão do Settings estão bem configurados."""
    settings = Settings()
    assert settings.API_VERSION == "0.2.0"
    assert settings.WHISPER_MODEL == "base"
    assert settings.WHISPER_DEVICE == "cpu"
    assert settings.AI_PROVIDER in ["gemini", "openrouter", "mock"]
    assert settings.MODEL_REVISE == "gemini-2.5-flash-lite"
