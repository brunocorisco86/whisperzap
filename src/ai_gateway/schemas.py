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
    tasks: list[ExtractedTask] = Field(default_factory=list, description="Lista de tarefas acionáveis extraídas")
    entities: list[ExtractedEntity] = Field(default_factory=list, description="Entidades nomeadas identificadas")
    decisions: list[str] = Field(default_factory=list, description="Decisões tomadas ou acordos firmados")
    ideas: list[str] = Field(default_factory=list, description="Ideias, insights ou sugestões")
    topics: list[str] = Field(default_factory=list, description="Tópicos e palavras-chave principais")
    urgency: Literal["LOW", "MEDIUM", "HIGH", "URGENT"] = Field(default="MEDIUM", description="Nível de urgência geral")
    provider: str = Field(..., description="Provedor de LLM utilizado")
    model: str = Field(..., description="Modelo utilizado")
    processing_time_ms: float = Field(..., description="Tempo de processamento em ms")

