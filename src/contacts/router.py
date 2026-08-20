import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status

logger = logging.getLogger(__name__)
from sqlalchemy.orm import Session
from src.contacts.models import ContactRecord
from src.contacts.schemas import (
    ContactBatchImportRequest,
    ContactBatchImportResponse,
    ContactCreate,
    ContactResponse,
    ContactUpdate,
)
from src.contacts.service import contact_service, record_to_response
from src.memory.database import get_db

router = APIRouter(prefix="/api/v1/contacts", tags=["Contatos & Papéis"])


@router.get("", response_model=list[ContactResponse])
async def list_contacts(
    role: Optional[str] = Query(default=None, description="Filtrar por papel: EXECUTIVE, FAMILY_CORE, etc."),
    company: Optional[str] = Query(default=None, description="Filtrar por empresa"),
    only_unknown: bool = Query(default=False, description="Listar apenas contatos não classificados"),
    interaction_period: Optional[str] = Query(
        default=None,
        description="Filtrar por período da última interação: 'today', '7d', '30d', 'all'",
    ),
    db: Session = Depends(get_db),
):
    """Lista contatos cadastrados com filtros opcionais (papel, empresa, período de interação)."""
    return contact_service.list_contacts(
        role=role,
        company=company,
        only_unknown=only_unknown,
        interaction_period=interaction_period,
        db=db,
    )


@router.get("/markdown-table", response_class=Response)
async def get_contacts_markdown_table(
    only_unknown: bool = Query(default=False, description="Gerar tabela apenas de contatos desconhecidos"),
    db: Session = Depends(get_db),
):
    """Retorna a lista de contatos em formato de Tabela Markdown (.md) para fácil cópia/edição no WhatsApp."""
    md_table = contact_service.export_markdown_table(only_unknown=only_unknown, db=db)
    return Response(content=md_table, media_type="text/markdown")


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create_or_update_contact(payload: ContactCreate, db: Session = Depends(get_db)):
    """Cadastra ou atualiza um contato manualmente."""
    return contact_service.create_or_update_contact(payload, db=db)


@router.post("/batch-import", response_model=ContactBatchImportResponse)
async def batch_import_contacts(payload: ContactBatchImportRequest, db: Session = Depends(get_db)):
    """Importa ou atualiza contatos em lote a partir de uma Tabela Markdown (.md) ou Array JSON (.json)."""
    return contact_service.import_batch_from_text(payload.content, db=db)


@router.patch("/{contact_id}", response_model=ContactResponse)
async def update_contact(contact_id: str, payload: ContactUpdate, db: Session = Depends(get_db)):
    """Atualiza dados específicos de um contato existente."""
    from src.memory.graph import knowledge_graph
    import re

    rec = db.query(ContactRecord).filter(
        (ContactRecord.id == contact_id)
        | (ContactRecord.name == contact_id)
        | (ContactRecord.phone_number == contact_id)
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Contato não encontrado")

    old_name = rec.name

    if payload.name is not None and payload.name.strip():
        rec.name = payload.name.strip()
    if payload.phone_number is not None:
        digits = re.sub(r"\D", "", payload.phone_number.strip())
        rec.phone_number = digits if len(digits) >= 8 else payload.phone_number.strip()
    if payload.nickname is not None:
        rec.nickname = payload.nickname.strip() if payload.nickname else None
    if payload.role is not None:
        rec.role = payload.role.value if hasattr(payload.role, "value") else str(payload.role)
    if payload.company is not None:
        rec.company = payload.company.strip() if payload.company else None
    if payload.projects is not None:
        rec.projects_json = payload.projects
    if payload.is_favorite is not None:
        rec.is_favorite = payload.is_favorite
    if payload.can_generate_tasks is not None:
        rec.can_generate_tasks = payload.can_generate_tasks
    if payload.custom_weight is not None:
        rec.custom_weight = payload.custom_weight
    if payload.notes is not None:
        rec.notes = payload.notes
    if payload.last_interaction_at is not None:
        rec.last_interaction_at = payload.last_interaction_at

    rec.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rec)

    # Se o nome mudou, remove o nó antigo do grafo
    if old_name and old_name != rec.name:
        try:
            knowledge_graph.remove_node(old_name)
        except Exception:
            pass

    contact_service._sync_contact_to_graph(rec)
    return record_to_response(rec)


@router.patch("/{contact_id}/favorite", response_model=ContactResponse)
async def toggle_favorite(contact_id: str, db: Session = Depends(get_db)):
    """Alterna o status de favorito de um contato (+10% de peso de prioridade)."""
    try:
        return contact_service.toggle_favorite(contact_id=contact_id, db=db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{contact_id}/toggle-tasks", response_model=ContactResponse)
async def toggle_tasks(contact_id: str, db: Session = Depends(get_db)):
    """Alterna se o contato pode gerar tarefas acionáveis no sistema."""
    try:
        return contact_service.toggle_can_generate_tasks(contact_id=contact_id, db=db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(contact_id: str, db: Session = Depends(get_db)):
    """Remove um contato cadastrado e purga todos os nós associados no Grafo de Conhecimento."""
    from src.memory.graph import knowledge_graph
    rec = db.query(ContactRecord).filter(
        (ContactRecord.id == contact_id)
        | (ContactRecord.name == contact_id)
        | (ContactRecord.phone_number == contact_id)
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Contato não encontrado")

    # Remove todos os nós no Grafo NetworkX
    names_to_remove = {rec.name, rec.nickname, rec.phone_number, rec.id}
    for n in names_to_remove:
        if n:
            knowledge_graph.remove_node(n)

    # Purga nós do grafo cuja string contenha o nome
    for node in knowledge_graph.list_nodes():
        node_name = node.get("name", "")
        if rec.name and rec.name.lower() in node_name.lower():
            knowledge_graph.remove_node(node_name)

    db.delete(rec)
    db.commit()
    return None


@router.get("/profile/{phone}")
@router.get("/avatar/{phone}")
async def get_contact_profile(phone: str, db: Session = Depends(get_db)):
    """Consulta foto de perfil e pushName do WhatsApp via Evolution API e persiste."""
    import re
    import httpx
    from src.config import settings

    digits = re.sub(r"\D", "", phone.strip())
    if not digits:
        return {"phone": phone, "name": None, "profile_picture_url": None}

    # Se não tem DDI (55), adiciona
    if len(digits) in (10, 11) and not digits.startswith("55"):
        digits = f"55{digits}"

    headers = {
        "apikey": settings.EVOLUTION_API_KEY,
        "Content-Type": "application/json",
    }

    from src.contacts.service import get_evolution_working_proxy, invalidate_evolution_proxy_cache

    picture_url = None
    push_name = None

    proxy = await get_evolution_working_proxy()
    try:
        async with httpx.AsyncClient(proxy=proxy, timeout=6.0) as client:
            # 1. Busca foto de perfil
            try:
                url_pic = f"{settings.EVOLUTION_API_URL.rstrip('/')}/chat/fetchProfilePictureUrl/{settings.EVOLUTION_INSTANCE}"
                res_pic = await client.post(url_pic, headers=headers, json={"number": digits})
                if res_pic.status_code == 200:
                    data_pic = res_pic.json()
                    picture_url = data_pic.get("profilePictureUrl") or data_pic.get("url")
            except Exception as e:
                invalidate_evolution_proxy_cache()
                logger.warning(f"Erro ao buscar foto na Evolution API para {digits}: {e}")

            # 2. Busca pushName do contato no WhatsApp
            try:
                url_contacts = f"{settings.EVOLUTION_API_URL.rstrip('/')}/chat/findContacts/{settings.EVOLUTION_INSTANCE}"
                res_contacts = await client.post(url_contacts, headers=headers, json={"where": {"remoteJid": f"{digits}@s.whatsapp.net"}})
                if res_contacts.status_code == 200:
                    data_contacts = res_contacts.json()
                    if isinstance(data_contacts, list) and len(data_contacts) > 0:
                        push_name = data_contacts[0].get("pushName")
                        if not picture_url:
                            picture_url = data_contacts[0].get("profilePicUrl")
            except Exception as e:
                invalidate_evolution_proxy_cache()
                logger.warning(f"Erro ao buscar pushName na Evolution API para {digits}: {e}")
    except Exception as ce:
        invalidate_evolution_proxy_cache()
        logger.warning(f"Falha de conexão com Evolution API ({settings.EVOLUTION_API_URL}): {ce}")

    # Atualiza banco SQL se encontrado
    try:
        rec = db.query(ContactRecord).filter(
            (ContactRecord.phone_number == digits) | (ContactRecord.phone_number == phone.strip())
        ).first()
        if rec:
            if picture_url:
                rec.avatar_url = picture_url
            if push_name and (rec.name.startswith("55") or rec.name.startswith("audio_") or rec.name == digits):
                rec.name = push_name
            db.commit()
    except Exception as e:
        logger.warning(f"Erro ao persistir perfil do WhatsApp para {digits}: {e}")

    return {
        "phone": digits,
        "name": push_name,
        "profile_picture_url": picture_url,
    }


@router.post("/import-vcard")
async def import_vcard_endpoint(
    request: Request,
    db: Session = Depends(get_db),
):
    """Importa contatos a partir de texto bruto ou diretório padrão da VPS."""
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        uploaded_file = form.get("file")
        if uploaded_file and hasattr(uploaded_file, "read"):
            content_bytes = await uploaded_file.read()
            vcard_text = content_bytes.decode("utf-8", errors="ignore")
            filename = getattr(uploaded_file, "filename", "upload.vcf")
            return contact_service.import_vcards_from_text(vcard_text, source_label=filename, db=db)

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    if payload and payload.get("content"):
        return contact_service.import_vcards_from_text(payload["content"], source_label="raw_text", db=db)

    dir_path = payload.get("directory", "data/vcards") if payload else "data/vcards"
    return contact_service.import_vcards_from_directory(dir_path=dir_path, db=db)


@router.post("/upload-vcard")
async def upload_vcard_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Faz upload de arquivo .vcf / .vcard e processa importação de contatos."""
    content_bytes = await file.read()
    vcard_text = content_bytes.decode("utf-8", errors="ignore")
    return contact_service.import_vcards_from_text(vcard_text, source_label=file.filename or "upload.vcf", db=db)



@router.post("/deduplicate")
async def deduplicate_contacts_endpoint(
    dry_run: bool = Query(default=False, description="Simula deduplicação sem aplicar alterações"),
    db: Session = Depends(get_db),
):
    """Executa deduplicação profunda, expurgo de contatos inválidos/grupos e mesclagem canônica."""
    if not dry_run:
        contact_service.deduplicate_and_merge_contacts(db=db)
    res = contact_service.deduplicate_contacts(dry_run=dry_run, db=db)
    return res


@router.post("/sync-avatars")
async def sync_avatars_endpoint(
    force_all: bool = Query(default=False, description="Força re-consulta mesmo para contatos com foto"),
    db: Session = Depends(get_db),
):
    """Varre a base de contatos e atualiza fotos de perfil e nomes públicos via Evolution API."""
    return await contact_service.sync_all_avatars_from_evolution(force_all=force_all, db=db)


@router.post("/pipeline")
async def run_contacts_pipeline_endpoint(
    payload: Optional[dict] = None,
    db: Session = Depends(get_db),
):
    """Executa a esteira completa: vCard + Deduplicação + Avatares WhatsApp + Grafo MUSA."""
    vcard_content = payload.get("content") if payload else None
    vcards_dir = payload.get("directory", "data/vcards") if payload else "data/vcards"
    return await contact_service.run_full_contacts_pipeline(vcard_content=vcard_content, vcards_dir=vcards_dir, db=db)


