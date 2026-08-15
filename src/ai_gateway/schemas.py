from typing import Literal, Optional
from pydantic import BaseModel, Field



class ReviseRequest(BaseModel):
    """Requisição para revisão contextual de transcrição."""

    text: str = Field(
        ...,
        description="Texto bruto da transcrição vindo do Whisper",
        examples=["entao amanha preciso fala com joao sobre o sensor de racao do silo 3"],
    )
    context: Optional[str] = Field(
        default=None,
        description="Contexto opcional (ex: mensagens anteriores, projeto ativo, termos frequentes)",
        examples=["Usuário atua com automação de silos e integração avícola."],
    )
    metadata: Optional[dict] = Field(
        default=None,
        description="Metadados adicionais da mensagem de áudio",
    )


class ReviseResponse(BaseModel):
    """Resposta com o texto revisado."""

    text_revised: str = Field(
        ...,
        description="Texto limpo e revisado com pontuação sem acréscimo de fatos",
        examples=["Então amanhã preciso falar com João sobre o sensor de ração do silo 3."],
    )
    provider: str = Field(..., description="Provedor de LLM utilizado na revisão")
    model: str = Field(..., description="Modelo utilizado na revisão")
    processing_time_ms: float = Field(..., description="Tempo de processamento em milissegundos")


class ExtractedTask(BaseModel):
    """Tarefa extraída de uma mensagem."""

    title: str = Field(..., description="Título conciso e acionável da tarefa")
    assignee: Optional[str] = Field(default=None, description="Pessoa responsável pela execução")
    due_date: Optional[str] = Field(default=None, description="Prazo ou data mencionada (ex: 'amanhã', '2026-08-15', 'sexta-feira')")
    priority: Literal["LOW", "MEDIUM", "HIGH", "URGENT"] = Field(default="MEDIUM", description="Nível de prioridade inferido")


class ExtractedEntity(BaseModel):
    """Entidade nomeada reconhecida no contexto."""

    name: str = Field(..., description="Nome da entidade")
    category: Literal["PERSON", "LOCATION", "EQUIPMENT", "PROJECT", "SYSTEM", "CONCEPT", "OTHER"] = Field(
        default="OTHER", description="Categoria da entidade"
    )
    details: Optional[str] = Field(default=None, description="Detalhes contextuais ou especificação")


class ExtractedTriple(BaseModel):
    """Tripla semântica de relacionamento (Sujeito, Predicado, Objeto)."""

    source: str = Field(..., description="Entidade de origem (Sujeito)")
    relation: str = Field(..., description="Relação semântica em maiúsculas (ex: SPOUSE_OF, MANAGES, RESPONSIBLE_FOR, BELONGS_TO, LOCATED_IN, DEPENDS_ON, HAS_PROBLEM)")
    target: str = Field(..., description="Entidade de destino (Objeto)")


class SemanticExtractionRequest(BaseModel):
    """Requisição para extração semântica de intenções e entidades."""

    text: str = Field(..., description="Texto revisado ou mensagem a ser analisada")
    speaker: Optional[str] = Field(default="user", description="Identificador ou nome de quem enviou")
    context: Optional[str] = Field(default=None, description="Contexto adicional da conversa")
    include_dictionary: bool = Field(default=True, description="Se deve injetar o glossário léxico de domínio no prompt")


class SemanticExtractionResponse(BaseModel):
    """Resposta estruturada da extração semântica."""

    intent: Literal["TASK", "IDEA", "DECISION", "EVENT", "PROBLEM", "NOTE", "QUESTION"] = Field(
        ..., description="Intenção primária da mensagem"
    )
    summary: str = Field(..., description="Resumo em 1 frase do conteúdo principal")
    sentiment: Optional[str] = Field(default="NEUTRAL", description="Sentimento/tom emocional do locutor (POSITIVE, NEUTRAL, URGENT, ANXIOUS, FRUSTRATED, CONFIDENT)")
    sentiment_score: Optional[float] = Field(default=0.0, description="Score numérico de -1.0 a 1.0")
    tasks: list[ExtractedTask] = Field(default_factory=list, description="Lista de tarefas acionáveis extraídas")
    entities: list[ExtractedEntity] = Field(default_factory=list, description="Entidades nomeadas identificadas")
    triples: list[ExtractedTriple] = Field(default_factory=list, description="Relacionamentos e triplas semânticas explícitas extraídas")
    decisions: list[str] = Field(default_factory=list, description="Decisões tomadas ou acordos firmados")
    ideas: list[str] = Field(default_factory=list, description="Ideias, insights ou sugestões")
    topics: list[str] = Field(default_factory=list, description="Tópicos e palavras-chave principais")
    urgency: Literal["LOW", "MEDIUM", "HIGH", "URGENT"] = Field(default="MEDIUM", description="Nível de urgência geral")
    provider: str = Field(..., description="Provedor de LLM utilizado")
    model: str = Field(..., description="Modelo utilizado")
    processing_time_ms: float = Field(..., description="Tempo de processamento em ms")


# ===================== Agente Hermes Q&A (RAG Híbrido) =====================


class MemorySourceCitation(BaseModel):
    """Citação de fonte de memória utilizada na resposta do Hermes."""

    message_id: str = Field(..., description="ID da mensagem de origem")
    speaker: str = Field(default="user", description="Remetente da mensagem")
    text_snippet: str = Field(..., description="Trecho ou resumo relevante da mensagem")
    similarity: float = Field(default=0.0, description="Similaridade semântica com a pergunta")
    created_at: Optional[str] = Field(default=None, description="Data/hora em que a memória foi gravada")


class HermesQueryRequest(BaseModel):
    """Requisição de consulta contextual ao Agente Hermes."""

    query: str = Field(..., description="Pergunta ou instrução em linguagem natural", examples=["Quais foram os problemas relatados sobre os sensores de silo?"])
    top_k: int = Field(default=5, ge=1, le=20, description="Quantidade máxima de memórias a recuperar")
    min_similarity: float = Field(default=0.0, ge=0.0, le=1.0, description="Similaridade mínima de cosseno")
    include_graph: bool = Field(default=True, description="Se deve consultar conexões e entidades do Grafo de Conhecimento")


class HermesQueryResponse(BaseModel):
    """Resposta do Agente Hermes com RAG Híbrido e citação estrita de fontes."""

    query: str = Field(..., description="Pergunta original")
    answer: str = Field(..., description="Resposta contextualizada gerada pelo Agente Hermes")
    sources: list[MemorySourceCitation] = Field(default_factory=list, description="Fontes/mensagens recuperadas e citadas")
    related_entities: list[str] = Field(default_factory=list, description="Entidades conectadas identificadas no grafo")
    pending_tasks_mentioned: list[str] = Field(default_factory=list, description="Tarefas abertas relacionadas ao tópico")
    provider: str = Field(..., description="Provedor de LLM utilizado")
    model: str = Field(..., description="Modelo de LLM utilizado")
    processing_time_ms: float = Field(..., description="Tempo de processamento em ms")


# ===================== Relatórios e Síntese =====================


class DailySummaryRequest(BaseModel):
    """Requisição para geração do Resumo Diário e Plano para Amanhã."""

    date: Optional[str] = Field(default=None, description="Data no formato YYYY-MM-DD (default: hoje)")
    speaker_filter: Optional[str] = Field(default=None, description="Filtrar por remetente específico")


class DailyActionItem(BaseModel):
    """Ação recomendada para o plano do dia seguinte."""

    title: str = Field(..., description="Ação a ser executada")
    assignee: Optional[str] = Field(default=None, description="Responsável")
    priority: Literal["LOW", "MEDIUM", "HIGH", "URGENT"] = Field(default="MEDIUM", description="Prioridade")
    due_date: Optional[str] = Field(default=None, description="Prazo")
    related_project: Optional[str] = Field(default=None, description="Projeto ou área relacionada")


class DailySummaryResponse(BaseModel):
    """Resposta estruturada do Resumo Diário."""

    date: str = Field(..., description="Data analisada (YYYY-MM-DD)")
    executive_summary: str = Field(..., description="Visão geral executiva do dia")
    key_events: list[str] = Field(default_factory=list, description="Principais acontecimentos")
    decisions: list[str] = Field(default_factory=list, description="Decisões tomadas")
    issues_and_blockers: list[str] = Field(default_factory=list, description="Problemas, bloqueios ou riscos identificados")
    completed_tasks: list[str] = Field(default_factory=list, description="Tarefas finalizadas no dia")
    pending_tasks: list[str] = Field(default_factory=list, description="Tarefas que continuam pendentes")
    plan_for_tomorrow: list[DailyActionItem] = Field(default_factory=list, description="Plano de ação para o dia seguinte")
    whatsapp_text: str = Field(..., description="Texto limpo e pronto para envio no WhatsApp com formatação e emojis")
    messages_analyzed: int = Field(default=0, description="Total de mensagens analisadas")
    provider: str = Field(..., description="Provedor de LLM utilizado")
    model: str = Field(..., description="Modelo de LLM utilizado")
    processing_time_ms: float = Field(..., description="Tempo de processamento em ms")


class WeeklyReportRequest(BaseModel):
    """Requisição para relatório semanal e plano de domingo."""

    start_date: Optional[str] = Field(default=None, description="Data de início (YYYY-MM-DD)")
    end_date: Optional[str] = Field(default=None, description="Data de fim (YYYY-MM-DD)")


class WeeklyReportResponse(BaseModel):
    """Resposta consolidada de inteligência semanal."""

    period: str = Field(..., description="Período coberto (ex: 2026-08-08 a 2026-08-14)")
    executive_summary: str = Field(..., description="Visão geral dos resultados e dinâmicas da semana")
    active_projects: list[str] = Field(default_factory=list, description="Projetos mais movimentados")
    top_contacts: list[str] = Field(default_factory=list, description="Pessoas/contatos com maior interação")
    bottlenecks: list[str] = Field(default_factory=list, description="Gargalos e problemas recorrentes")
    tasks_metrics: dict = Field(default_factory=dict, description="Métricas de execução (total, concluídas, pendentes)")
    sunday_strategic_plan: list[DailyActionItem] = Field(default_factory=list, description="Plano estratégico para a semana seguinte")
    whatsapp_text: str = Field(..., description="Relatório semanal formatado para WhatsApp")
    messages_analyzed: int = Field(default=0, description="Total de mensagens analisadas")
    provider: str = Field(..., description="Provedor de LLM utilizado")
    model: str = Field(..., description="Modelo de LLM utilizado")
    processing_time_ms: float = Field(..., description="Tempo de processamento em ms")


