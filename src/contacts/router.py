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

    picture_url = None
    push_name = None

    async with httpx.AsyncClient(timeout=8.0) as client:
        # 1. Busca foto de perfil
        try:
            url_pic = f"{settings.EVOLUTION_API_URL.rstrip('/')}/chat/fetchProfilePictureUrl/{settings.EVOLUTION_INSTANCE}"
            res_pic = await client.post(url_pic, headers=headers, json={"number": digits})
            if res_pic.status_code == 200:
                data_pic = res_pic.json()
                picture_url = data_pic.get("profilePictureUrl") or data_pic.get("url")
        except Exception as e:
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
            logger.warning(f"Erro ao buscar pushName na Evolution API para {digits}: {e}")

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

