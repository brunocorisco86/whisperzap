"""Schemas Pydantic para o Módulo Analítico e Dashboard Executivo."""

from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field


class KPICard(BaseModel):
    """Representa um cartão de KPI com valor, rótulo e variação percentual."""
    title: str
    value: Union[str, int, float]
    subtitle: Optional[str] = None
    trend_pct: Optional[float] = None
    trend_direction: Optional[str] = None  # UP, DOWN, NEUTRAL
    icon: Optional[str] = None


class TimeSeriesPoint(BaseModel):
    """Ponto em uma série temporal agregada."""
    period_label: str  # ex: '15/08', 'Sem 33', 'Ago/2026'
    raw_date: str
    unique_senders: int = 0
    total_messages: int = 0
    audio_messages: int = 0
    text_messages: int = 0
    avg_chars: float = 0.0
    avg_audio_duration_s: float = 0.0
    tasks_generated: int = 0


class TopSenderMetric(BaseModel):
    """Métrica agregada por remetente/contato."""
    speaker: str
    role: Optional[str] = None
    phone_number: Optional[str] = None
    avatar_url: Optional[str] = None
    total_messages: int = 0
    audio_count: int = 0
    total_duration_s: float = 0.0
    tasks_count: int = 0
    dominant_sentiment: str = "NEUTRAL"
    avg_sentiment_score: float = 0.0


class WordFrequencyItem(BaseModel):
    """Item de frequência de palavras/tópicos para o WordMap."""
    word: str
    count: int
    category: str = "GERAL"  # ZOOTECNIA, LOGISTICA, GESTAO, PESSOAL, GERAL
    weight_pct: float = 0.0


class HeatmapCell(BaseModel):
    """Célula de intensidade para a matriz de horários (24h x 7 dias)."""
    day_of_week: int  # 0 = Segunda, ..., 6 = Domingo
    day_name: str
    hour: int  # 0 a 23
    count: int = 0


class AnalyticsDashboardResponse(BaseModel):
    """Payload completo consolidado para renderização do Dashboard."""
    period: str
    group_by: str
    start_date: str
    end_date: str
    
    # 5 Hero KPIs
    kpi_unique_senders: KPICard
    kpi_total_messages: KPICard
    kpi_audio_duration: KPICard
    kpi_actionability_rate: KPICard
    kpi_sentiment_health: KPICard
    
    # Gráfico 1: Série temporal de pessoas e mensagens
    timeseries: List[TimeSeriesPoint]
    
    # Gráfico 2: Top interlocutores
    top_senders: List[TopSenderMetric]
    
    # Gráfico 3: Nuvem de Palavras / WordMap
    wordmap: List[WordFrequencyItem]
    
    # Gráfico 4: Matriz de Horários de Pico (Heatmap)
    heatmap: List[HeatmapCell]
    
    # Metadados adicionais
    summary_text: Optional[str] = None
