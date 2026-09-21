"""Serviço de Auditoria e Observabilidade Estruturada para o Hermes Voice Memory."""

import json
import logging
from logging.handlers import RotatingFileHandler
import os
import uuid
from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional
from sqlalchemy import case, func
from src.config import settings
from src.memory.database import SessionLocal
from src.memory.models import AuditLogRecord

_STATS_CACHE: Dict[str, Any] = {}
_STATS_CACHE_TS: float = 0.0
_STATS_CACHE_TTL: float = 15.0


def invalidate_audit_stats_cache() -> None:
    """Invalida o cache em memória das estatísticas de auditoria."""
    global _STATS_CACHE_TS
    _STATS_CACHE_TS = 0.0

# Configuração do Logger em Arquivo JSONL Rotativo
LOGS_DIR = os.path.join(settings.DATA_DIR or "data", "logs")
os.makedirs(LOGS_DIR, exist_ok=True)
JSONL_LOG_PATH = os.path.join(LOGS_DIR, "hermes_audit.jsonl")

audit_file_logger = logging.getLogger("hermes_audit_file")
audit_file_logger.setLevel(logging.INFO)
audit_file_logger.propagate = False

if not audit_file_logger.handlers:
    file_handler = RotatingFileHandler(
        JSONL_LOG_PATH,
        maxBytes=10 * 1024 * 1024,  # 10 MB por arquivo
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    audit_file_logger.addHandler(file_handler)

logger = logging.getLogger(__name__)


def log_event(
    module: str,
    action: str,
    speaker: Optional[str] = None,
    status: str = "SUCCESS",
    duration_ms: float = 0.0,
    details: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
) -> Optional[AuditLogRecord]:
    """Registra um evento de auditoria no banco de dados e no arquivo de log JSONL."""
    event_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    details_dict = details or {}

    # 1. Log Estruturado em Arquivo JSONL
    log_entry = {
        "id": event_id,
        "timestamp": now.isoformat(),
        "module": module,
        "action": action,
        "speaker": speaker,
        "status": status,
        "duration_ms": round(duration_ms, 2),
        "details": details_dict,
        "error_message": error_message,
    }
    try:
        audit_file_logger.info(json.dumps(log_entry, ensure_ascii=False))
    except Exception as err:
        logger.warning(f"Falha ao escrever log JSONL: {err}")

    # 2. Persistência no Banco de Dados
    try:
        session = SessionLocal()
        try:
            record = AuditLogRecord(
                id=event_id,
                created_at=now,
                module=module,
                action=action,
                speaker=speaker,
                status=status,
                duration_ms=round(duration_ms, 2),
                details=details_dict,
                error_message=error_message,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            invalidate_audit_stats_cache()
            return record
        finally:
            session.close()
    except Exception as db_err:
        logger.error(f"Erro ao persistir log de auditoria no DB: {db_err}")
        return None


def get_audit_logs(
    limit: int = 50,
    offset: int = 0,
    module: Optional[str] = None,
    status: Optional[str] = None,
    speaker: Optional[str] = None,
    search: Optional[str] = None,
) -> List[AuditLogRecord]:
    """Retorna logs de auditoria com paginação e filtros opcionais."""
    session = SessionLocal()
    try:
        query = session.query(AuditLogRecord)

        if module:
            query = query.filter(AuditLogRecord.module == module.upper())
        if status:
            query = query.filter(AuditLogRecord.status == status.upper())
        if speaker:
            query = query.filter(AuditLogRecord.speaker.ilike(f"%{speaker}%"))
        if search:
            query = query.filter(
                (AuditLogRecord.action.ilike(f"%{search}%"))
                | (AuditLogRecord.error_message.ilike(f"%{search}%"))
            )

        return query.order_by(AuditLogRecord.created_at.desc()).offset(offset).limit(limit).all()
    finally:
        session.close()


def get_audit_stats(force_refresh: bool = False) -> Dict[str, Any]:
    """Calcula estatísticas e métricas operacionais agregadas com alta performance e cache TTL de 15s."""
    global _STATS_CACHE, _STATS_CACHE_TS
    now_ts = time.time()
    if not force_refresh and _STATS_CACHE and (now_ts - _STATS_CACHE_TS) < _STATS_CACHE_TTL:
        return _STATS_CACHE

    session = SessionLocal()
    try:
        # 1. Agregação unificada em 1 única query SQL de alta velocidade com CASE WHEN
        aggregates = (
            session.query(
                func.count(AuditLogRecord.id).label("total"),
                func.count(case((AuditLogRecord.status == "ERROR", AuditLogRecord.id))).label("errors"),
                func.count(case((AuditLogRecord.status == "SUCCESS", AuditLogRecord.id))).label("successes"),
                func.avg(AuditLogRecord.duration_ms).label("avg_latency"),
            )
            .first()
        )
        total_logs = (aggregates.total if aggregates else 0) or 0
        error_logs = (aggregates.errors if aggregates else 0) or 0
        success_logs = (aggregates.successes if aggregates else 0) or 0
        avg_latency = (aggregates.avg_latency if aggregates else 0.0) or 0.0

        # 2. Distribuição por módulo
        module_counts = (
            session.query(AuditLogRecord.module, func.count(AuditLogRecord.id))
            .group_by(AuditLogRecord.module)
            .all()
        )
        by_module = {mod: count for mod, count in module_counts}

        # 3. Últimos erros indexados
        recent_errors = (
            session.query(AuditLogRecord)
            .filter(AuditLogRecord.status == "ERROR")
            .order_by(AuditLogRecord.created_at.desc())
            .limit(5)
            .all()
        )

        res = {
            "total_events": total_logs,
            "success_events": success_logs,
            "error_events": error_logs,
            "success_rate_percent": round((success_logs / total_logs * 100), 1) if total_logs > 0 else 100.0,
            "avg_duration_ms": round(float(avg_latency), 2),
            "by_module": by_module,
            "recent_errors": [
                {
                    "id": err.id,
                    "created_at": err.created_at.isoformat(),
                    "module": err.module,
                    "action": err.action,
                    "error_message": err.error_message,
                }
                for err in recent_errors
            ],
        }
        _STATS_CACHE = res
        _STATS_CACHE_TS = now_ts
        return res
    finally:
        session.close()
