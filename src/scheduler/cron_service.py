"""Serviço de Agendamento Interno (Background Cron) para o Hermes Voice Memory.

Garante que rotinas essenciais (Resumo Diário das 18:00 e Agente Pescador Léxico das 19:00)
sejam executadas automaticamente dentro do container FastAPI, independente de crontab externo.
"""

import asyncio
import logging
from datetime import datetime, timezone
from src.dictionary.harvester import lexical_harvester
from src.memory.timezone_utils import get_now_brt

logger = logging.getLogger(__name__)

_scheduler_task: asyncio.Task | None = None
_last_executed_hour: dict[str, str] = {}


def try_acquire_cron_lock(task_key: str) -> bool:
    """Garante execução estritamente única e atômica da tarefa entre múltiplos workers do Uvicorn via PostgreSQL."""
    from src.memory.database import SessionLocal
    from src.memory.models import CronLockRecord
    from sqlalchemy.exc import IntegrityError
    import os

    try:
        with SessionLocal() as db:
            lock = CronLockRecord(task_key=task_key, worker_pid=os.getpid())
            db.add(lock)
            db.commit()
            logger.info(f"🔒 [Cron Lock] Bloqueio adquirido com sucesso para '{task_key}' (Worker PID: {os.getpid()}).")
            return True
    except IntegrityError:
        logger.info(f"⏭️ [Cron Lock] Tarefa '{task_key}' já adquirida/executada por outro worker. Ignorando execução duplicada.")
        return False
    except Exception as exc:
        logger.warning(f"⚠️ [Cron Lock] Falha ao verificar lock no banco para '{task_key}': {exc}. Usando fallback em memória.")
        if _last_executed_hour.get(task_key) != task_key:
            _last_executed_hour[task_key] = task_key
            return True
        return False


async def _background_scheduler_loop():
    """Loop assíncrono que verifica horários de agendamento com trava distribuída (18:00, 19:00, 21:00 BRT)."""
    logger.info("🕒 Hermes Background Scheduler iniciado com sucesso (Horário de Brasília / America/Sao_Paulo).")

    while True:
        try:
            now = get_now_brt()
            today_str = now.strftime("%Y-%m-%d")
            hour = now.hour
            minute = now.minute

            # 1. Rotina das 19:00 -> Agente Pescador Léxico (Harvester)
            if hour == 19 and minute < 5:
                key = f"harvest_{today_str}"
                if _last_executed_hour.get("harvest") != key and try_acquire_cron_lock(key):
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

            # 2. Rotina das 18:00 -> Consolidação de Sentimentos e Disparo do Resumo Diário via WhatsApp
            if hour == 18 and minute < 5:
                key = f"daily_report_{today_str}"
                if _last_executed_hour.get("daily_report") != key and try_acquire_cron_lock(key):
                    logger.info("📋 [Cron 18:00] Iniciando consolidação e disparo do Resumo Diário...")
                    _last_executed_hour["daily_report"] = key
                    try:
                        from src.memory.sentiment_timeline import sentiment_timeline_service
                        from src.reports.daily import daily_report_service
                        from src.whatsapp.service import whatsapp_service
                        from src.config import settings
                        from src.memory.database import SessionLocal

                        # Consolida sentimentos
                        sentiment_timeline_service.collect_daily_sentiments(target_date=today_str)

                        # Gera resumo executivo diário
                        with SessionLocal() as db:
                            rep = await daily_report_service.generate_daily_report(target_date=today_str, db=db)
                            if rep and rep.whatsapp_text and settings.USER_PHONE_NUMBER:
                                await whatsapp_service.send_text_message(
                                    number=settings.USER_PHONE_NUMBER,
                                    text=rep.whatsapp_text,
                                )
                                logger.info(f"✅ [Cron 18:00] Resumo Diário enviado para {settings.USER_PHONE_NUMBER}.")
                    except Exception as e:
                        logger.error(f"❌ [Cron 18:00] Erro ao consolidar/enviar Resumo Diário: {e}")

            # 3. Rotina das 21:00 -> Fechamento Sereno do Dia & Lembretes Ativos via WhatsApp (TRAVA ATÔMICA CONTRA DUPLICAÇÃO)
            if hour == 21 and minute < 5:
                key = f"serenity_closing_{today_str}"
                if _last_executed_hour.get("serenity_closing") != key and try_acquire_cron_lock(key):
                    logger.info("🌙 [Cron 21:00] Iniciando consolidação e disparo do Fechamento Sereno do Dia...")
                    _last_executed_hour["serenity_closing"] = key
                    try:
                        from src.reports.daily import daily_report_service
                        from src.whatsapp.service import whatsapp_service
                        from src.config import settings
                        from src.memory.database import SessionLocal

                        with SessionLocal() as db:
                            serenity_text = await daily_report_service.generate_serenity_closing(target_date=today_str, db=db)
                            if serenity_text and settings.USER_PHONE_NUMBER:
                                await whatsapp_service.send_text_message(
                                    number=settings.USER_PHONE_NUMBER,
                                    text=serenity_text,
                                )
                                logger.info(f"✅ [Cron 21:00] Fechamento Sereno enviado para {settings.USER_PHONE_NUMBER}.")
                    except Exception as e:
                        logger.error(f"❌ [Cron 21:00] Erro ao enviar Fechamento Sereno: {e}")

                # 3.1 Pruning Seguro do Histórico da Evolution API (D-2 até D0)
                key_prune = f"evolution_prune_{today_str}"
                if _last_executed_hour.get("evolution_prune") != key_prune and try_acquire_cron_lock(key_prune):
                    logger.info("🧹 [Cron 21:00] Iniciando poda autônoma do histórico da Evolution API (D-2 a D0)...")
                    _last_executed_hour["evolution_prune"] = key_prune
                    try:
                        from src.whatsapp.evolution_pruner import evolution_history_pruner
                        res_prune = evolution_history_pruner.prune_history(days_to_keep=2)
                        logger.info(f"✅ [Cron 21:00] Pruning Evolution concluído: {res_prune.get('status')} - {res_prune.get('deleted_count', 0)} msgs removidas.")
                    except Exception as e:
                        logger.error(f"❌ [Cron 21:00] Erro ao executar Pruning na Evolution API: {e}")

                # 3.2 Racionalização de Tarefas Terpsícore com spaCy & Polímnia
                key_rat = f"task_rationalize_{today_str}"
                if _last_executed_hour.get("task_rationalize") != key_rat and try_acquire_cron_lock(key_rat):
                    logger.info("🧠 [Cron 21:00] Iniciando racionalização semântica de tarefas PENDING (spaCy + Polímnia)...")
                    _last_executed_hour["task_rationalize"] = key_rat
                    try:
                        from src.memory.task_sentiment_analyzer import task_sentiment_analyzer
                        from src.memory.database import SessionLocal
                        with SessionLocal() as db:
                            res_rat = task_sentiment_analyzer.rationalize_pending_tasks(db, similarity_threshold=0.48)
                            logger.info(
                                f"✅ [Cron 21:00] Racionalização Terpsícore concluída: {res_rat.get('merged_count', 0)} duplicatas "
                                f"fundidas de {res_rat.get('total_scanned', 0)} analisadas. {res_rat.get('remaining_pending', 0)} ativas restantes."
                            )
                    except Exception as e:
                        logger.error(f"❌ [Cron 21:00] Erro na racionalização de tarefas Terpsícore: {e}")

            # 4. Rotina Semanal de Domingo às 20:00 -> Disparo do Relatório Semanal via WhatsApp
            if now.weekday() == 6 and hour == 20 and minute < 5:
                key = f"weekly_report_{today_str}"
                if _last_executed_hour.get("weekly_report") != key and try_acquire_cron_lock(key):
                    logger.info("📊 [Cron Domingo 20:00] Iniciando consolidação e disparo do Relatório Semanal...")
                    _last_executed_hour["weekly_report"] = key
                    try:
                        from src.reports.weekly import weekly_report_service
                        from src.whatsapp.service import whatsapp_service
                        from src.config import settings
                        from src.memory.database import SessionLocal

                        with SessionLocal() as db:
                            w_rep = await weekly_report_service.generate_weekly_report(target_date=today_str, db=db)
                            if w_rep and w_rep.whatsapp_text and settings.USER_PHONE_NUMBER:
                                await whatsapp_service.send_text_message(
                                    number=settings.USER_PHONE_NUMBER,
                                    text=w_rep.whatsapp_text,
                                )
                                logger.info(f"✅ [Cron Domingo 20:00] Relatório Semanal enviado para {settings.USER_PHONE_NUMBER}.")
                    except Exception as e:
                        logger.error(f"❌ [Cron Domingo 20:00] Erro ao gerar/enviar Relatório Semanal: {e}")

            # 5. Rotina Semanal de Domingo às 02:00 -> Varredura e Descoberta de Novos Modelos de IA (ModelRegistry)
            if now.weekday() == 6 and hour == 2 and minute < 5:
                key = f"model_discovery_{today_str}"
                if _last_executed_hour.get("model_discovery") != key and try_acquire_cron_lock(key):
                    logger.info("🤖 [Cron Domingo 02:00] Iniciando varredura semanal de novos modelos de IA custo-eficientes...")
                    _last_executed_hour["model_discovery"] = key
                    try:
                        from src.ai_gateway.model_registry import model_registry
                        res = await model_registry.discover_gemini_models(auto_adopt=True)
                        logger.info(
                            f"✅ [Cron Domingo 02:00] Descoberta de IA concluída: {res.get('discovered_count')} modelos mapeados. "
                            f"Modelos ativos: {res.get('active_models')}"
                        )
                    except Exception as e:
                        logger.error(f"❌ [Cron Domingo 02:00] Erro na descoberta semanal de modelos de IA: {e}")

            # 6. Rotina Semanal de Domingo às 23:00 -> Agente 'Zeladora' (Faxina no Grafo)
            if now.weekday() == 6 and hour == 23 and minute < 5:
                key = f"janitor_{today_str}"
                if _last_executed_hour.get("janitor") != key and try_acquire_cron_lock(key):
                    logger.info("🧹 [Cron Domingo 23:00] Agente 'Zeladora' iniciando faxina semanal no Grafo de Conhecimento...")
                    _last_executed_hour["janitor"] = key
                    try:
                        from src.memory.janitor import graph_janitor_service
                        report = graph_janitor_service.clean_graph()
                        logger.info(f"✅ [Cron Domingo 23:00] Zeladora finalizou a faxina: {report.summary}")
                    except Exception as e:
                        logger.error(f"❌ [Cron Domingo 23:00] Erro na faxina da Zeladora: {e}")

            # 7. Watchdog Autônomo de Saúde e Auto-Cura do Socket WhatsApp (Evolution API) a cada 5 minutos
            if minute % 5 == 0:
                key = f"wa_watchdog_{today_str}_{hour}_{minute}"
                if _last_executed_hour.get("wa_watchdog") != key:
                    _last_executed_hour["wa_watchdog"] = key
                    try:
                        from src.whatsapp.service import whatsapp_service
                        health = await whatsapp_service.check_socket_health()
                        if not health.get("healthy"):
                            logger.warning(f"⚠️ [Watchdog WhatsApp] Problema no socket detectado e remediado: {health}")
                    except Exception as e:
                        logger.debug(f"Aviso no watchdog do WhatsApp Evolution API: {e}")

            # 8. Watchdog Autônomo de Saúde e Circuit Breaker de Modelos de IA a cada 30 minutos
            if minute % 30 == 0:
                key = f"ai_watchdog_{today_str}_{hour}_{minute}"
                if _last_executed_hour.get("ai_watchdog") != key:
                    _last_executed_hour["ai_watchdog"] = key
                    try:
                        from src.ai_gateway.model_registry import model_registry
                        cb_status = model_registry.circuit_breaker.get_status()
                        needs_probe = any(s.get("state") in ("OPEN", "HALF_OPEN") for s in cb_status.values())

                        if needs_probe or not model_registry.data.last_discovery_at:
                            logger.info("🤖 [Watchdog IA] Executando verificação autônoma de saúde e modelos viáveis...")
                            probe_result = await model_registry.check_viable_models(probe_each=True)
                            if probe_result.get("auto_remediated"):
                                logger.warning(f"⚡ [Watchdog IA] Auto-remediação aplicada: {probe_result.get('remediation_details')}")
                    except Exception as e:
                        logger.debug(f"Aviso no Watchdog Autônomo de IA: {e}")

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
