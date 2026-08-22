"""Serviço de Auditoria e Observabilidade Estruturada para o Hermes Voice Memory."""

import json
import logging
from logging.handlers import RotatingFileHandler
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import func
from src.config import settings
from src.memory.database import SessionLocal
from src.memory.models import AuditLogRecord

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


def get_audit_stats() -> Dict[str, Any]:
    """Calcula estatísticas e métricas operacionais agregadas."""
    session = SessionLocal()
    try:
        total_logs = session.query(func.count(AuditLogRecord.id)).scalar() or 0
        error_logs = session.query(func.count(AuditLogRecord.id)).filter(AuditLogRecord.status == "ERROR").scalar() or 0
        success_logs = session.query(func.count(AuditLogRecord.id)).filter(AuditLogRecord.status == "SUCCESS").scalar() or 0
        avg_latency = session.query(func.avg(AuditLogRecord.duration_ms)).scalar() or 0.0

        # Distribuição por módulo
        module_counts = (
            session.query(AuditLogRecord.module, func.count(AuditLogRecord.id))
            .group_by(AuditLogRecord.module)
            .all()
        )
        by_module = {mod: count for mod, count in module_counts}

        # Últimos erros
        recent_errors = (
            session.query(AuditLogRecord)
            .filter(AuditLogRecord.status == "ERROR")
            .order_by(AuditLogRecord.created_at.desc())
            .limit(5)
            .all()
        )

        return {
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
    finally:
        session.close()
