"""Serviço de Agendamento Interno (Background Cron) para o Hermes Voice Memory.

Garante que rotinas essenciais (Resumo Diário das 18:00 e Agente Pescador Léxico das 19:00)
sejam executadas automaticamente dentro do container FastAPI, independente de crontab externo.
"""

import asyncio
import logging
from datetime import datetime, timezone
from src.dictionary.harvester import lexical_harvester

logger = logging.getLogger(__name__)

_scheduler_task: asyncio.Task | None = None
_last_executed_hour: dict[str, str] = {}


async def _background_scheduler_loop():
    """Loop assíncrono que verifica horários de agendamento (18:00 e 19:00)."""
    logger.info("🕒 Hermes Background Scheduler iniciado com sucesso na VPS.")

    while True:
        try:
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            hour = now.hour
            minute = now.minute

            # 1. Rotina das 19:00 -> Agente Pescador Léxico (Harvester)
            if hour == 19 and minute < 5:
                key = f"harvest_{today_str}"
                if _last_executed_hour.get("harvest") != key:
                    logger.info("🎣 [Cron 19:00] Iniciando execução automática do Agente Pescador Léxico...")
                    _last_executed_hour["harvest"] = key
                    try:
                        result = await lexical_harvester.harvest_pending_candidates()
                        logger.info(
                            f"✅ [Cron 19:00] Harvester concluído: {result.promoted_terms_count} promovidos, "
                            f"{result.rejected_terms_count} rejeitados de {result.total_candidates_analyzed} analisados."
                        )
                    except Exception as e:
                        logger.error(f"❌ [Cron 19:00] Erro ao executar Lexical Harvester: {e}")

            # 2. Rotina das 18:00 -> Consolidação de Sentimentos Diários
            if hour == 18 and minute < 5:
                key = f"sentiment_{today_str}"
                if _last_executed_hour.get("sentiment") != key:
                    logger.info("🌡️ [Cron 18:00] Iniciando consolidação diária de sentimentos...")
                    _last_executed_hour["sentiment"] = key
                    try:
                        from src.memory.sentiment_timeline import sentiment_timeline_service
                        snapshots = sentiment_timeline_service.collect_daily_snapshots(date_str=today_str)
                        logger.info(f"✅ [Cron 18:00] Snapshots de sentimentos consolidados para {len(snapshots)} pessoas.")
                    except Exception as e:
                        logger.error(f"❌ [Cron 18:00] Erro ao consolidar sentimentos: {e}")

        except Exception as exc:
            logger.error(f"Aviso no loop do Background Scheduler: {exc}")

        # Aguarda 30 segundos antes da próxima checagem
        await asyncio.sleep(30)


def start_scheduler():
    """Inicia a task do scheduler em background."""
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(_background_scheduler_loop())


def stop_scheduler():
    """Para a task do scheduler."""
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        _scheduler_task = None
