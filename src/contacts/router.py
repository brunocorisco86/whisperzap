import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

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
    db: Session = Depends(get_db),
):
    """Lista contatos cadastrados com filtros opcionais."""
    return contact_service.list_contacts(role=role, company=company, only_unknown=only_unknown, db=db)


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
    """Atualiza dados específicos de um contato."""
    rec = db.query(ContactRecord).filter(ContactRecord.id == contact_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Contato não encontrado")

    if payload.name is not None:
        rec.name = payload.name
    if payload.nickname is not None:
        rec.nickname = payload.nickname
    if payload.role is not None:
        rec.role = payload.role.value
    if payload.company is not None:
        rec.company = payload.company
    if payload.projects is not None:
        rec.projects_json = payload.projects
    if payload.custom_weight is not None:
        rec.custom_weight = payload.custom_weight
    if payload.notes is not None:
        rec.notes = payload.notes

    db.commit()
    db.refresh(rec)
    contact_service._sync_contact_to_graph(rec)
    return record_to_response(rec)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(contact_id: str, db: Session = Depends(get_db)):
    """Remove um contato cadastrado."""
    from src.memory.graph import knowledge_graph
    rec = db.query(ContactRecord).filter(
        (ContactRecord.id == contact_id)
        | (ContactRecord.name == contact_id)
        | (ContactRecord.phone_number == contact_id)
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Contato não encontrado")

    knowledge_graph.remove_node(rec.name)
    db.delete(rec)
    db.commit()
    return None


@router.get("/avatar/{phone}")
async def get_contact_avatar(phone: str):
    """Consulta a foto de perfil do WhatsApp via Evolution API."""
    import re
    import httpx
    from src.config import settings

    digits = re.sub(r"\D", "", phone.strip())
    if not digits:
        return {"phone": phone, "profile_picture_url": None}

    # Se não tem DDI (55), adiciona
    if len(digits) in (10, 11) and not digits.startswith("55"):
        digits = f"55{digits}"

    url = f"{settings.EVOLUTION_API_URL.rstrip('/')}/chat/fetchProfilePictureUrl/{settings.EVOLUTION_INSTANCE}"
    headers = {
        "apikey": settings.EVOLUTION_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {"number": digits}

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            res = await client.post(url, headers=headers, json=payload)
            if res.status_code == 200:
                data = res.json()
                picture_url = data.get("profilePictureUrl") or data.get("url")
                return {"phone": digits, "profile_picture_url": picture_url}
    except Exception as e:
        logger.warning(f"Erro ao buscar foto na Evolution API para {digits}: {e}")

    return {"phone": digits, "profile_picture_url": None}

