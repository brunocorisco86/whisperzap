"""Router FastAPI para a API de Auditoria & Observabilidade do Hermes."""

from typing import List, Optional
from fastapi import APIRouter, Query
from src.audit.service import get_audit_logs, get_audit_stats
from src.memory.models import AuditLogResponse

router = APIRouter(prefix="/api/v1/audit", tags=["Auditoria & Observabilidade"])


@router.get("/logs", response_model=List[AuditLogResponse], summary="Consulta histórico de logs de auditoria")
async def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    module: Optional[str] = Query(default=None, description="Filtrar por módulo (ex: TRANSCRIBER, AI_GATEWAY, MEMORY, WHATSAPP, AUTH)"),
    status: Optional[str] = Query(default=None, description="Filtrar por status (SUCCESS, ERROR, BYPASS, WARNING)"),
    speaker: Optional[str] = Query(default=None, description="Filtrar por nome/identificador do contato"),
    search: Optional[str] = Query(default=None, description="Busca textual na ação ou mensagem de erro"),
):
    """Retorna lista paginada e filtrada de eventos de auditoria do sistema."""
    return get_audit_logs(
        limit=limit,
        offset=offset,
        module=module,
        status=status,
        speaker=speaker,
        search=search,
    )


@router.get("/stats", summary="Métricas consolidadas de auditoria e desempenho")
async def audit_metrics():
    """Retorna indicadores-chave de desempenho (KPIs), taxa de sucesso e distribuição por módulo."""
    return get_audit_stats()
