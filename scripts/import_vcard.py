"""Script Ultra-Resiliente para Importação de Contatos vCard (.vcf / .vcard).

Lê arquivos .vcf exportados do Google Contacts, Apple iCloud ou Android,
faz a sanitização profunda, deduplicação e normalização telefônica (regras Brasil + E.164 internacional),
e sincroniza os contatos em lote (bulk) no Banco SQLite e no Grafo de Conhecimento.
"""

import glob
import logging
import os
import sys
import time
from typing import List

# Garante inclusão do diretório raiz no PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.contacts.models import ContactRecord
from src.contacts.parser import parse_vcard_text
from src.contacts.schemas import ContactCreate, ContactRole
from src.contacts.service import contact_service, generate_contact_id
from src.memory.database import SessionLocal, init_db
from src.memory.graph import knowledge_graph

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("vcard_importer")


def import_vcards_from_directory(dir_path: str = "data/vcards"):
    """Lê todos os arquivos .vcf na pasta especificada e importa para o banco e grafo."""
    init_db()
    db = SessionLocal()

    vcf_files = sorted(glob.glob(os.path.join(dir_path, "*.vcf")) + glob.glob(os.path.join(dir_path, "*.vcard")))

    if not vcf_files:
        logger.warning(f"⚠️ Nenhum arquivo .vcf ou .vcard encontrado em '{dir_path}'.")
        logger.info(f"📁 Coloque seus arquivos em: {os.path.abspath(dir_path)}/ e execute novamente.")
        return

    logger.info(f"📂 Encontrado(s) {len(vcf_files)} arquivo(s) vCard para processamento.")

    start_time = time.time()
    total_parsed = 0
    total_inserted = 0
    total_updated = 0
    skipped_no_phone = 0

    try:
        # Carrega mapa de contatos existentes por telefone e por ID para lookup O(1)
        existing_by_phone = {c.phone_number: c for c in db.query(ContactRecord).filter(ContactRecord.phone_number.isnot(None)).all() if c.phone_number}
        existing_by_id = {c.id: c for c in db.query(ContactRecord).all()}

        for file_path in vcf_files:
            file_size_kb = round(os.path.getsize(file_path) / 1024, 1)
            logger.info(f"🔍 Lendo '{os.path.basename(file_path)}' ({file_size_kb} KB)...")

            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            contacts_list = parse_vcard_text(content)
            total_parsed += len(contacts_list)
            logger.info(f"📋 Encontrados {len(contacts_list)} registros válidos no arquivo.")

            batch_records_to_add: List[ContactRecord] = []
            
            for item in contacts_list:
                phone = (item.phone_number or "").strip()
                name = (item.name or "").strip()

                if not phone:
                    # Contato sem telefone: adiciona apenas ao Grafo se tiver nome relevante
                    if name and len(name) > 1:
                        knowledge_graph.add_node(name, category="PERSON", details=item.notes or "Contato Google (sem tel)")
                        skipped_no_phone += 1
                    continue

                c_id = generate_contact_id(name, phone)
                if not c_id:
                    continue

                # Verifica se já existe por telefone ou id
                existing = existing_by_phone.get(phone) or existing_by_id.get(c_id)

                if existing:
                    # Atualiza nome se o existente for genérico/numérico ou se o novo for mais completo
                    if existing.name.isdigit() or (len(name) > len(existing.name) and not existing.name.startswith("wa_")):
                        existing.name = name
                    if item.company and not existing.company:
                        existing.company = item.company
                    if item.nickname and not existing.nickname:
                        existing.nickname = item.nickname
                    if item.notes and "Importado" not in (existing.notes or ""):
                        existing.notes = f"{existing.notes} | {item.notes}" if existing.notes else item.notes
                    
                    # Adiciona ao grafo sem IO de disco por item
                    knowledge_graph.graph.add_node(
                        existing.name,
                        category="PERSON",
                        role=existing.role,
                        phone=existing.phone_number,
                        company=existing.company,
                    )
                    total_updated += 1
                else:
                    new_rec = ContactRecord(
                        id=c_id,
                        name=name,
                        phone_number=phone,
                        nickname=item.nickname,
                        role=item.role.value if hasattr(item.role, "value") else str(item.role),
                        company=item.company,
                        projects_json=item.projects or [],
                        notes=item.notes or "Importado via Google vCard",
                    )
                    db.add(new_rec)
                    existing_by_phone[phone] = new_rec
                    existing_by_id[c_id] = new_rec
                    
                    # Adiciona ao grafo sem IO de disco por item
                    knowledge_graph.graph.add_node(
                        new_rec.name,
                        category="PERSON",
                        role=new_rec.role,
                        phone=new_rec.phone_number,
                        company=new_rec.company,
                    )
                    total_inserted += 1

            db.commit()

        # Salva o estado do grafo no disco uma única vez no final
        knowledge_graph._save()
        elapsed = round(time.time() - start_time, 2)

        logger.info("=" * 60)
        logger.info(f"🎉 Importação de vCards concluída em {elapsed}s!")
        logger.info(f"📊 Registros parseados:      {total_parsed}")
        logger.info(f"✨ Novos contatos inseridos: {total_inserted}")
        logger.info(f"🔄 Contatos atualizados:     {total_updated}")
        logger.info(f"👥 Entidades sem telefone:   {skipped_no_phone}")
        logger.info(f"🗂️ Total de contatos na base: {db.query(ContactRecord).count()}")
        logger.info("=" * 60)

    except Exception as e:
        db.rollback()
        logger.error(f"❌ Falha durante a importação: {e}", exc_info=True)
    finally:
        db.close()


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "data/vcards"
    import_vcards_from_directory(target)
