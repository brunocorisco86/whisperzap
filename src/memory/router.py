from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from src.ai_gateway.schemas import (
    DailySummaryRequest,
    DailySummaryResponse,
    HermesQueryRequest,
    HermesQueryResponse,
    WeeklyReportRequest,
    WeeklyReportResponse,
)
from src.memory.database import get_db
from src.memory.graph import knowledge_graph
from src.memory.models import (
    MemoryStats,
    MessageCreate,
    SearchQuery,
    SearchResult,
    TaskResponse,
    TaskUpdate,
)
from src.memory.repository import memory_repository
from src.reports.daily import daily_report_service
from src.reports.weekly import weekly_report_service

router = APIRouter(prefix="/api/v1/memory", tags=["Memória em Camadas & Agente Hermes"])


@router.post("/messages", status_code=status.HTTP_201_CREATED)
async def save_message(payload: MessageCreate, db: Session = Depends(get_db)):
    """Salva a mensagem, realiza a extração semântica silenciosa e atualiza o grafo."""
    msg = await memory_repository.save_message(payload, db=db)
    return {
        "message_id": msg.id,
        "speaker": msg.speaker,
        "intent": msg.intent,
        "summary": msg.summary,
        "tasks_extracted": len(msg.tasks),
        "entities_extracted": len(msg.entities),
        "created_at": msg.created_at,
    }


@router.post("/query", response_model=HermesQueryResponse, summary="Consulta ao Agente Hermes com RAG Híbrido")
async def query_hermes(payload: HermesQueryRequest, db: Session = Depends(get_db)):
    """Permite ao Hermes ou usuários fazerem perguntas à memória com busca vetorial + grafo + tarefas."""
    return await memory_repository.query_hermes_rag(
        query=payload.query,
        top_k=payload.top_k,
        min_similarity=payload.min_similarity,
        include_graph=payload.include_graph,
        db=db,
    )


@router.post("/daily/generate", response_model=DailySummaryResponse, summary="Gera Resumo Diário e Plano para Amanhã")
async def generate_daily_summary(
    payload: DailySummaryRequest = DailySummaryRequest(), db: Session = Depends(get_db)
):
    """Gera o Resumo Diário das 18:00 com ações prioritárias para o dia seguinte."""
    return await daily_report_service.generate_daily_report(
        target_date=payload.date,
        speaker_filter=payload.speaker_filter,
        db=db,
    )


@router.get("/daily", response_model=DailySummaryResponse, summary="Consulta Resumo Diário por data")
async def get_daily_summary(
    date: str | None = Query(default=None, description="Data no formato YYYY-MM-DD (default: hoje)"),
    speaker: str | None = Query(default=None, description="Filtro por remetente"),
    db: Session = Depends(get_db),
):
    """Retorna o Resumo Diário formatado para uma data específica."""
    return await daily_report_service.generate_daily_report(
        target_date=date,
        speaker_filter=speaker,
        db=db,
    )


@router.post("/weekly/generate", response_model=WeeklyReportResponse, summary="Gera Relatório Semanal & Plano de Domingo")
async def generate_weekly_report(
    payload: WeeklyReportRequest = WeeklyReportRequest(), db: Session = Depends(get_db)
):
    """Gera a análise estratégica semanal e o plano de domingo à noite."""
    return await weekly_report_service.generate_weekly_report(
        start_date=payload.start_date,
        end_date=payload.end_date,
        db=db,
    )


@router.get("/weekly", response_model=WeeklyReportResponse, summary="Consulta Relatório Semanal")
async def get_weekly_report(
    start_date: str | None = Query(default=None, description="Data início YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="Data fim YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """Retorna a análise semanal e métricas dos últimos 7 dias."""
    return await weekly_report_service.generate_weekly_report(
        start_date=start_date,
        end_date=end_date,
        db=db,
    )


@router.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(
    status: str | None = Query(default=None, description="Filtrar por status: PENDING, IN_PROGRESS, DONE"),
    priority: str | None = Query(default=None, description="Filtrar por prioridade: LOW, MEDIUM, HIGH, URGENT"),
    assignee: str | None = Query(default=None, description="Filtrar por responsável"),
    db: Session = Depends(get_db),
):
    """Lista tarefas extraídas com filtros."""
    return memory_repository.list_tasks(status=status, priority=priority, assignee=assignee, db=db)


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(task_id: str, payload: TaskUpdate, db: Session = Depends(get_db)):
    """Atualiza status ou dados de uma tarefa."""
    task = memory_repository.update_task(task_id, payload, db=db)
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return task


@router.post("/search", response_model=list[SearchResult])
async def search_memory(payload: SearchQuery, db: Session = Depends(get_db)):
    """Busca semântica de memórias por similaridade vetorial."""
    return await memory_repository.search_memories(
        query=payload.query,
        top_k=payload.top_k,
        min_similarity=payload.min_similarity,
        db=db,
    )


@router.get("/graph/nodes")
async def list_graph_nodes(category: str | None = Query(default=None, description="Filtrar por categoria")):
    """Lista entidades cadastradas no grafo de conhecimento."""
    return knowledge_graph.list_nodes(category=category)


@router.get("/graph/entity/{name}")
async def get_entity_neighborhood(name: str, depth: int = Query(default=1, ge=1, le=3)):
    """Retorna subgrafo vizinho e conexões diretas de uma entidade."""
    result = knowledge_graph.get_neighborhood(entity_name=name, depth=depth)
    if not result["found"]:
        raise HTTPException(status_code=404, detail=f"Entidade '{name}' não encontrada no grafo")
    return result


@router.get("/stats", response_model=MemoryStats)
async def get_memory_stats(db: Session = Depends(get_db)):
    """Retorna estatísticas globais da memória e grafo."""
    return memory_repository.get_stats(db=db)

