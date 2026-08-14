"""Módulo de Configuração com Pydantic Settings."""

from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações da aplicação Hermes Voice Memory."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Configurações Gerais
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    API_TITLE: str = "Hermes Voice Memory API"
    API_VERSION: str = "0.2.0"

    # AI Gateway
    AI_PROVIDER: Literal["gemini", "openrouter", "mock"] = "gemini"
    AI_DEFAULT_MODEL: str = "gemini-2.5-flash-lite"
    GEMINI_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""

    # Model Router
    MODEL_REVISE: str = "gemini-2.5-flash-lite"
    MODEL_EXTRACT: str = "gemini-2.5-flash-lite"
    MODEL_SUMMARIZE: str = "gemini-2.5-flash"
    MODEL_WEEKLY: str = "gemini-2.5-pro"

    AI_LOG_PROMPTS: bool = False
    AI_LOG_RESPONSES: bool = False

    # Speech-to-Text (Whisper)
    WHISPER_MODEL: str = "base"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"

    # Banco de dados
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "hermes_voice_memory"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres_dev_password"

    # WhatsApp / n8n
    N8N_WEBHOOK_URL: str = "http://localhost:5678/webhook/voice-received"
    WHATSAPP_API_TOKEN: str = ""


settings = Settings()
