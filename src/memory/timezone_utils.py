"""Utilitários de Fuso Horário e Conversão para Horário Oficial de Brasília (America/Sao_Paulo)."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Optional

BRASILIA_TZ = ZoneInfo("America/Sao_Paulo")


def get_now_brt() -> datetime:
    """Retorna o datetime atual no Horário Oficial de Brasília (UTC-3)."""
    return datetime.now(BRASILIA_TZ)


def to_local_tz(dt: Optional[datetime], tz: ZoneInfo = BRASILIA_TZ) -> Optional[datetime]:
    """Converte um datetime (UTC ou naive) para o fuso horário de Brasília."""
    if dt is None:
        return None

    if dt.tzinfo is None:
        # Se for naive, assume UTC e converte para Brasília
        dt_utc = dt.replace(tzinfo=timezone.utc)
        return dt_utc.astimezone(tz)
    
    return dt.astimezone(tz)


def format_brt(dt: Optional[datetime], fmt: str = "%d/%m/%Y %H:%M") -> str:
    """Formata um datetime no fuso de Brasília."""
    local_dt = to_local_tz(dt)
    if local_dt is None:
        return ""
    return local_dt.strftime(fmt)
