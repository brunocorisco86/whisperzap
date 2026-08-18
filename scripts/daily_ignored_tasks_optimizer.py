#!/usr/bin/env python3
"""Script de Cronjob Diário: Otimizador Inteligente de Tarefas com spaCy e Agente LLM.

Executa diariamente (ex: às 03:00 da manhã) para processar todas as tarefas
com status CANCELLED no banco de dados PostgreSQL, extrair padrões de sentimento
e linguísticos com spaCy e sintetizar diretrizes negativas para o extrator.
"""

import asyncio
import logging
import os
import sys

# Adiciona a raiz do projeto ao PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.memory.database import SessionLocal
from src.ai_gateway.task_learner import task_learner_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("daily_task_optimizer")


async def main():
    logger.info("🚀 [Cronjob] Iniciando Otimização Diária de Tarefas Ignoradas (spaCy + LLM Critic)...")
    db = SessionLocal()
    try:
        result = await task_learner_engine.run_feedback_optimization(db=db)
        logger.info(f"✅ [Cronjob] Otimização concluída com sucesso!")
        logger.info(f"📊 Versão das Regras: {result.get('version')}")
        logger.info(f"📊 Tarefas Canceladas Analisadas: {result.get('total_cancelled_analyzed')}")
        logger.info("📋 Diretrizes Negativas Ativas:")
        for idx, rule in enumerate(result.get("negative_guidelines", []), start=1):
            logger.info(f"   {idx}. {rule}")
    except Exception as e:
        logger.error(f"❌ [Cronjob] Erro durante a otimização de tarefas: {e}", exc_info=True)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
