"""Router FastAPI para a Memória em Camadas e Grafo de Conhecimento."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
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

router = APIRouter(prefix="/api/v1/memory", tags=["Memória em Camadas & Grafo"])


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
