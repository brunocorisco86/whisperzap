"""Script para sincronizar nós de pessoas do Grafo para a tabela SQL de Contatos."""

import sys
from src.contacts.service import contact_service
from src.contacts.schemas import ContactCreate, ContactRole
from src.memory.database import SessionLocal, init_db
from src.memory.graph import knowledge_graph

def seed_contacts():
    init_db()
    db = SessionLocal()
    try:
        nodes = knowledge_graph.list_nodes(category="PERSON")
        print(f"Encontrados {len(nodes)} nós de pessoas no Grafo.")
        
        for n in nodes:
            name = n.get("name")
            if not name or name.lower() in ("user", "5544999990001", "5544999990002"):
                continue
                
            phone = n.get("phone") or "5544900000000"
            role_str = n.get("role") or "UNKNOWN"
            company = n.get("company")
            weight = n.get("weight")
            details = n.get("details")
            
            try:
                role_enum = ContactRole(role_str)
            except ValueError:
                role_enum = ContactRole.UNKNOWN
                
            contact_data = ContactCreate(
                name=name,
                phone_number=phone,
                role=role_enum,
                company=company,
                custom_weight=weight,
                notes=details
            )
            saved = contact_service.create_or_update_contact(contact_data, db=db)
            print(f"✅ Contato sincronizado: {saved.name} ({saved.role.value}) - {saved.phone_number}")
            
    finally:
        db.close()

if __name__ == "__main__":
    seed_contacts()
