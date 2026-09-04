"""Módulo de Pruning Seguro e Retenção do Histórico da Evolution API.

Mantém rigorosamente uma janela de 3 dias de conversas no WhatsApp (D-2 até D0)
no banco 'evolution_db', reduzindo overhead de contexto e otimizando I/O.
Isolamento absoluto: NUNCA acessa ou altera o banco 'hermes_voice_memory'.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Tuple
from sqlalchemy import create_engine, text
from src.config import settings
from src.memory.timezone_utils import get_now_brt, TIMEZONE_BRT

logger = logging.getLogger(__name__)


class EvolutionHistoryPruner:
    """Gerencia a retenção de dados e expurgo de mensagens antigas da Evolution API."""

    def get_evolution_db_url(self) -> str:
        """Obtém a URL de conexão com o banco evolution_db."""
        base_url = settings.DATABASE_URL or ""
        if base_url and "/" in base_url:
            prefix = base_url.rsplit("/", 1)[0]
            return f"{prefix}/evolution_db"

        user = settings.POSTGRES_USER or "postgres"
        pwd = settings.POSTGRES_PASSWORD or ""
        host = settings.POSTGRES_HOST or "localhost"
        port = settings.POSTGRES_PORT or 5432
        return f"postgresql://{user}:{pwd}@{host}:{port}/evolution_db"

    def calculate_cutoff(self, days_to_keep: int = 2) -> Tuple[datetime, int]:
        """Calcula a data e o timestamp epoch de corte em BRT.
        
        Para days_to_keep=2 (D-2):
        Se hoje for 04/09, o corte é 02/09 00:00:00 BRT.
        Tudo >= 02/09 00:00:00 BRT é preservado (D-2, D-1, D0).
        Tudo < 02/09 00:00:00 BRT é podado.
        """
        now_brt = get_now_brt()
        cutoff_dt = (now_brt - timedelta(days=days_to_keep)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        cutoff_epoch = int(cutoff_dt.timestamp())
        return cutoff_dt, cutoff_epoch

    def ensure_index(self, engine) -> None:
        """Garante que a tabela Message tenha índice em messageTimestamp para evitar sequential scan."""
        try:
            with engine.connect() as conn:
                conn.execute(text(
                    'CREATE INDEX IF NOT EXISTS "Message_messageTimestamp_idx" '
                    'ON evolution_api."Message" ("messageTimestamp");'
                ))
                conn.commit()
                logger.info("⚡ [Evolution Pruner] Índice 'Message_messageTimestamp_idx' verificado/criado com sucesso.")
        except Exception as exc:
            logger.warning(f"⚠️ [Evolution Pruner] Aviso ao criar índice em evolution_api.Message: {exc}")

    def prune_history(self, days_to_keep: int = 2) -> Dict[str, Any]:
        """Executa a poda de mensagens anteriores a D-2 no banco evolution_db.
        
        Remove mensagens em evolution_api."Message" onde messageTimestamp < cutoff_epoch.
        As tabelas 'Media' e 'MessageUpdate' são limpas em cascata (ON DELETE CASCADE).
        Executa VACUUM ANALYZE para recompactar páginas e atualizar o planejador.
        """
        cutoff_dt, cutoff_epoch = self.calculate_cutoff(days_to_keep=days_to_keep)
        cutoff_str = cutoff_dt.strftime("%d/%m/%Y %H:%M:%S (%Z)")
        db_url = self.get_evolution_db_url()

        logger.info(f"🧹 [Evolution Pruner] Iniciando poda de mensagens anteriores a {cutoff_str} (Epoch: {cutoff_epoch})...")

        engine = create_engine(db_url, isolation_level="AUTOCOMMIT")

        try:
            self.ensure_index(engine)

            with engine.connect() as conn:
                total_before = conn.execute(
                    text('SELECT count(*) FROM evolution_api."Message"')
                ).scalar() or 0

                to_delete = conn.execute(
                    text('SELECT count(*) FROM evolution_api."Message" WHERE "messageTimestamp" < :cutoff'),
                    {"cutoff": cutoff_epoch}
                ).scalar() or 0

                if to_delete == 0:
                    logger.info(f"✨ [Evolution Pruner] Nenhuma mensagem anterior a {cutoff_str} encontrada para poda.")
                    return {
                        "status": "NO_OP",
                        "deleted_count": 0,
                        "remaining_count": total_before,
                        "cutoff_date": cutoff_str,
                        "cutoff_epoch": cutoff_epoch,
                    }

                del_result = conn.execute(
                    text('DELETE FROM evolution_api."Message" WHERE "messageTimestamp" < :cutoff'),
                    {"cutoff": cutoff_epoch}
                )
                deleted_count = del_result.rowcount

                total_after = conn.execute(
                    text('SELECT count(*) FROM evolution_api."Message"')
                ).scalar() or 0

                try:
                    conn.execute(text('VACUUM ANALYZE evolution_api."Message";'))
                    logger.info("🧹 [Evolution Pruner] VACUUM ANALYZE executado com sucesso em evolution_api.Message.")
                except Exception as vac_err:
                    logger.debug(f"Aviso no VACUUM da Evolution: {vac_err}")

                logger.info(
                    f"✅ [Evolution Pruner] Poda concluída com sucesso: {deleted_count} mensagens removidas. "
                    f"Restantes na janela D-2..D0: {total_after} mensagens."
                )

                return {
                    "status": "SUCCESS",
                    "deleted_count": deleted_count,
                    "remaining_count": total_after,
                    "cutoff_date": cutoff_str,
                    "cutoff_epoch": cutoff_epoch,
                }

        except Exception as exc:
            logger.error(f"❌ [Evolution Pruner] Falha ao executar poda na Evolution API: {exc}")
            return {
                "status": "ERROR",
                "error": str(exc),
                "cutoff_date": cutoff_str,
                "cutoff_epoch": cutoff_epoch,
            }
        finally:
            engine.dispose()


evolution_history_pruner = EvolutionHistoryPruner()
