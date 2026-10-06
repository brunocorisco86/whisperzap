"""Schemas Pydantic para o Orquestrador JEV (Judge - Evaluator - Verifier)."""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class JEVAction(str, Enum):
    """Ação de roteamento deliberada pelo Judge."""
    BYPASS = "BYPASS"                   # Descarte ou silêncio (saudações, ruído, SAC)
    DIRECT_RESOLVE = "DIRECT_RESOLVE"   # Tarefa ou nota direta resolvida localmente (zero tokens)
    DEEP_ANALYSIS = "DEEP_ANALYSIS"     # Áudio complexo/longo que requer LLM mestre (Gemini)
    GRAPH_QUERY = "GRAPH_QUERY"         # Pergunta sobre histórico, relacionamentos ou entidades


class JEVIntent(str, Enum):
    """Intenção semântica identificada pelo JEV."""
    TASK = "TASK"
    IDEA = "IDEA"
    DECISION = "DECISION"
    MEMO = "MEMO"
    QUESTION = "QUESTION"
    PROBLEM = "PROBLEM"
    NOISE = "NOISE"


class JEVUrgency(str, Enum):
    """Nível de urgência avaliado pelo JEV."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class JEVJudgement(BaseModel):
    """Veredito estruturado emitido pelo Judge."""
    action: JEVAction = Field(..., description="Ação recomendada de roteamento")
    intent: JEVIntent = Field(default=JEVIntent.MEMO, description="Intenção semântica principal")
    urgency: JEVUrgency = Field(default=JEVUrgency.MEDIUM, description="Urgência classificada")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Grau de confiança da decisão (0 a 1)")
    suggested_route: str = Field(default="gemini", description="Motor sugerido: 'local', 'gemini', 'bypass'")
    tier_used: str = Field(default="tier1_heuristic", description="Tier que tomou a decisão: 'tier1_heuristic' ou 'tier2_slm'")
    rationale: str = Field(default="", description="Breve justificativa técnica do veredito")
    extracted_entities: List[str] = Field(default_factory=list, description="Entidades preliminares identificadas")
    direct_task_title: Optional[str] = Field(default=None, description="Título da tarefa caso seja DIRECT_RESOLVE")
    direct_due_date: Optional[str] = Field(default=None, description="Data limite identificada localmente (YYYY-MM-DD)")


class JEVJudgeRequest(BaseModel):
    """Payload de entrada para avaliação do JEV via API."""
    text: str = Field(..., min_length=1, description="Texto ou transcrição a ser julgado")
    speaker: Optional[str] = Field(default="Bruno", description="Nome ou telefone do locutor")
    is_self_memo: bool = Field(default=False, description="Indica se é nota pessoal do usuário")
    duration_s: float = Field(default=0.0, description="Duração do áudio em segundos, se aplicável")
    meta_info: Optional[Dict[str, Any]] = Field(default=None, description="Metadados do canal (WhatsApp, pushName, etc.)")
