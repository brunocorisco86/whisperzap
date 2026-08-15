"""Testes para o serviço de Resumo Diário e Plano para Amanhã."""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from src.ai_gateway.schemas import DailyActionItem
from src.main import app
from src.memory.database import init_db
from src.reports.daily import format_daily_whatsapp_message, daily_report_service


@pytest.fixture(autouse=True)
def setup_database():
    """Inicializa banco antes de cada teste."""
    init_db()


def test_format_daily_whatsapp_message():
    """Testa formatação de texto para WhatsApp."""
    plan = [
        DailyActionItem(
            title="Calibrar sensor do silo 3",
            assignee="João",
            priority="HIGH",
            due_date="Amanhã",
            related_project="Automação de Silos",
        )
    ]
    msg = format_daily_whatsapp_message(
        date_str="2026-08-14",
        executive_summary="Dia produtivo e alinhado.",
        key_events=["Reunião de alinhamento com a diretoria"],
        decisions=["Aprovada compra de novos módulos de telemetria"],
        issues=["Atraso no frete da transportadora"],
        completed_tasks=["Revisão dos logs do gateway"],
        pending_tasks=["Homologar firmware v2"],
        plan=plan,
    )

    assert "RESUMO DIÁRIO — 14/08/2026" in msg
    assert "Reunião de alinhamento" in msg
    assert "Aprovada compra" in msg
    assert "Atraso no frete" in msg
    assert "PLANO PARA AMANHÃ" in msg
    assert "Calibrar sensor do silo 3" in msg
    assert "(João)" in msg


def test_daily_report_api_endpoints():
    """Testa os endpoints POST /api/v1/memory/daily/generate e GET /api/v1/memory/daily."""
    client = TestClient(app)

    # 1. Cria mensagens
    client.post(
        "/api/v1/memory/messages",
        json={"speaker": "user", "revised_text": "Hoje finalizei a calibração de todos os sensores."},
    )

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 2. Chama geração POST
    post_res = client.post("/api/v1/memory/daily/generate", json={"date": today_str})
    assert post_res.status_code == 200
    data = post_res.json()
    assert data["date"] == today_str
    assert "executive_summary" in data
    assert "whatsapp_text" in data
    assert "plan_for_tomorrow" in data

    # 3. Chama consulta GET
    get_res = client.get(f"/api/v1/memory/daily?date={today_str}")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["date"] == today_str
