"""Testes automatizados para validação do Fuso Horário no Scheduler e Relatórios."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch
import pytest

from src.memory.timezone_utils import BRASILIA_TZ, get_now_brt
from src.scheduler.cron_service import _background_scheduler_loop, _last_executed_hour


@pytest.mark.asyncio
async def test_scheduler_respects_brasilia_timezone():
    """Valida que o loop do scheduler usa o Horário de Brasília (BRT) e não o horário naive/UTC do SO."""
    _last_executed_hour.clear()

    # Simula momento em que no Brasil são 18:02 (horário de disparo do Resumo Diário)
    mock_now_brt = datetime(2026, 8, 27, 18, 2, 0, tzinfo=BRASILIA_TZ)

    with patch("src.scheduler.cron_service.get_now_brt", return_value=mock_now_brt):
        with patch("src.reports.daily.daily_report_service.generate_daily_report", new_callable=AsyncMock) as mock_daily:
            with patch("src.whatsapp.service.whatsapp_service.send_text_message", new_callable=AsyncMock) as mock_send:
                with patch("src.memory.sentiment_timeline.sentiment_timeline_service.collect_daily_sentiments") as mock_sent:
                    with patch("asyncio.sleep", side_effect=asyncio.CancelledError):
                        try:
                            await _background_scheduler_loop()
                        except asyncio.CancelledError:
                            pass

                    # Verifica se a chave de hoje foi registrada e os serviços acionados
                    assert "daily_report" in _last_executed_hour
                    assert _last_executed_hour["daily_report"] == "daily_report_2026-08-27"
                    mock_sent.assert_called_once_with(target_date="2026-08-27")


@pytest.mark.asyncio
async def test_scheduler_does_not_fire_at_15h_brt():
    """Valida que às 15:00 BRT (que era 18:00 UTC) o scheduler NÃO dispara o resumo diário."""
    _last_executed_hour.clear()

    # 15:00 BRT
    mock_now_brt = datetime(2026, 8, 27, 15, 0, 0, tzinfo=BRASILIA_TZ)

    with patch("src.scheduler.cron_service.get_now_brt", return_value=mock_now_brt):
        with patch("src.reports.daily.daily_report_service.generate_daily_report", new_callable=AsyncMock) as mock_daily:
            with patch("asyncio.sleep", side_effect=asyncio.CancelledError):
                try:
                    await _background_scheduler_loop()
                except asyncio.CancelledError:
                    pass

            assert "daily_report" not in _last_executed_hour
            mock_daily.assert_not_called()
