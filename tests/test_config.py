"""Testes unitários para configurações do sistema."""

from src.config import Settings


def test_settings_default_values():
    """Valida se os valores padrão do Settings estão bem configurados."""
    settings = Settings()
    assert settings.API_VERSION == "0.2.0"
    assert settings.WHISPER_MODEL == "small"
    assert settings.WHISPER_DEVICE == "cpu"
    assert settings.MODEL_REVISE == "gemini-3.1-flash-lite"
    assert settings.NTFY_TOPIC == "bruno-casa-dallas"
    assert settings.NTFY_FAMILY_TOPIC == "EEpT9fCTfBkjC4bg"
