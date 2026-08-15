"""Módulo de Analytics & Dashboard Executivo."""

from src.analytics.router import router
from src.analytics.service import analytics_service

__all__ = ["router", "analytics_service"]
