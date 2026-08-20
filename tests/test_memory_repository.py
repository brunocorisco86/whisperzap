"""Testes unitários para o Repositório de Memória Hermes."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.ai_gateway.extractor import semantic_extractor
from src.ai_gateway.providers.mock import MockProvider
from src.memory.models import Base, MessageCreate, TaskUpdate
from src.contacts.models import ContactRecord
from src.memory.repository import MemoryRepository, cosine_similarity


@pytest.fixture
def memory_db():
    """Cria um banco SQLite em memória isolado para testes de repositório."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    # Configura MockProvider no extrator e embedding
    semantic_extractor.provider = MockProvider(model_name="mock-extractor")

    yield session
    session.close()


def test_cosine_similarity():
    """Testa cálculo de similaridade de cosseno."""
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    assert cosine_similarity(v1, v2) == pytest.approx(1.0)

    v3 = [0.0, 1.0, 0.0]
    assert cosine_similarity(v1, v3) == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_save_message_and_retrieve_tasks(memory_db):
    """Testa o salvamento completo de mensagem com extração semântica e tarefas."""
    repo = MemoryRepository()
    repo.embedding_provider = MockProvider(model_name="mock-embedding")

    msg_data = MessageCreate(
        speaker="Bruno",
        raw_text="preciso falar com joao amanha sobre o sensor de racao do silo 3",
        revised_text="Preciso falar com o João amanhã sobre o sensor de ração do Silo 3.",
    )

    msg = await repo.save_message(msg_data, db=memory_db)
    assert msg.id is not None
    assert msg.intent == "TASK"

    # Verifica se as tarefas foram criadas
    tasks = repo.list_tasks(db=memory_db)
    assert len(tasks) >= 1
    assert tasks[0].status == "PENDING"

    # Atualiza tarefa para DONE
    task_id = tasks[0].id
    updated = repo.update_task(task_id, TaskUpdate(status="DONE"), db=memory_db)
    assert updated is not None
    assert updated.status == "DONE"
    assert updated.completed_at is not None


@pytest.mark.asyncio
async def test_semantic_search_memories(memory_db):
    """Testa busca vetorial por similaridade."""
    repo = MemoryRepository()
    repo.embedding_provider = MockProvider(model_name="mock-embedding")

    # Salva duas mensagens
    await repo.save_message(
        MessageCreate(
            speaker="Bruno",
            revised_text="Instalação dos sensores de temperatura no aviário 1.",
        ),
        db=memory_db,
    )
    await repo.save_message(
        MessageCreate(
            speaker="Bruno",
            revised_text="Reunião com a equipe financeira da cooperativa C.Vale.",
        ),
        db=memory_db,
    )

    # Busca por termo
    results = await repo.search_memories(query="sensores de temperatura", top_k=5, db=memory_db)
    assert len(results) >= 1
    assert results[0].text is not None


def test_get_stats(memory_db):
    """Testa coleta de estatísticas da memória."""
    repo = MemoryRepository()
    stats = repo.get_stats(db=memory_db)
    assert stats.total_messages >= 0
    assert stats.total_tasks >= 0
