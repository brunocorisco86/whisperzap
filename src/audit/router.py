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


@router.get("/tokens", summary="Auditoria e Governança dos Tokens de API")
async def check_tokens_health():
    """Valida formato, presença, mascaramento e conectividade ativa das credenciais de API."""
    from datetime import datetime, timezone
    import time
    import httpx
    from src.config import settings, mask_token

    results = {}

    # 1. Google Gemini API
    gemini_key = settings.GEMINI_API_KEY
    if not gemini_key or gemini_key.startswith("sua_chave"):
        results["gemini"] = {
            "configured": False,
            "status": "MISSING_KEY",
            "masked_key": mask_token(gemini_key),
            "latency_ms": 0,
        }
    else:
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                r = await client.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={gemini_key}")
                lat = round((time.perf_counter() - t0) * 1000, 1)
                results["gemini"] = {
                    "configured": True,
                    "valid": r.status_code == 200,
                    "status_code": r.status_code,
                    "latency_ms": lat,
                    "status": "HEALTHY" if r.status_code == 200 else ("OVERLOADED_OR_AUTH_ERR" if r.status_code in (401, 403, 429, 503) else f"HTTP_{r.status_code}"),
                    "masked_key": mask_token(gemini_key),
                }
        except Exception as e:
            results["gemini"] = {
                "configured": True,
                "valid": False,
                "status": "TIMEOUT_OR_NETWORK_ERR",
                "error": str(e),
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "masked_key": mask_token(gemini_key),
            }

    # 2. WhatsApp Evolution API
    evo_url = settings.EVOLUTION_API_URL.rstrip("/")
    evo_key = settings.EVOLUTION_API_KEY
    if not evo_key:
        results["evolution_api"] = {
            "configured": False,
            "status": "MISSING_KEY",
            "masked_key": mask_token(evo_key),
        }
    else:
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=3.5) as client:
                r = await client.get(
                    f"{evo_url}/instance/connectionState/{settings.EVOLUTION_INSTANCE}",
                    headers={"apikey": evo_key},
                )
                lat = round((time.perf_counter() - t0) * 1000, 1)
                state = r.json().get("instance", {}).get("state") if r.status_code == 200 else None
                results["evolution_api"] = {
                    "configured": True,
                    "valid": r.status_code == 200,
                    "status_code": r.status_code,
                    "latency_ms": lat,
                    "connection_state": state,
                    "instance": settings.EVOLUTION_INSTANCE,
                    "status": "HEALTHY" if state == "open" else ("DISCONNECTED" if r.status_code == 200 else "AUTH_OR_DOWN"),
                    "masked_key": mask_token(evo_key),
                }
        except Exception as e:
            results["evolution_api"] = {
                "configured": True,
                "valid": False,
                "status": "UNREACHABLE",
                "error": str(e),
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "masked_key": mask_token(evo_key),
            }

    # 3. OpenRouter (Opcional)
    openrouter_key = settings.OPENROUTER_API_KEY
    is_openrouter_cfg = bool(openrouter_key and not openrouter_key.startswith("sua_chave"))
    results["openrouter"] = {
        "configured": is_openrouter_cfg,
        "masked_key": mask_token(openrouter_key),
        "status": "CONFIGURED" if is_openrouter_cfg else "OPTIONAL_NOT_CONFIGURED",
    }

    all_critical_healthy = (
        results.get("gemini", {}).get("status") == "HEALTHY"
        and results.get("evolution_api", {}).get("status") == "HEALTHY"
    )

    return {
        "status": "healthy" if all_critical_healthy else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tokens": results,
    }

