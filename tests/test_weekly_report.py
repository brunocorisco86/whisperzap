"""Testes para o serviço de Relatório Semanal e Plano de Domingo."""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from src.ai_gateway.schemas import DailyActionItem
from src.main import app
from src.memory.database import init_db
from src.reports.weekly import format_weekly_whatsapp_message, weekly_report_service


@pytest.fixture(autouse=True)
def setup_database():
    """Inicializa banco antes de cada teste."""
    init_db()


def test_format_weekly_whatsapp_message():
    """Testa a formatação de texto para o relatório semanal do WhatsApp."""
    plan = [
        DailyActionItem(
            title="Iniciar implantação na granja piloto",
            assignee="Equipe Operacional",
            priority="HIGH",
            due_date="Terça-feira 09:00",
            related_project="Telemetria",
        )
    ]
    metrics = {
        "total": 10,
        "completed": 8,
        "pending": 2,
    }
    msg = format_weekly_whatsapp_message(
        period_str="2026-08-07 a 2026-08-14",
        executive_summary="Semana excelente com alto índice de conclusão de tarefas.",
        active_projects=["Telemetria Silos", "Integração C.Vale"],
        top_contacts=["João Silva", "Diretoria Agro"],
        bottlenecks=["Fornecimento de cabos blindados"],
        tasks_metrics=metrics,
        plan=plan,
    )

    assert "RELATÓRIO SEMANAL & PLANO DE DOMINGO" in msg
    assert "2026-08-07 a 2026-08-14" in msg
    assert "Concluídas: 8/10 (80%)" in msg
    assert "Telemetria Silos" in msg
    assert "João Silva" in msg
    assert "PLANO ESTRATÉGICO PARA A PRÓXIMA SEMANA" in msg
    assert "Iniciar implantação na granja piloto" in msg


def test_weekly_report_api_endpoints():
    """Testa os endpoints POST /api/v1/memory/weekly/generate e GET /api/v1/memory/weekly."""
    client = TestClient(app)

    # 1. Salva mensagens e tarefas
    client.post(
        "/api/v1/memory/messages",
        json={"speaker": "Carlos", "revised_text": "Projeto Silos avançou conforme o esperado nesta semana."},
    )

    # 2. Chama geração POST
    post_res = client.post("/api/v1/memory/weekly/generate", json={})
    assert post_res.status_code == 200
    data = post_res.json()
    assert "period" in data
    assert "executive_summary" in data
    assert "tasks_metrics" in data
    assert "sunday_strategic_plan" in data
    assert "whatsapp_text" in data

    # 3. Chama consulta GET
    get_res = client.get("/api/v1/memory/weekly")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert "period" in get_data
