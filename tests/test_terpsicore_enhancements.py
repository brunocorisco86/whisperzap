"""Testes das melhorias no módulo Terpsícore.

- Filtro por pessoa de onde saiu a tarefa (speaker/origem)
- Extração de tags de contexto via spaCy (sem tokens de API)
- Cálculo de similaridade e agrupamento por remetente
- Mesclagem de tarefas semelhantes com status PENDING e unificação de anotações
- Endpoint de mesclagem e elementos de UI no index.html
"""

import uuid
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.memory.database import SessionLocal
from src.memory.models import MessageRecord, TaskRecord
from src.memory.task_sentiment_analyzer import task_sentiment_analyzer
from src.memory.repository import memory_repository

client = TestClient(app)


def test_task_tags_extraction_with_spacy():
    """Testa extração de tags de domínio e contexto via spaCy (zero custo de API)."""
    tags_logistica = task_sentiment_analyzer.extract_task_tags(
        title="Agendar entrega de ração no silo da granja",
        source_text="O caminhão da C.Vale precisa descarregar o farelo de soja no silo amanhã cedo.",
        priority="URGENT",
    )
    assert isinstance(tags_logistica, list)
    assert "⚡ Urgente" in tags_logistica
    assert any(t in tags_logistica for t in ("Logística", "Ração", "Silos", "Granja", "C.Vale"))

    tags_financeiro = task_sentiment_analyzer.extract_task_tags(
        title="Pagar boleto do fornecedor de equipamentos",
        source_text="Enviar comprovante da nota fiscal para o financeiro.",
        priority="LOW",
    )
    assert "Financeiro" in tags_financeiro or "Compras" in tags_financeiro


def test_task_similarity_computation():
    """Testa cálculo de similaridade lexical e semântica entre tarefas."""
    sim_high = task_sentiment_analyzer.compute_task_similarity(
        title_a="Agendar entrega de ração no silo",
        notes_a="Confirmar com o motorista do caminhão",
        title_b="Agendar entrega de ração para o silo",
        notes_b="Verificar disponibilidade do motorista",
    )
    assert sim_high >= 0.50

    sim_low = task_sentiment_analyzer.compute_task_similarity(
        title_a="Agendar entrega de ração no silo",
        notes_a="Logística de frete",
        title_b="Revisar balanço financeiro anual e contratos",
        notes_b="Contabilidade e folha",
    )
    assert sim_low < 0.35


def test_list_tasks_filter_by_speaker_and_tags():
    """Testa se list_tasks filtra por remetente/speaker e retorna tags populadas."""
    db = SessionLocal()
    try:
        msg_id_1 = str(uuid.uuid4())
        msg_id_2 = str(uuid.uuid4())

        msg1 = MessageRecord(
            id=msg_id_1,
            created_at=datetime.now(timezone.utc),
            speaker="Marcos Cooperado",
            revised_text="Preciso agendar entrega de ração no silo 3 urgente.",
            intent="TASK",
            summary="Pedido de entrega de ração",
        )
        msg2 = MessageRecord(
            id=msg_id_2,
            created_at=datetime.now(timezone.utc),
            speaker="Carlos Gerente",
            revised_text="Revisar planilha financeira da granja.",
            intent="TASK",
            summary="Revisão de fluxo de caixa",
        )
        db.add_all([msg1, msg2])

        task1 = TaskRecord(
            id=str(uuid.uuid4()),
            message_id=msg_id_1,
            title="Agendar entrega de ração no silo 3",
            assignee="Bruno Conter",
            priority="URGENT",
            status="PENDING",
            notes="Prioridade máxima para o cooperado",
        )
        task2 = TaskRecord(
            id=str(uuid.uuid4()),
            message_id=msg_id_2,
            title="Revisar planilha financeira da granja",
            assignee="Bruno Conter",
            priority="MEDIUM",
            status="PENDING",
            notes="Conferir custos de insumos",
        )
        db.add_all([task1, task2])
        db.commit()

        # 1. Filtra por speaker Marcos
        res_marcos = memory_repository.list_tasks(speaker="Marcos Cooperado", db=db)
        assert any(t.id == task1.id for t in res_marcos)
        assert not any(t.id == task2.id for t in res_marcos)
        assert len(res_marcos[0].tags) > 0

        # 2. Filtra por speaker Carlos
        res_carlos = memory_repository.list_tasks(speaker="Carlos Gerente", db=db)
        assert any(t.id == task2.id for t in res_carlos)
        assert not any(t.id == task1.id for t in res_carlos)

        # 3. Via API Endpoint com query param speaker
        resp = client.get("/api/v1/memory/tasks?speaker=Marcos+Cooperado")
        assert resp.status_code == 200
        data = resp.json()
        assert any(t["id"] == task1.id for t in data)
        assert not any(t["id"] == task2.id for t in data)
        assert "tags" in data[0]
    finally:
        db.close()


def test_merge_similar_pending_tasks_grouped_by_speaker():
    """Testa agrupamento por pessoa e mesclagem de tarefas semelhantes e notas."""
    db = SessionLocal()
    try:
        msg_id = str(uuid.uuid4())
        msg = MessageRecord(
            id=msg_id,
            created_at=datetime.now(timezone.utc),
            speaker="Luciano Silos",
            revised_text="Verificar sensor de nível do silo 2 e calibrar sensor.",
            intent="TASK",
        )
        db.add(msg)

        task_id_1 = str(uuid.uuid4())
        task_id_2 = str(uuid.uuid4())

        t1 = TaskRecord(
            id=task_id_1,
            message_id=msg_id,
            created_at=datetime.now(timezone.utc),
            title="Calibrar sensor de nível do silo 2",
            assignee="Bruno Conter",
            priority="MEDIUM",
            status="PENDING",
            notes="Nota original da tarefa 1: bateria fraca.",
        )
        t2 = TaskRecord(
            id=task_id_2,
            message_id=msg_id,
            created_at=datetime.now(timezone.utc),
            title="Calibrar sensor de nível do silo 2 com urgência",
            assignee="Bruno Conter",
            priority="URGENT",
            status="PENDING",
            notes="Nota da tarefa 2: verificar também antena LoRa.",
        )
        db.add_all([t1, t2])
        db.commit()

        # Executa mesclagem
        merge_res = memory_repository.merge_similar_pending_tasks(similarity_threshold=0.50, db=db)
        assert merge_res["status"] == "success"
        assert merge_res["merged_groups_count"] >= 1
        assert merge_res["tasks_merged_count"] >= 1

        # Verifica tarefa primária
        db.refresh(t1)
        db.refresh(t2)

        # Uma deve estar PENDING com notas unificadas e a outra CANCELLED
        pending_task = t1 if t1.status == "PENDING" else t2
        cancelled_task = t2 if t1.status == "PENDING" else t1

        assert pending_task.status == "PENDING"
        assert cancelled_task.status == "CANCELLED"
        assert "Mesclado de" in pending_task.notes or "Nota original da tarefa" in pending_task.notes
        assert "antena LoRa" in pending_task.notes or "bateria fraca" in pending_task.notes
        assert pending_task.priority == "URGENT"  # Herdou a prioridade mais alta
    finally:
        db.close()


def test_merge_similar_tasks_api_endpoint():
    """Testa o endpoint POST /api/v1/memory/tasks/merge-similar."""
    res = client.post("/api/v1/memory/tasks/merge-similar")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "merged_groups_count" in data
    assert "tasks_merged_count" in data
    assert "message" in data


def test_terpsicore_ui_elements_in_index_html():
    """Verifica se index.html contém o seletor de pessoa de origem e botão de mesclar."""
    with open("src/web/templates/index.html", "r", encoding="utf-8") as f:
        html = f.read()

    assert 'id="tasks-filter-speaker"' in html
    assert 'id="btn-merge-tasks"' in html
    assert 'onclick="window.mergeSimilarTasks()"' in html
