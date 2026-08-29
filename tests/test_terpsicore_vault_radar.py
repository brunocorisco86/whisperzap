"""Testes unitários e de integração do Terpsícore aprimorado:

- Segregação estrita sem duplicidade entre Fluxo Normal e Vault (> 1 semana)
- Atributos Estratégicos: Ideia/Semente, Objetivo Épico e Favorito
- Funções de Toggle e Repositório
- Fusão Semântica no Baú por Embeddings
- Métricas do Jardim de Realizações e Radar de Procrastinação
"""

import uuid
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.memory.database import SessionLocal
from src.memory.models import MessageRecord, TaskRecord, TaskVaultAction
from src.memory.repository import memory_repository

client = TestClient(app)


def test_strict_segregation_normal_flow_vs_vault():
    """Garante que tarefas com prazo <= 7 dias ficam no fluxo ativo e tarefas > 7 dias / vault ficam no baú sem duplicidade."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        
        # 1. Tarefa Imediata (prazo curto: 2 dias)
        t_active = TaskRecord(
            id=str(uuid.uuid4()),
            title="Revisar ração do lote 12",
            due_date=(now + timedelta(days=2)).strftime("%Y-%m-%d"),
            status="PENDING",
            priority="HIGH",
            in_vault=False,
            is_idea=False,
            is_epic=False,
            is_favorite=False,
        )
        
        # 2. Tarefa Longo Prazo (> 7 dias: 20 dias)
        t_vault_long = TaskRecord(
            id=str(uuid.uuid4()),
            title="Implementar novo sensor IoT nos silos da cooperativa",
            due_date=(now + timedelta(days=20)).strftime("%Y-%m-%d"),
            status="PENDING",
            priority="MEDIUM",
            in_vault=False,
            is_idea=False,
            is_epic=True,
            is_favorite=False,
        )

        # 3. Tarefa com Flag Explícita de Vault
        t_vault_flag = TaskRecord(
            id=str(uuid.uuid4()),
            title="Contrato anual de fretes com a transportadora",
            due_date="próximo mês",
            status="PENDING",
            priority="LOW",
            in_vault=True,
            vault_reason="Aguardando diretoria",
            procrastination_factor="DEPENDENCY",
            is_idea=False,
            is_epic=False,
            is_favorite=False,
        )

        db.add_all([t_active, t_vault_long, t_vault_flag])
        db.commit()

        # Consulta Fluxo Ativo
        active_list = memory_repository.list_tasks(view_mode="active", db=db)
        active_ids = [t.id for t in active_list]

        assert t_active.id in active_ids, "Tarefa imediata deve estar no fluxo ativo"
        assert t_vault_long.id not in active_ids, "Tarefa > 7 dias NÃO pode aparecer no fluxo ativo (zero duplicidade)"
        assert t_vault_flag.id not in active_ids, "Tarefa in_vault=True NÃO pode aparecer no fluxo ativo (zero duplicidade)"

        # Consulta Vault
        vault_list = memory_repository.list_tasks(view_mode="vault", db=db)
        vault_ids = [t.id for t in vault_list]

        assert t_active.id not in vault_ids, "Tarefa ativa de curto prazo NÃO pode aparecer no Vault"
        assert t_vault_long.id in vault_ids, "Tarefa de 20 dias deve estar no Vault"
        assert t_vault_flag.id in vault_ids, "Tarefa arquivada deve estar no Vault"

    finally:
        db.close()


def test_task_strategic_attributes_toggle():
    """Testa marcação e alternância de Ideia, Épico e Favorito."""
    db = SessionLocal()
    try:
        t = TaskRecord(
            id=str(uuid.uuid4()),
            title="Pensar em arquitetura de sensores nos aviários",
            status="PENDING",
            priority="MEDIUM",
            is_idea=False,
            is_epic=False,
            is_favorite=False,
        )
        db.add(t)
        db.commit()

        # Toggle Idea
        res_idea = memory_repository.toggle_task_idea(t.id, db=db)
        assert res_idea.is_idea is True
        res_idea2 = memory_repository.toggle_task_idea(t.id, db=db)
        assert res_idea2.is_idea is False

        # Toggle Epic
        res_epic = memory_repository.toggle_task_epic(t.id, db=db)
        assert res_epic.is_epic is True

        # Toggle Favorite
        res_fav = memory_repository.toggle_task_favorite(t.id, db=db)
        assert res_fav.is_favorite is True

    finally:
        db.close()


def test_move_to_vault_and_restore():
    """Testa envio de tarefa para o Baú com delay, lembrete e reavaliação, e posterior resgate."""
    db = SessionLocal()
    try:
        t = TaskRecord(
            id=str(uuid.uuid4()),
            title="Reavaliar fornecedor de balanças",
            status="PENDING",
            priority="MEDIUM",
            in_vault=False,
        )
        db.add(t)
        db.commit()

        action = TaskVaultAction(
            postpone_days=14,
            reminder_datetime="2026-09-15 09:00",
            vault_reason="Aguardando cotação de outras empresas",
            procrastination_factor="DEPENDENCY",
            stakeholder_link="Carlos Compras",
            project_link="Modernização C.Vale",
            reassessment_notes="Verificar se vale a pena trocar de fornecedor agora",
            priority="LOW",
        )

        res_vault = memory_repository.move_task_to_vault(t.id, action, db=db)
        assert res_vault.in_vault is True
        assert res_vault.procrastination_factor == "DEPENDENCY"
        assert res_vault.stakeholder_link == "Carlos Compras"
        assert res_vault.priority == "LOW"

        # Resgate
        res_restored = memory_repository.restore_task_from_vault(t.id, db=db)
        assert res_restored.in_vault is False
        assert res_restored.postponed_until is None

    finally:
        db.close()


def test_procrastination_radar_and_garden_metrics():
    """Testa geração de métricas estruturadas para o Radar de Procrastinação e Jardim de Realizações."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        # Cria uma ideia concluída (conquista / fruto)
        t_done_idea = TaskRecord(
            id=str(uuid.uuid4()),
            title="Automatizar disparo de relatórios para granjas",
            created_at=now - timedelta(days=5),
            completed_at=now,
            status="DONE",
            is_idea=True,
            is_epic=True,
            project_link="Projeto Agrotech",
        )
        # Cria uma tarefa estagnada por clareza de escopo
        t_vault_scope = TaskRecord(
            id=str(uuid.uuid4()),
            title="Refatorar todo o sistema legado sem especificação",
            status="PENDING",
            in_vault=True,
            procrastination_factor="SCOPE_CLARITY",
            postponed_until=now + timedelta(days=10),
        )
        db.add_all([t_done_idea, t_vault_scope])
        db.commit()

        radar = memory_repository.get_procrastination_radar_metrics(db=db)
        assert isinstance(radar, dict)
        assert radar["total_vault_tasks"] >= 1
        assert "SCOPE_CLARITY" in radar["dimensions"]
        assert len(radar["insights"]) > 0

        garden = memory_repository.get_garden_metamorphosis_metrics(db=db)
        assert isinstance(garden, dict)
        assert garden["total_seeds"] >= 1
        assert garden["total_harvested"] >= 1
        assert len(garden["recent_harvests"]) >= 1

    finally:
        db.close()


def test_api_endpoints_tasks_vault_garden():
    """Testa chamadas HTTP aos novos endpoints REST."""
    db = SessionLocal()
    try:
        t_id = str(uuid.uuid4())
        task = TaskRecord(
            id=t_id,
            title="Desenvolver assistente de voz offline",
            status="PENDING",
            priority="HIGH",
        )
        db.add(task)
        db.commit()

        # 1. Toggle Favorite
        res_fav = client.post(f"/api/v1/memory/tasks/{t_id}/toggle-favorite")
        assert res_fav.status_code == 200
        assert res_fav.json()["is_favorite"] is True

        # 2. Toggle Epic
        res_epic = client.post(f"/api/v1/memory/tasks/{t_id}/toggle-epic")
        assert res_epic.status_code == 200
        assert res_epic.json()["is_epic"] is True

        # 3. Toggle Idea
        res_idea = client.post(f"/api/v1/memory/tasks/{t_id}/toggle-idea")
        assert res_idea.status_code == 200
        assert res_idea.json()["is_idea"] is True

        # 4. Move to Vault
        res_vault = client.post(
            f"/api/v1/memory/tasks/{t_id}/vault",
            json={
                "postpone_days": 10,
                "vault_reason": "Pesquisa de modelos leves",
                "procrastination_factor": "PERFECTIONISM",
            },
        )
        assert res_vault.status_code == 200
        assert res_vault.json()["in_vault"] is True

        # 5. List with view_mode=vault
        res_list_vault = client.get("/api/v1/memory/tasks?view_mode=vault")
        assert res_list_vault.status_code == 200
        vault_ids = [t["id"] for t in res_list_vault.json()]
        assert t_id in vault_ids

        # 6. List with view_mode=active (não deve conter a tarefa do vault)
        res_list_active = client.get("/api/v1/memory/tasks?view_mode=active")
        assert res_list_active.status_code == 200
        active_ids = [t["id"] for t in res_list_active.json()]
        assert t_id not in active_ids

        # 7. Radar Endpoint
        res_radar = client.get("/api/v1/memory/tasks/vault/radar")
        assert res_radar.status_code == 200
        assert "dimensions" in res_radar.json()

        # 8. Garden Metrics Endpoint
        res_garden = client.get("/api/v1/memory/tasks/garden/metrics")
        assert res_garden.status_code == 200
        assert "total_seeds" in res_garden.json()

        # 9. Restore / Unvault
        res_unvault = client.post(f"/api/v1/memory/tasks/{t_id}/unvault")
        assert res_unvault.status_code == 200
        assert res_unvault.json()["in_vault"] is False

    finally:
        db.close()


@pytest.mark.asyncio
async def test_serenity_closing_report_generation():
    """Testa geração da mensagem de fechamento sereno das 21:00 BRT."""
    from src.reports.daily import daily_report_service
    db = SessionLocal()
    try:
        msg_text = await daily_report_service.generate_serenity_closing(db=db)
        assert isinstance(msg_text, str)
        assert "FECHAMENTO SERENO" in msg_text
        assert "21:00" in msg_text
        assert "Baú de Espera (Vault)" in msg_text
    finally:
        db.close()


def test_vault_strict_one_week_rule_and_auto_return():
    """Testa a regra de que o Baú só pode ter tarefas > 1 semana e retorno automático quando faltam <= 7 dias."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        # 1. Tarefa com delay curto (ex: 3 dias) NÃO pode pertencer ao Baú (pertence ao fluxo normal)
        t_short_delay = TaskRecord(
            id=str(uuid.uuid4()),
            title="Ligar para o produtor e alinhar visita",
            status="PENDING",
            postponed_until=now + timedelta(days=3),
        )

        # 2. Tarefa com delay longo (> 7 dias: 14 dias) pertence ao Baú
        t_long_delay = TaskRecord(
            id=str(uuid.uuid4()),
            title="Revisar contrato da cooperativa com o fornecedor",
            status="PENDING",
            postponed_until=now + timedelta(days=14),
        )

        db.add_all([t_short_delay, t_long_delay])
        db.commit()

        # Validação direta da função de classificação
        assert memory_repository.is_task_in_vault(t_short_delay, now) is False, "Delay <= 7 dias NÃO pertence ao Baú"
        assert memory_repository.is_task_in_vault(t_long_delay, now) is True, "Delay > 7 dias pertence ao Baú"

        # Consulta com view_mode="active"
        active_list = memory_repository.list_tasks(view_mode="active", db=db)
        active_ids = [t.id for t in active_list]
        assert t_short_delay.id in active_ids, "Tarefa de 3 dias deve estar no fluxo normal"
        assert t_long_delay.id not in active_ids, "Tarefa de 14 dias NÃO pode estar no fluxo normal"

        # Consulta com view_mode="vault"
        vault_list = memory_repository.list_tasks(view_mode="vault", db=db)
        vault_ids = [t.id for t in vault_list]
        assert t_short_delay.id not in vault_ids, "Tarefa de 3 dias NÃO pode estar no Baú"
        assert t_long_delay.id in vault_ids, "Tarefa de 14 dias deve estar no Baú"

        # 3. Transição Temporal: Simula que passaram 10 dias (faltam apenas 4 dias para o prazo de 14 dias)
        simulated_future_now = now + timedelta(days=10)
        assert memory_repository.is_task_in_vault(t_long_delay, simulated_future_now) is False, \
            "Quando faltam <= 7 dias, a tarefa deve sair do Baú e retornar automaticamente ao fluxo ativo"

    finally:
        db.close()
