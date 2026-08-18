from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
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


@router.post("/messages")
async def save_message(payload: MessageCreate, response: Response, db: Session = Depends(get_db)):
    """Salva a mensagem, realiza a extração semântica silenciosa e atualiza o grafo.

    Se a mensagem for vazia, ruído ou apenas emojis, ela é descartada sem consumir tokens ou persistir no banco.
    """
    msg = await memory_repository.save_message(payload, db=db)
    if msg is None:
        response.status_code = status.HTTP_200_OK
        return {
            "status": "ignored",
            "saved": False,
            "message_id": None,
            "speaker": payload.speaker,
            "reason": "Mensagem ignorada e descartada (vazia, apenas emojis, mídia sem texto ou trivial)",
        }

    response.status_code = status.HTTP_201_CREATED
    return {
        "status": "saved",
        "saved": True,
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
async def get_full_graph(
    main_only: bool = Query(default=True, description="Exibir apenas nós principais e conectados (padrão)"),
    days_cutoff: int = Query(default=7, description="Ocultar contatos sem interação há mais de X dias (padrão: 7)"),
    db: Session = Depends(get_db),
):
    """Retorna o grafo estruturado e otimizado para o frontend, aplicando filtros de relevância e corte temporal padrão (7 dias)."""
    from datetime import datetime, timezone, timedelta
    from src.contacts.models import ContactRecord
    from src.memory.models import MessageRecord
    from src.ai_gateway.bypass import is_owner_interaction, normalize_text
    import re

    category_colors = {
        "PERSON": {"background": "#10b981", "border": "#059669", "highlight": "#34d399"},
        "LOCATION": {"background": "#3b82f6", "border": "#2563eb", "highlight": "#60a5fa"},
        "PROJECT": {"background": "#8b5cf6", "border": "#7c3aed", "highlight": "#a78bfa"},
        "SYSTEM": {"background": "#f59e0b", "border": "#d97706", "highlight": "#fbbf24"},
        "EQUIPMENT": {"background": "#f97316", "border": "#ea580c", "highlight": "#fb923c"},
        "CONCEPT": {"background": "#64748b", "border": "#475569", "highlight": "#94a3b8"},
        "OTHER": {"background": "#64748b", "border": "#475569", "highlight": "#94a3b8"},
    }

    now = datetime.now(timezone.utc)
    if days_cutoff == 1:
        cutoff_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif days_cutoff > 1:
        cutoff_time = now - timedelta(days=days_cutoff)
    else:
        cutoff_time = None

    # 1. Conjunto estrito de identificadores de pessoas que CONVERSARAM no banco de dados
    active_conversations_people = set()
    if cutoff_time:
        recent_msgs = db.query(MessageRecord.speaker, MessageRecord.meta_info).filter(
            MessageRecord.created_at >= cutoff_time
        ).all()
        for spk, meta in recent_msgs:
            if spk:
                spk_str = str(spk).strip()
                active_conversations_people.add(spk_str.lower())
                active_conversations_people.add(normalize_text(spk_str))
                digits = re.sub(r"\D", "", spk_str)
                if digits:
                    active_conversations_people.add(digits)
                    if len(digits) >= 8:
                        active_conversations_people.add(digits[-8:])
            if isinstance(meta, dict):
                r_jid = str(meta.get("remoteJid") or meta.get("phone") or meta.get("sender_phone") or "")
                if r_jid:
                    r_digits = re.sub(r"\D", "", r_jid.split("@")[0])
                    if r_digits:
                        active_conversations_people.add(r_digits)
                        if len(r_digits) >= 8:
                            active_conversations_people.add(r_digits[-8:])
                p_name = meta.get("pushName")
                if p_name:
                    p_str = str(p_name).strip()
                    active_conversations_people.add(p_str.lower())
                    active_conversations_people.add(normalize_text(p_str))

    # Mapa de contatos cadastrados
    contacts_list = db.query(ContactRecord).all()
    contacts_by_name = {c.name.lower(): c for c in contacts_list if c.name}
    contacts_by_phone = {c.phone_number: c for c in contacts_list if c.phone_number}

    candidate_nodes = []
    candidate_node_ids = set()

    for n, attrs in knowledge_graph.graph.nodes(data=True):
        cat = attrs.get("category", "OTHER").upper()
        mentions = attrs.get("mentions", 1)
        degree = knowledge_graph.graph.degree(n) if knowledge_graph.graph.has_node(n) else 0
        is_owner = is_owner_interaction(n)

        # Detecta se o nó é uma Pessoa / Contato
        n_lower = n.strip().lower()
        n_norm = normalize_text(n)
        n_digits = re.sub(r"\D", "", n)
        matching_contact = contacts_by_name.get(n_lower) or (contacts_by_phone.get(n_digits) if n_digits else None)
        is_person = (cat == "PERSON") or (matching_contact is not None)

        # 1. Poda Estrita de Pessoas por Conversas Reais no Banco de Dados
        if days_cutoff > 0 and is_person and not is_owner:
            c_phone_digits = re.sub(r"\D", "", matching_contact.phone_number) if (matching_contact and matching_contact.phone_number) else ""
            c_name_norm = normalize_text(matching_contact.name) if matching_contact else ""
            
            has_talked = (
                (n_lower in active_conversations_people)
                or (n_norm in active_conversations_people)
                or (n_digits and n_digits in active_conversations_people)
                or (n_digits and len(n_digits) >= 8 and n_digits[-8:] in active_conversations_people)
                or (c_phone_digits and c_phone_digits in active_conversations_people)
                or (c_phone_digits and len(c_phone_digits) >= 8 and c_phone_digits[-8:] in active_conversations_people)
                or (c_name_norm and c_name_norm in active_conversations_people)
            )

            # Se não conversou nos últimos X dias no banco de dados, é podado do grafo ativo
            if not has_talked:
                continue

        # 2. Filtro de Nós Principais (main_only)
        if main_only and not is_owner:
            if degree == 0 and mentions < 3:
                continue
            if cat in ("CONCEPT", "OTHER") and degree <= 1 and mentions <= 1:
                continue

        colors = category_colors.get(cat, category_colors["OTHER"])
        size = 18 + min(mentions * 2 + degree * 2, 36)

        title_parts = [f"<b>{n}</b> ({cat})"]
        if attrs.get("role"):
            title_parts.append(f"Role: {attrs.get('role')}")
        if attrs.get("phone"):
            title_parts.append(f"Tel: {attrs.get('phone')}")
        if attrs.get("company"):
            title_parts.append(f"Empresa: {attrs.get('company')}")
        if attrs.get("details"):
            title_parts.append(f"Detalhes: {attrs.get('details')}")
        title_parts.append(f"Conexões: {degree} | Menções: {mentions}")

        candidate_nodes.append({
            "id": n,
            "label": n,
            "category": cat,
            "color": colors,
            "size": size,
            "title": "<br>".join(title_parts),
            "attributes": attrs,
            "degree": degree,
            "mentions": mentions,
        })
        candidate_node_ids.add(n)

    # Filtra arestas apenas entre os nós mantidos
    kept_edges = []
    connected_node_ids = set()
    for u, v, attrs in knowledge_graph.graph.edges(data=True):
        if u in candidate_node_ids and v in candidate_node_ids:
            rel = attrs.get("relation", "RELATED_TO")
            weight = float(attrs.get("weight", 1.0))
            kept_edges.append({
                "from": u,
                "to": v,
                "label": rel,
                "arrows": "to",
                "font": {"size": 9, "color": "#94a3b8", "strokeWidth": 2, "strokeColor": "#090d16"},
                "color": {"color": "#334155", "highlight": "#10b981"},
                "width": 1.0 + min(weight / 20.0, 3.0),
            })
            connected_node_ids.add(u)
            connected_node_ids.add(v)

    # Se main_only=True, mantém nós conectados, pessoas com conversas ativas no período e o proprietário
    if main_only:
        final_nodes = [
            n for n in candidate_nodes
            if (
                n["id"] in connected_node_ids
                or is_owner_interaction(n["id"])
                or (n.get("category") == "PERSON" and (n["id"].strip().lower() in active_conversations_people or normalize_text(n["id"]) in active_conversations_people))
            )
        ]
    else:
        final_nodes = candidate_nodes

    return {
        "nodes": final_nodes,
        "edges": kept_edges,
        "stats": {
            "total_nodes_in_graph": knowledge_graph.stats()["nodes"],
            "total_edges_in_graph": knowledge_graph.stats()["edges"],
            "filtered_nodes": len(final_nodes),
            "filtered_edges": len(kept_edges),
            "main_only": main_only,
            "days_cutoff": days_cutoff,
        },
    }


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

    query = db.query(MessageRecord).filter(
        (MessageRecord.revised_text != "") | (MessageRecord.raw_text != "")
    )
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


# ===================== Agente 'Zeladora' (Graph Janitor) =====================


@router.post(
    "/graph/clean",
    summary="Executa a faxina no Grafo de Conhecimento com o Agente Zeladora",
    tags=["graph", "janitor"],
)
async def clean_knowledge_graph(
    dry_run: bool = Query(default=False, description="Se True, apenas simula as exclusões e fusões sem alterar o disco"),
    min_edge_weight: float = Query(default=1.0, description="Peso mínimo para manter arestas no grafo"),
    prune_isolated: bool = Query(default=True, description="Remove nós isolados (grau 0 e menções <= 1)"),
    deduplicate_aliases: bool = Query(default=True, description="Desambigua e mescla nós quase-idênticos (aliases)"),
):
    """Executa a rotina de higienização do Grafo de Conhecimento, protegendo contatos oficiais e podando ruídos."""
    from src.memory.janitor import graph_janitor_service
    return graph_janitor_service.clean_graph(
        dry_run=dry_run,
        min_edge_weight=min_edge_weight,
        prune_isolated=prune_isolated,
        deduplicate_aliases=deduplicate_aliases,
    )


@router.get(
    "/graph/janitor/logs",
    summary="Consulta o histórico de faxinas realizadas pela Zeladora",
    tags=["graph", "janitor"],
)
async def get_graph_janitor_logs():
    """Retorna a lista de relatórios das últimas faxinas executadas pela Zeladora."""
    from src.memory.janitor import graph_janitor_service
    return graph_janitor_service.get_history()



