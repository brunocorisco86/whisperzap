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
    AI_DEFAULT_MODEL: str = "gemini-3.1-flash-lite"
    GEMINI_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""

    # Model Router
    MODEL_REVISE: str = "gemini-3.1-flash-lite"
    MODEL_EXTRACT: str = "gemini-3.1-flash-lite"
    MODEL_SUMMARIZE: str = "gemini-3.1-flash-lite"
    MODEL_WEEKLY: str = "gemini-3.1-flash-lite"

    AI_LOG_PROMPTS: bool = False
    AI_LOG_RESPONSES: bool = False

    # Speech-to-Text (Whisper)
    WHISPER_MODEL: str = "base"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    WHISPER_MAX_CONCURRENCY: int = 2

    # Banco de dados e Persistência
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "hermes_voice_memory"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres_dev_password"
    DATABASE_URL: str = ""

    # Embeddings & Busca Vetorial
    EMBEDDING_PROVIDER: Literal["gemini", "openrouter", "mock"] = "gemini"
    EMBEDDING_MODEL: str = "text-embedding-004"

    # Grafo de Conhecimento e Dicionário Léxico
    DATA_DIR: str = "data"
    GRAPH_PERSISTENCE_PATH: str = "data/hermes_graph.json"
    DICTIONARY_PERSISTENCE_PATH: str = "data/lexical_dictionary.json"

    # WhatsApp / Evolution API & n8n
    N8N_WEBHOOK_URL: str = "http://localhost:5678/webhook/voice-received"
    WHATSAPP_API_TOKEN: str = ""
    EVOLUTION_API_URL: str = "http://100.106.3.81:8080"
    EVOLUTION_API_KEY: str = "8c114ae397eb273edfe82e05728be8b4e17cc25649d7e26df40c438c67c368b0"
    EVOLUTION_INSTANCE: str = "hermes"


settings = Settings()
