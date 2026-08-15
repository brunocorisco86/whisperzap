"""Gerenciamento de Conexão com o Banco de Dados (PostgreSQL / SQLite fallback)."""

import logging
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from src.config import settings
from src.memory.models import Base

logger = logging.getLogger(__name__)


def get_database_url() -> str:
    """Retorna a URL do banco de dados configurada ou constrói fallback."""
    if settings.DATABASE_URL:
        return settings.DATABASE_URL

    # Se estiver configurado Postgres e acessível, usa postgresql
    if settings.POSTGRES_HOST and settings.POSTGRES_HOST != "localhost" and settings.ENVIRONMENT == "production":
        return (
            f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@"
            f"{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
        )

    # Fallback local ultrarrápido para desenvolvimento/testes
    db_dir = settings.DATA_DIR or "data"
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "hermes_memory.db")
    return f"sqlite:///{db_path}"


DATABASE_URL = get_database_url()

# Cria o engine com configurações apropriadas
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Inicializa as tabelas do banco de dados se não existirem e adiciona novas colunas."""
    from sqlalchemy import text
    try:
        Base.metadata.create_all(bind=engine)
        with engine.connect() as conn:
            try:
                conn.execute(text("ALTER TABLE messages ADD COLUMN sentiment VARCHAR(32) DEFAULT 'NEUTRAL'"))
                conn.commit()
            except Exception:
                pass
            try:
                conn.execute(text("ALTER TABLE messages ADD COLUMN sentiment_score FLOAT DEFAULT 0.0"))
                conn.commit()
            except Exception:
                pass
            try:
                conn.execute(text("ALTER TABLE contacts ADD COLUMN avatar_url VARCHAR(500)"))
                conn.commit()
            except Exception:
                pass
        logger.info(f"Banco de dados inicializado com sucesso usando: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}")
    except Exception as e:
        logger.error(f"Erro ao inicializar banco de dados: {e}")


def get_db():
    """Dependency para injeção de sessão do banco no FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
