"""Testes automatizados para Cron Locks distribuídos e Watchdog do WhatsApp."""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from src.main import app
from src.scheduler.cron_service import try_acquire_cron_lock
from src.whatsapp.service import whatsapp_service

client = TestClient(app)


def test_try_acquire_cron_lock_concurrency():
    """Valida que try_acquire_cron_lock impede execuções duplicadas da mesma rotina agendada."""
    test_key_1 = "test_routine_2026-09-04_18"
    test_key_2 = "test_routine_2026-09-04_21"

    # 1ª tentativa para chave 1 -> Deve obter o lock com sucesso
    acquired_1 = try_acquire_cron_lock(test_key_1)
    assert acquired_1 is True

    # 2ª tentativa imediata para a mesma chave 1 (simulando 2º worker do Uvicorn) -> Deve ser bloqueada
    acquired_duplicate = try_acquire_cron_lock(test_key_1)
    assert acquired_duplicate is False

    # Tentativa para uma chave diferente (outra rotina ou outro horário) -> Deve obter com sucesso
    acquired_2 = try_acquire_cron_lock(test_key_2)
    assert acquired_2 is True


@pytest.mark.asyncio
async def test_whatsapp_service_restart_instance():
    """Valida o método restart_instance acionando o endpoint correspondente na Evolution API."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200

        success = await whatsapp_service.restart_instance()
        assert success is True
        mock_post.assert_called_once()
        assert "instance/restart" in mock_post.call_args[0][0]


@pytest.mark.asyncio
async def test_whatsapp_service_check_socket_health_open():
    """Valida checagem de saúde quando o socket está conectado e saudável ('open')."""
    import httpx
    mock_resp = httpx.Response(200, json={"instance": {"state": "open"}})
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        health = await whatsapp_service.check_socket_health()
        assert health["healthy"] is True
        assert health["state"] == "open"


@pytest.mark.asyncio
async def test_whatsapp_service_check_socket_health_auto_heal_when_down():
    """Valida auto-cura quando o socket do WhatsApp cai ('connecting' ou 'close')."""
    import httpx
    mock_resp = httpx.Response(200, json={"instance": {"state": "close"}})
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        with patch.object(whatsapp_service, "restart_instance", new_callable=AsyncMock) as mock_restart:
            mock_restart.return_value = True

            health = await whatsapp_service.check_socket_health()
            assert health["healthy"] is False
            assert health["state"] == "close"
            assert health["auto_healed"] is True
            mock_restart.assert_called_once()


def test_api_restart_whatsapp_instance():
    """Testa o endpoint POST /api/v1/whatsapp/restart-instance."""
    with patch("src.whatsapp.service.whatsapp_service.restart_instance", new_callable=AsyncMock) as mock_restart:
        mock_restart.return_value = True

        response = client.post("/api/v1/whatsapp/restart-instance")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["restarted"] is True
