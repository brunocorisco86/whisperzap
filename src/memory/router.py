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


@router.get("/graph/full")
async def get_full_graph():
    """Retorna o grafo completo estruturado para renderização no frontend (vis-network / force-directed)."""
    nodes = []
    category_colors = {
        "PERSON": {"background": "#10b981", "border": "#059669", "highlight": "#34d399"},
        "LOCATION": {"background": "#3b82f6", "border": "#2563eb", "highlight": "#60a5fa"},
        "PROJECT": {"background": "#8b5cf6", "border": "#7c3aed", "highlight": "#a78bfa"},
        "SYSTEM": {"background": "#f59e0b", "border": "#d97706", "highlight": "#fbbf24"},
        "EQUIPMENT": {"background": "#f97316", "border": "#ea580c", "highlight": "#fb923c"},
        "CONCEPT": {"background": "#64748b", "border": "#475569", "highlight": "#94a3b8"},
        "OTHER": {"background": "#64748b", "border": "#475569", "highlight": "#94a3b8"},
    }

    for n, attrs in knowledge_graph.graph.nodes(data=True):
        cat = attrs.get("category", "OTHER").upper()
        colors = category_colors.get(cat, category_colors["OTHER"])
        mentions = attrs.get("mentions", 1)
        size = 18 + min(mentions * 2, 32)

        title_parts = [f"<b>{n}</b> ({cat})"]
        if attrs.get("role"):
            title_parts.append(f"Role: {attrs.get('role')}")
        if attrs.get("phone"):
            title_parts.append(f"Tel: {attrs.get('phone')}")
        if attrs.get("company"):
            title_parts.append(f"Empresa: {attrs.get('company')}")
        if attrs.get("details"):
            title_parts.append(f"Detalhes: {attrs.get('details')}")

        nodes.append({
            "id": n,
            "label": n,
            "category": cat,
            "color": colors,
            "size": size,
            "title": "<br>".join(title_parts),
            "attributes": attrs,
        })

    edges = []
    for u, v, attrs in knowledge_graph.graph.edges(data=True):
        rel = attrs.get("relation", "RELATED_TO")
        weight = float(attrs.get("weight", 1.0))
        edges.append({
            "from": u,
            "to": v,
            "label": rel,
            "arrows": "to",
            "font": {"size": 9, "color": "#94a3b8", "strokeWidth": 2, "strokeColor": "#090d16"},
            "color": {"color": "#334155", "highlight": "#10b981"},
            "width": 1.0 + min(weight / 20.0, 3.0),
        })

    return {"nodes": nodes, "edges": edges, "stats": knowledge_graph.stats()}


@router.get("/messages")
async def list_recent_messages(
    limit: int = Query(default=50, le=200),
    speaker: str | None = Query(default=None, description="Filtrar por remetente"),
    intent: str | None = Query(default=None, description="Filtrar por intenção"),
    sentiment: str | None = Query(default=None, description="Filtrar por sentimento"),
    search: str | None = Query(default=None, description="Busca textual livre"),
    db: Session = Depends(get_db),
):
    """Lista mensagens e notas de áudio enriquecidas com transcrições, metadados e tarefas."""
    from src.memory.models import MessageRecord

    query = db.query(MessageRecord)
    if speaker:
        query = query.filter(MessageRecord.speaker.ilike(f"%{speaker.strip()}%"))
    if intent:
        query = query.filter(MessageRecord.intent == intent.upper())
    if sentiment:
        query = query.filter(MessageRecord.sentiment == sentiment.upper())
    if search:
        search_term = f"%{search.strip()}%"
        query = query.filter(
            (MessageRecord.revised_text.ilike(search_term))
            | (MessageRecord.raw_text.ilike(search_term))
            | (MessageRecord.summary.ilike(search_term))
            | (MessageRecord.speaker.ilike(search_term))
        )

    records = query.order_by(MessageRecord.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "speaker": r.speaker,
            "intent": r.intent or "NOTE",
            "urgency": r.urgency or "MEDIUM",
            "sentiment": r.sentiment or "NEUTRAL",
            "sentiment_score": round(r.sentiment_score or 0.0, 2),
            "summary": r.summary,
            "revised_text": r.revised_text,
            "raw_text": r.raw_text or r.revised_text,
            "audio_duration_s": r.audio_duration_s,
            "audio_filename": r.audio_filename,
            "meta_info": r.meta_info if isinstance(r.meta_info, dict) else {},
            "created_at": r.created_at.strftime("%d/%m/%Y %H:%M") if r.created_at else None,
            "created_at_iso": r.created_at.isoformat() if r.created_at else None,
            "tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "assignee": t.assignee,
                    "due_date": t.due_date,
                    "priority": t.priority,
                    "status": t.status,
                }
                for t in r.tasks
            ],
            "entities": [
                {
                    "name": e.name,
                    "category": e.category,
                    "details": e.details,
                }
                for e in r.entities
            ],
            "tasks_count": len(r.tasks),
            "entities_count": len(r.entities),
        }
        for r in records
    ]


@router.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(message_id: str, db: Session = Depends(get_db)):
    """Exclui uma mensagem e seus artefatos dependentes da memória."""
    from src.memory.models import EmbeddingRecord, EntityRecord, MessageRecord, TaskRecord

    msg = db.query(MessageRecord).filter(MessageRecord.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Mensagem não encontrada")

    # Remove dependentes
    db.query(EmbeddingRecord).filter(EmbeddingRecord.message_id == message_id).delete()
    db.query(TaskRecord).filter(TaskRecord.message_id == message_id).delete()
    db.query(EntityRecord).filter(EntityRecord.message_id == message_id).delete()
    db.delete(msg)
    db.commit()
    return None


@router.get("/stats", response_model=MemoryStats)
async def get_memory_stats(db: Session = Depends(get_db)):
    """Retorna estatísticas globais da memória e grafo."""
    return memory_repository.get_stats(db=db)


# ===================== Série Temporal de Sentimentos =====================


@router.post("/sentiment/collect", summary="Consolida sentimentos do dia para série temporal")
async def collect_daily_sentiments(
    date: str | None = Query(default=None, description="Data no formato YYYY-MM-DD (default: hoje)"),
    db: Session = Depends(get_db),
):
    """Executa a consolidação de sentimentos de todas as pessoas que interagiram na data."""
    from src.memory.sentiment_timeline import sentiment_timeline_service
    return sentiment_timeline_service.collect_daily_sentiments(target_date=date, db=db)


@router.get("/sentiment/daily", summary="Consulta snapshots de sentimentos consolidados do dia")
async def get_daily_sentiment_snapshots(
    date: str | None = Query(default=None, description="Data no formato YYYY-MM-DD (default: hoje)"),
    db: Session = Depends(get_db),
):
    """Retorna o panorama e métricas emocionais de todas as pessoas em um determinado dia."""
    from src.memory.sentiment_timeline import sentiment_timeline_service
    return sentiment_timeline_service.get_daily_snapshots(target_date=date, db=db)


@router.get("/sentiment/timeline", summary="Consulta série temporal de sentimentos de uma pessoa")
async def get_sentiment_timeline(
    speaker: str = Query(..., description="Nome ou identificador da pessoa"),
    start_date: str | None = Query(default=None, description="Data inicial YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="Data final YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """Retorna a evolução histórica de sentimentos e pontos da série temporal para gráficos."""
    from src.memory.sentiment_timeline import sentiment_timeline_service
    return sentiment_timeline_service.get_person_timeline(
        speaker=speaker,
        start_date=start_date,
        end_date=end_date,
        db=db,
    )



