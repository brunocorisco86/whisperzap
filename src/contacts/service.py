"""Serviço de Gestão de Contatos, Ponderação de Prioridade e Integração com Grafo."""

import logging
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4
from sqlalchemy.orm import Session
from src.contacts.models import ContactRecord
from src.contacts.parser import contacts_to_markdown_table, parse_contact_batch
from src.contacts.schemas import (
    ROLE_WEIGHTS,
    ContactBatchImportResponse,
    ContactCreate,
    ContactResponse,
    ContactRole,
    ContactUpdate,
)
from src.memory.database import SessionLocal
from src.memory.graph import knowledge_graph

logger = logging.getLogger(__name__)


def calculate_effective_weight(contact: ContactRecord | ContactCreate) -> float:
    """Calcula o peso de prioridade efetivo (0.0 a 1.0) para o contato."""
    if getattr(contact, "custom_weight", None) is not None:
        return float(contact.custom_weight)

    role_str = getattr(contact, "role", "UNKNOWN")
    try:
        role_enum = ContactRole(role_str) if isinstance(role_str, str) else role_str
        return ROLE_WEIGHTS.get(role_enum, 0.40)
    except ValueError:
        return 0.40


def record_to_response(rec: ContactRecord) -> ContactResponse:
    """Converte ContactRecord para ContactResponse enriquecido."""
    role_val = ContactRole(rec.role) if rec.role in ContactRole._value2member_map_ else ContactRole.UNKNOWN
    return ContactResponse(
        id=rec.id,
        phone_number=rec.phone_number,
        name=rec.name,
        nickname=rec.nickname,
        role=role_val,
        company=rec.company,
        projects=rec.projects_json or [],
        custom_weight=rec.custom_weight,
        notes=rec.notes,
        effective_weight=calculate_effective_weight(rec),
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


class ContactService:
    """Serviço unificado de gestão de contatos e motor de priorização."""

    def list_contacts(
        self,
        role: Optional[str] = None,
        company: Optional[str] = None,
        only_unknown: bool = False,
        db: Session | None = None,
    ) -> list[ContactResponse]:
        """Lista contatos com filtros opcionais."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            query = db.query(ContactRecord)
            if only_unknown:
                query = query.filter(ContactRecord.role == "UNKNOWN")
            elif role:
                query = query.filter(ContactRecord.role == role.upper())

            if company:
                query = query.filter(ContactRecord.company.ilike(f"%{company}%"))

            records = query.order_by(ContactRecord.name.asc()).all()
            return [record_to_response(r) for r in records]
        finally:
            if should_close:
                db.close()

    def get_contact_by_phone(self, phone: str, db: Session | None = None) -> ContactRecord | None:
        """Busca contato por número de telefone."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            import re
            digits = re.sub(r"\D", "", phone.strip())
            return db.query(ContactRecord).filter(
                (ContactRecord.phone_number == digits) | (ContactRecord.phone_number == phone.strip())
            ).first()
        finally:
            if should_close:
                db.close()

    def get_contact_by_name(self, name: str, db: Session | None = None) -> ContactRecord | None:
        """Busca contato por nome ou apelido."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            name_clean = name.strip()
            return db.query(ContactRecord).filter(
                (ContactRecord.name.ilike(f"%{name_clean}%")) | (ContactRecord.nickname.ilike(f"%{name_clean}%"))
            ).first()
        finally:
            if should_close:
                db.close()

    def create_or_update_contact(self, data: ContactCreate, db: Session | None = None) -> ContactResponse:
        """Cria ou atualiza um contato e sincroniza com o Grafo de Conhecimento."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            existing = self.get_contact_by_phone(data.phone_number, db=db)
            if existing:
                existing.name = data.name
                if data.nickname:
                    existing.nickname = data.nickname
                existing.role = data.role.value if isinstance(data.role, ContactRole) else str(data.role)
                if data.company is not None:
                    existing.company = data.company
                if data.projects:
                    existing.projects_json = data.projects
                if data.custom_weight is not None:
                    existing.custom_weight = data.custom_weight
                if data.notes:
                    existing.notes = data.notes
                existing.updated_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(existing)
                rec = existing
            else:
                contact_id = str(uuid4())
                rec = ContactRecord(
                    id=contact_id,
                    phone_number=data.phone_number,
                    name=data.name,
                    nickname=data.nickname,
                    role=data.role.value if isinstance(data.role, ContactRole) else str(data.role),
                    company=data.company,
                    projects_json=data.projects,
                    custom_weight=data.custom_weight,
                    notes=data.notes,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                db.add(rec)
                db.commit()
                db.refresh(rec)

            # Sincroniza nó no Grafo NetworkX
            self._sync_contact_to_graph(rec)

            return record_to_response(rec)
        finally:
            if should_close:
                db.close()

    def _sync_contact_to_graph(self, contact: ContactRecord) -> None:
        """Cria/atualiza conexões ricas no Grafo NetworkX para o contato."""
        try:
            knowledge_graph.add_node(
                contact.name,
                category="PERSON",
                role=contact.role,
                phone=contact.phone_number,
                company=contact.company,
                weight=calculate_effective_weight(contact),
            )

            if contact.company:
                knowledge_graph.add_node(contact.company, category="LOCATION")
                knowledge_graph.add_edge(contact.name, contact.company, relation=f"AFFILIATED_AS_{contact.role}")

            if contact.projects_json:
                for proj in contact.projects_json:
                    knowledge_graph.add_node(proj, category="PROJECT")
                    knowledge_graph.add_edge(contact.name, proj, relation="WORKS_ON")
        except Exception as e:
            logger.warning(f"Erro ao sincronizar contato {contact.name} com o grafo: {e}")

    def import_batch_from_text(self, raw_text: str, db: Session | None = None) -> ContactBatchImportResponse:
        """Importa contatos em lote a partir de uma Tabela Markdown (.md) ou Array JSON (.json)."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            parsed_items = parse_contact_batch(raw_text)
            imported = 0
            updated = 0
            errors = []
            results: list[ContactResponse] = []

            for item in parsed_items:
                try:
                    existing = self.get_contact_by_phone(item.phone_number, db=db)
                    is_update = existing is not None
                    saved = self.create_or_update_contact(item, db=db)
                    results.append(saved)
                    if is_update:
                        updated += 1
                    else:
                        imported += 1
                except Exception as e:
                    errors.append(f"Erro no contato {item.name} ({item.phone_number}): {str(e)}")

            return ContactBatchImportResponse(
                imported_count=imported,
                updated_count=updated,
                errors=errors,
                contacts=results,
            )
        finally:
            if should_close:
                db.close()

    def export_markdown_table(self, only_unknown: bool = False, db: Session | None = None) -> str:
        """Exporta lista de contatos em formato de Tabela Markdown (.md)."""
        contacts = self.list_contacts(only_unknown=only_unknown, db=db)
        return contacts_to_markdown_table(contacts)

    def calculate_priority_for_message(
        self,
        sender_phone_or_name: str,
        raw_urgency: str = "MEDIUM",
        db: Session | None = None,
    ) -> Literal["LOW", "MEDIUM", "HIGH", "URGENT"]:
        """Calcula a prioridade final ponderando o papel hierárquico do remetente."""
        contact = self.get_contact_by_phone(sender_phone_or_name, db=db)
        if not contact:
            contact = self.get_contact_by_name(sender_phone_or_name, db=db)

        # Peso do contato (0.40 a 1.00)
        contact_weight = calculate_effective_weight(contact) if contact else 0.40

        # Peso base da urgência inferida pela IA
        raw_urgency_weights = {
            "URGENT": 1.0,
            "HIGH": 0.80,
            "MEDIUM": 0.50,
            "LOW": 0.20,
        }
        urgency_weight = raw_urgency_weights.get(raw_urgency.upper(), 0.50)

        # Score combinado
        # Ex: Executive (1.0) + Medium (0.50) -> Score ~ 0.75 -> HIGH!
        # Ex: Executive (1.0) + High (0.80) -> Score ~ 0.90 -> URGENT!
        # Ex: Unknown (0.40) + High (0.80) -> Score ~ 0.60 -> MEDIUM
        combined_score = (contact_weight * 0.6) + (urgency_weight * 0.4)

        if combined_score >= 0.85:
            return "URGENT"
        elif combined_score >= 0.65:
            return "HIGH"
        elif combined_score >= 0.40:
            return "MEDIUM"
        else:
            return "LOW"


contact_service = ContactService()
