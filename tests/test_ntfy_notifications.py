"""Testes automatizados para o NtfyNotificationService e roteamento de notificações push."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.notifications.service import NtfyNotificationService
from src.config import settings


@pytest.fixture
def ntfy_svc():
    svc = NtfyNotificationService()
    svc.url = "https://ntfy.sh"
    svc.topic = "test-bruno-dallas"
    svc.enabled = True
    return svc


@pytest.mark.asyncio
async def test_send_notification_payload_structure(ntfy_svc):
    """Verifica se o payload JSON enviado ao ntfy contém todos os metadados corretos."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200

        res = await ntfy_svc.send_notification(
            message="Mensagem de teste rica em Markdown com *negrito* e `código`",
            title="🎙️ Teste de Áudio",
            priority=4,
            tags=["microphone", "memo"],
            click_url="https://dashboard.local",
        )

        assert res is True
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        payload = call_kwargs.get("json")

        assert payload["topic"] == "test-bruno-dallas"
        assert payload["title"] == "🎙️ Teste de Áudio"
        assert payload["priority"] == 4
        assert payload["markdown"] is True
        assert "microphone" in payload["tags"]
        assert payload["click"] == "https://dashboard.local"


@pytest.mark.asyncio
async def test_notify_audio_processed_verbosity(ntfy_svc):
    """Verifica se a notificação de áudio inclui métricas de prosódia, transcrição bruta vs revisada e tarefas."""
    mock_task = MagicMock()
    mock_task.title = "Comprar café torrado na distribuidora"
    mock_task.priority = "HIGH"
    mock_task.due_date = "2026-09-22"
    mock_task.assignee = "Bruno"
    mock_task.in_vault = True

    with patch.object(ntfy_svc, "send_notification", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        res = await ntfy_svc.notify_audio_processed(
            speaker="Bruno",
            revised_text="Preciso comprar café torrado na distribuidora amanhã cedo.",
            raw_text="preciso compra cafe torrado na distribuidora amanha cedo",
            is_self_memo=True,
            contact_phone="554497604925",
            duration_s=12.4,
            prosody={"wpm": 145.0, "pauses_duration_s": 1.8},
            sentiment={"polarity": "POSITIVE", "sentiment_score": 0.85},
            intent="TASK",
            tasks=[mock_task],
            model_name="Whisper Base",
        )

        assert res is True
        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        msg = kwargs["message"]

        # Verificações de alta verbosidade
        assert "Bruno" in msg
        assert "12.4s" in msg
        assert "145 WPM" in msg
        assert "1.8s pausas" in msg
        assert "Preciso comprar café" in msg
        assert "<details><summary>🔍 Ver texto bruto STT (Whisper)</summary>" in msg
        assert "preciso compra cafe torrado" in msg
        assert "POSITIVE" in msg
        assert "+0.85" in msg
        assert "Comprar café torrado na distribuidora" in msg
        assert "[HIGH]" in msg
        assert "2026-09-22" in msg
        assert "[Vault]" in msg


@pytest.mark.asyncio
async def test_notify_pdf_processed_verbosity(ntfy_svc):
    """Verifica se a notificação de PDF detalha páginas, resumo executivo, motor e tarefas."""
    mock_task = MagicMock()
    mock_task.title = "Revisar contrato da Safra 2026"
    mock_task.priority = "URGENT"
    mock_task.due_date = "2026-10-01"

    with patch.object(ntfy_svc, "send_notification", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        res = await ntfy_svc.notify_pdf_processed(
            filename="contrato_safra.pdf",
            speaker="Jurídico Cooperativa",
            page_count=14,
            size_bytes=2 * 1024 * 1024,
            tier_used="tier1_gemini_3.5",
            model_name="gemini-3.1-flash-lite",
            summary="Contrato de fornecimento de grãos com cláusulas de entrega em outubro.",
            tasks=[mock_task],
        )

        assert res is True
        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        msg = kwargs["message"]

        assert "contrato_safra.pdf" in msg
        assert "14 págs" in msg
        assert "2.00 MB" in msg
        assert "tier1_gemini_3.5" in msg
        assert "Contrato de fornecimento de grãos" in msg
        assert "Revisar contrato da Safra 2026" in msg
        assert "[URGENT]" in msg


@pytest.mark.asyncio
async def test_notify_scheduled_reports(ntfy_svc):
    """Verifica envio de relatórios agendados (diário e semanal)."""
    with patch.object(ntfy_svc, "send_notification", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        # Diário
        await ntfy_svc.notify_scheduled_report(
            title="📋 Resumo Diário Executivo (2026-09-21)",
            report_text="*Tarefas Concluídas:* 5\n*Novas:* 2",
            report_type="daily",
        )
        assert mock_send.call_args.kwargs["priority"] == 4
        assert "calendar" in mock_send.call_args.kwargs["tags"]

        # Semanal
        await ntfy_svc.notify_scheduled_report(
            title="📊 Relatório Semanal",
            report_text="Visão consolidada da semana.",
            report_type="weekly",
        )
        assert "bar_chart" in mock_send.call_args.kwargs["tags"]


@pytest.mark.asyncio
async def test_notify_system_event_priorities(ntfy_svc):
    """Verifica se eventos críticos recebem prioridade máxima (5)."""
    with patch.object(ntfy_svc, "send_notification", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        await ntfy_svc.notify_system_event(
            title="🚨 Falha Crítica de Conexão",
            details="Socket desconectado por mais de 5 minutos.",
            level="CRITICAL",
        )
        assert mock_send.call_args.kwargs["priority"] == 5

        await ntfy_svc.notify_system_event(
            title="ℹ️ Watchdog Info",
            details="Verificação rotineira concluída.",
            level="INFO",
        )
        assert mock_send.call_args.kwargs["priority"] == 2


@pytest.mark.asyncio
async def test_ntfy_disabled_behavior():
    """Garante que quando desativado, nenhuma requisição de rede é disparada."""
    disabled_svc = NtfyNotificationService()
    disabled_svc.enabled = False

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        res = await disabled_svc.send_notification("teste")
        assert res is False
        mock_post.assert_not_called()
