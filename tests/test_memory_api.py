"""Testes de integração para os endpoints da API (AI Extract, Dictionary e Memory)."""

import pytest
from fastapi.testclient import TestClient
from src.ai_gateway.extractor import semantic_extractor
from src.ai_gateway.providers.mock import MockProvider
from src.main import app
from src.memory.repository import memory_repository

from src.memory.database import init_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_mock_providers():
    """Garante que provedores mock e tabelas existam durante os testes de endpoints."""
    init_db()
    mock = MockProvider(model_name="mock-api-test")
    semantic_extractor.provider = mock
    memory_repository.embedding_provider = mock



def test_ai_extract_endpoint():
    """Testa POST /ai/extract."""
    response = client.post(
        "/ai/extract",
        json={
            "text": "Amanhã preciso falar com João sobre o sensor do silo 3.",
            "speaker": "Bruno",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "TASK"
    assert "tasks" in data
    assert "entities" in data
    assert data["provider"] == "mock"


def test_dictionary_endpoints():
    """Testa fluxo completo do dicionário: GET, POST, HINTS e DELETE."""
    # 1. GET lista de termos
    res_list = client.get("/api/v1/dictionary")
    assert res_list.status_code == 200
    assert len(res_list.json()) >= 1

    # 2. POST novo termo
    res_post = client.post(
        "/api/v1/dictionary",
        json={
            "term": "Bebedouro Nipple",
            "phonetic_variations": ["nipple", "nipel", "bebedouro nipel"],
            "expansion": "Bebedouro Automático Tipo Nipple",
            "category": "EQUIPAMENTOS",
        },
    )
    assert res_post.status_code == 201
    term_id = res_post.json()["id"]

    # 3. GET hints
    res_hints = client.get("/api/v1/dictionary/hints")
    assert res_hints.status_code == 200
    assert "whisper_initial_prompt" in res_hints.json()
    assert "prompt_context_hint" in res_hints.json()

    # 4. DELETE termo
    res_del = client.delete(f"/api/v1/dictionary/{term_id}")
    assert res_del.status_code == 204


def test_memory_messages_and_tasks_flow():
    """Testa criação de mensagem na memória, listagem de tarefas e atualização."""
    # 1. Salva mensagem
    res_msg = client.post(
        "/api/v1/memory/messages",
        json={
            "speaker": "Bruno",
            "revised_text": "Preciso falar com o João amanhã urgente sobre o silo 3.",
            "raw_text": "preciso fala com joao amanha urgente sobre o silo 3",
        },
    )
    assert res_msg.status_code == 201
    msg_id = res_msg.json()["message_id"]
    assert msg_id is not None

    # 2. Lista tarefas
    res_tasks = client.get("/api/v1/memory/tasks")
    assert res_tasks.status_code == 200
    tasks = res_tasks.json()
    assert len(tasks) >= 1

    # 3. Atualiza status da tarefa
    task_id = tasks[0]["id"]
    res_patch = client.patch(
        f"/api/v1/memory/tasks/{task_id}",
        json={"status": "DONE"},
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["status"] == "DONE"


def test_memory_search_and_graph_endpoints():
    """Testa busca semântica, consulta ao grafo e estatísticas."""
    # Busca semântica
    res_search = client.post(
        "/api/v1/memory/search",
        json={"query": "sensor do silo", "top_k": 3},
    )
    assert res_search.status_code == 200
    assert isinstance(res_search.json(), list)

    # Grafo de nós
    res_nodes = client.get("/api/v1/memory/graph/nodes")
    assert res_nodes.status_code == 200
    assert isinstance(res_nodes.json(), list)

    # Stats
    res_stats = client.get("/api/v1/memory/stats")
    assert res_stats.status_code == 200
    assert "total_messages" in res_stats.json()
    assert "graph_nodes" in res_stats.json()
