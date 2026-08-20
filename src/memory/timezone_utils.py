"""Utilitários de Fuso Horário e Conversão para Horário Oficial de Brasília (America/Sao_Paulo)."""

from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo
from typing import Optional, Any, Union

BRASILIA_TZ = ZoneInfo("America/Sao_Paulo")


def get_now_brt() -> datetime:
    """Retorna o datetime atual no Horário Oficial de Brasília (UTC-3)."""
    return datetime.now(BRASILIA_TZ)


def to_local_tz(dt: Any, tz: ZoneInfo = BRASILIA_TZ) -> Optional[datetime]:
    """Converte um datetime, date ou string ISO (UTC ou naive) para o fuso horário de Brasília."""
    if dt is None:
        return None

    if isinstance(dt, str):
        dt_str = dt.strip()
        if not dt_str:
            return None
        try:
            # Suporta sufixo 'Z' ou strings com offset
            parsed = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            return to_local_tz(parsed, tz)
        except Exception:
            return None

    if isinstance(dt, date) and not isinstance(dt, datetime):
        return datetime(dt.year, dt.month, dt.day, 0, 0, 0, tzinfo=tz)

    if not isinstance(dt, datetime):
        return None

    if dt.tzinfo is None:
        # Se for naive, assume UTC e converte para Brasília
        dt_utc = dt.replace(tzinfo=timezone.utc)
        return dt_utc.astimezone(tz)

    return dt.astimezone(tz)


def format_brt(dt: Any, fmt: str = "%d/%m/%Y %H:%M") -> str:
    """Formata um datetime no fuso de Brasília com fallback seguro."""
    local_dt = to_local_tz(dt)
    if local_dt is None:
        return ""
    return local_dt.strftime(fmt)

