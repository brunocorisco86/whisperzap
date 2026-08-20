"""Testes unitários e de integração para o Agente Hermes Q&A e RAG Híbrido."""

import pytest
from fastapi.testclient import TestClient
from src.ai_gateway.schemas import MemorySourceCitation
from src.ai_gateway.agent import hermes_agent_service
from src.main import app
from src.memory.database import SessionLocal, init_db
from src.memory.models import MessageCreate
from src.memory.repository import memory_repository


@pytest.fixture(autouse=True)
def setup_database():
    """Inicializa banco antes de cada teste."""
    init_db()


def test_hermes_agent_service_query_mock():
    """Testa a geração de resposta do Agente Hermes via MockProvider."""
    import asyncio

    sources = [
        MemorySourceCitation(
            message_id="msg_001",
            speaker="João Silva",
            text_snippet="Sensor do silo 3 foi calibrado hoje com sucesso.",
            similarity=0.92,
            created_at="2026-08-14 10:00",
        )
    ]
    related_entities = ["Sensor 3 -[BELONGS_TO]-> Silo 3"]
    pending_tasks = ["Revisar nível do silo amanhã"]

    response = asyncio.run(
        hermes_agent_service.answer_hermes_query(
            query="Qual o status do sensor 3?",
            sources=sources,
            related_entities=related_entities,
            pending_tasks=pending_tasks,
        )
    )

    assert response.query == "Qual o status do sensor 3?"
    assert len(response.sources) == 1
    assert response.sources[0].message_id == "msg_001"
    assert len(response.related_entities) == 1
    assert len(response.pending_tasks_mentioned) == 1
    assert response.answer is not None
    assert response.processing_time_ms >= 0


def test_hermes_query_api_endpoint():
    """Testa o endpoint POST /api/v1/memory/query integrado."""
    client = TestClient(app)

    # 1. Salva uma mensagem na memória
    msg_payload = {
        "speaker": "Carlos Gestor",
        "revised_text": "Precisamos entregar o relatório de ração da C.Vale até sexta-feira sem falta.",
    }
    client.post("/api/v1/memory/messages", json=msg_payload)

    # 2. Faz uma consulta ao Hermes
    query_payload = {
        "query": "Qual o prazo para o relatório de ração?",
        "top_k": 3,
        "include_graph": True,
    }
    response = client.post("/api/v1/memory/query", json=query_payload)
    assert response.status_code == 200

    data = response.json()
    assert "answer" in data
    assert "sources" in data
    assert isinstance(data["sources"], list)
    assert data["provider"] is not None


def test_hermes_query_speaker_and_task_matching():
    """Testa se a pergunta direcionada por nome recupera mensagens do remetente e tarefas geradas."""
    client = TestClient(app)

    from src.memory.database import SessionLocal
    from src.contacts.models import ContactRecord
    db_init = SessionLocal()
    try:
        if not db_init.query(ContactRecord).filter(ContactRecord.name == "Ailton").first():
            db_init.add(ContactRecord(
                id="c-ailton-test",
                name="Ailton",
                phone_number="5544999991122",
                role="COLLEAGUE",
            ))
            db_init.commit()
    finally:
        db_init.close()

    # 1. Salva mensagem do Ailton pedindo vaga de caseiro
    msg_payload = {
        "speaker": "Ailton",
        "revised_text": "Gostaria de saber se vc sabe se tem algum aviário precisando de caseiro?",
        "summary": "Ailton está buscando informações sobre vagas de emprego para caseiro em aviários.",
    }
    res_msg = client.post("/api/v1/memory/messages", json=msg_payload)
    assert res_msg.status_code in (200, 201)
    msg_id = res_msg.json()["message_id"]

    # 2. Cria tarefa pendente associada a essa mensagem
    from src.memory.database import SessionLocal
    from src.memory.models import TaskRecord
    db = SessionLocal()
    try:
        t = TaskRecord(
            id="t-ailton-1",
            message_id=msg_id,
            title="Verificar disponibilidade de vagas para caseiro em aviários",
            priority="LOW",
            status="PENDING",
        )
        db.add(t)
        db.commit()
    finally:
        db.close()

    # 3. Executa a pergunta "O que o Ailton queria hoje?"
    query_payload = {
        "query": "O que o Ailton queria hoje?",
        "top_k": 3,
        "include_graph": True,
    }
    response = client.post("/api/v1/memory/query", json=query_payload)
    assert response.status_code == 200

    data = response.json()
    assert any(s["speaker"] == "Ailton" for s in data["sources"])
    assert any("caseiro" in t.lower() or "ailton" in t.lower() for t in data["pending_tasks_mentioned"])
