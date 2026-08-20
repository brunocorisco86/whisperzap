"""Módulo de Configuração com Pydantic Settings."""

from typing import Literal, Optional
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

    # AI Gateway (Otimizado para Menor Pegada de Tokens com Gemini 3.1 Flash-Lite)
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
    EVOLUTION_API_URL: str = "http://100.74.64.89:8080"
    EVOLUTION_API_KEY: str = "8c114ae397eb273edfe82e05728be8b4e17cc25649d7e26df40c438c67c368b0"
    EVOLUTION_INSTANCE: str = "hermes"
    EVOLUTION_PROXY_URL: Optional[str] = None

    # Usuário Proprietário / Identificação
    USER_PHONE_NUMBER: str = "554497604925"
    USER_NAME: str = "Bruno"
    USER_ALIASES: str = "Bruno,user,eu,me,admin,554497604925,5544979604925"

    # Regras de Bypass de IA & Grupos
    IGNORE_GROUP_MESSAGES: bool = True
    AI_BYPASS_CHAR_THRESHOLD: int = 15
    AI_BYPASS_WORD_THRESHOLD: int = 3
    AI_BYPASS_PHRASES: str = "bom dia,boa tarde,boa noite,oi,olá,ola,ok,beleza,valeu,obrigado,obrigada,meu nome,sim,não,nao,tchau,ate mais,até mais,opa"

    # Threshold de Peso / Influência para Análise de Sentimento (Default 0.70: Executivos, Família, Cooperados, Favoritos)
    SENTIMENT_WEIGHT_THRESHOLD: float = 0.70

    # Autenticação do Dashboard Web
    DASHBOARD_PASSWORD: str = "blurbang"
    DASHBOARD_AUTH_ENABLED: bool = True
    DASHBOARD_SESSION_SECRET: str = "whisperzap_secret_session_key_2026"


settings = Settings()
