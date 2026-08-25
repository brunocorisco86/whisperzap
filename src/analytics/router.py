"""Rotas da API para Dashboard & Analytics — Hermes Voice Memory."""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.analytics.schemas import AnalyticsDashboardResponse
from src.analytics.service import analytics_service
from src.memory.database import get_db

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/dashboard", response_model=AnalyticsDashboardResponse)
def get_analytics_dashboard(
    period: str = Query(
        default="3d",
        description="Período de análise: 'today', '3d', '7d', '30d', 'month', 'all'",
    ),
    group_by: str = Query(
        default="day",
        description="Agrupamento temporal: 'day', 'week', 'month'",
    ),
    db: Session = Depends(get_db),
):
    """Retorna dados consolidados para o Dashboard Executivo (KPIs, Séries Temporais, Top Interlocutores, WordMap e Heatmap)."""
    return analytics_service.get_dashboard_metrics(
        period=period,
        group_by=group_by,
        db=db,
    )
