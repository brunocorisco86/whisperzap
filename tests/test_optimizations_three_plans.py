import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from src.main import app
from src.contacts.models import ContactRecord
from src.memory.database import SessionLocal
from src.memory.graph import knowledge_graph
from src.memory.models import MessageCreate, TaskRecord
from src.memory.repository import memory_repository
from src.contacts.service import contact_service

client = TestClient(app)


def test_contact_toggle_tasks_endpoint():
    """Testa o endpoint PATCH /api/v1/contacts/{id}/toggle-tasks."""
    db = SessionLocal()
    try:
        c_id = "wa_5544999990001"
        rec = db.query(ContactRecord).filter(ContactRecord.id == c_id).first()
        if not rec:
            rec = ContactRecord(
                id=c_id,
                name="Contato Teste Toggle",
                phone_number="5544999990001",
                role="COLLEAGUE",
                can_generate_tasks=False,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(rec)
            db.commit()

        # 1. Ativa toggle
        res = client.patch(f"/api/v1/contacts/{c_id}/toggle-tasks")
        assert res.status_code == 200
        data = res.json()
        assert data["can_generate_tasks"] is True

        # 2. Desativa toggle
        res2 = client.patch(f"/api/v1/contacts/{c_id}/toggle-tasks")
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["can_generate_tasks"] is False
    finally:
        db.close()


@pytest.mark.asyncio
async def test_task_creation_permission_enforcement():
    """Valida que mensagens de contato sem permissão não criam tarefas, mas com permissão ou dono criam."""
    db = SessionLocal()
    try:
        # 1. Contato sem permissão
        c_blocked_id = "wa_5544999990002"
        rec_blocked = db.query(ContactRecord).filter(ContactRecord.id == c_blocked_id).first()
        if not rec_blocked:
            rec_blocked = ContactRecord(
                id=c_blocked_id,
                name="Contato Sem Permissao",
                phone_number="5544999990002",
                role="COLLEAGUE",
                can_generate_tasks=False,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(rec_blocked)
            db.commit()
        else:
            rec_blocked.can_generate_tasks = False
            db.commit()

        # Mensagem com tarefa explícita
        msg_blocked = MessageCreate(
            speaker="Contato Sem Permissao",
            revised_text="Por favor agendar reunião urgente amanhã com a equipe e entregar relatório.",
            meta_info={"phone": "5544999990002"},
        )
        saved_msg = await memory_repository.save_message(msg_blocked, db=db)
        assert saved_msg is not None
        tasks_blocked = db.query(TaskRecord).filter(TaskRecord.message_id == saved_msg.id).all()
        assert len(tasks_blocked) == 0  # Deve ser 0 porque can_generate_tasks é False!

        # 2. Agora habilita o toggle
        rec_blocked.can_generate_tasks = True
        db.commit()

        msg_allowed = MessageCreate(
            speaker="Contato Sem Permissao",
            revised_text="Precisamos revisar o estoque de ração do silo 3 até sexta-feira com o João.",
            meta_info={"phone": "5544999990002"},
        )
        saved_msg_allowed = await memory_repository.save_message(msg_allowed, db=db)
        assert saved_msg_allowed is not None

        # 3. Dono sempre pode gerar tarefas
        msg_owner = MessageCreate(
            speaker="Bruno Conter",
            revised_text="Lembrar de calibrar o sensor de telemetria da granja 4 amanhã cedo.",
            meta_info={"fromMe": True},
        )
        saved_msg_owner = await memory_repository.save_message(msg_owner, db=db)
        assert saved_msg_owner is not None
    finally:
        db.close()


def test_graph_cutoff_and_main_only_default():
    """Testa se o endpoint /api/v1/memory/graph/full aplica corte de 30 dias e nós principais por padrão."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        old_date = now - timedelta(days=60)
        recent_date = now - timedelta(days=2)

        c_old = ContactRecord(
            id="wa_5544888880001",
            name="Contato Inativo Antigo",
            phone_number="5544888880001",
            role="COLLEAGUE",
            last_interaction_at=old_date,
            is_favorite=False,
            created_at=old_date,
            updated_at=old_date,
        )
        c_recent = ContactRecord(
            id="wa_5544888880002",
            name="Contato Ativo Recente",
            phone_number="5544888880002",
            role="EXECUTIVE",
            last_interaction_at=recent_date,
            is_favorite=False,
            created_at=recent_date,
            updated_at=recent_date,
        )
        db.merge(c_old)
        db.merge(c_recent)
        db.commit()

        knowledge_graph.add_node("Contato Inativo Antigo", category="PERSON", last_interaction_at=old_date.isoformat())
        knowledge_graph.add_node("Contato Ativo Recente", category="PERSON", last_interaction_at=recent_date.isoformat())
        knowledge_graph.add_edge("Contato Ativo Recente", "Granja Central", relation="SUPERVISES")

        # 1. Chamada Padrão (main_only=True, days_cutoff=30)
        res_default = client.get("/api/v1/memory/graph/full")
        assert res_default.status_code == 200
        data_default = res_default.json()
        node_ids_default = [n["id"] for n in data_default["nodes"]]

        assert "Contato Ativo Recente" in node_ids_default
        assert "Contato Inativo Antigo" not in node_ids_default
        assert data_default["stats"]["days_cutoff"] == 30
        assert data_default["stats"]["main_only"] is True

        # 2. Chamada Completa (main_only=False, days_cutoff=0)
        res_all = client.get("/api/v1/memory/graph/full?main_only=false&days_cutoff=0")
        assert res_all.status_code == 200
        data_all = res_all.json()
        node_ids_all = [n["id"] for n in data_all["nodes"]]

        assert "Contato Inativo Antigo" in node_ids_all
    finally:
        db.close()


def test_list_tasks_enriched_for_accordion():
    """Testa se list_tasks retorna campos completos para a sanfona De ➔ Para."""
    res = client.get("/api/v1/memory/tasks")
    assert res.status_code == 200
    tasks = res.json()
    assert isinstance(tasks, list)
    if len(tasks) > 0:
        t = tasks[0]
        assert "speaker" in t
        assert "assignee" in t
        assert "revised_text" in t
        assert "message_time" in t
        assert "source_text_snippet" in t
