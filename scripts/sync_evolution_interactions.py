"""Script de Sincronização Inicial Pesada (Backfill) das Últimas Interações da Evolution API para o Hermes.

1. Extrai chats e contatos únicos da Evolution API (Raspberry Pi / Local).
2. Mapeia a data/hora da última mensagem (updatedAt / messageTimestamp) e foto de perfil.
3. Atualiza a coluna 'last_interaction_at' no Banco SQL de Produção (VPS) e Local.
"""

import json
import logging
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from typing import Dict, Any, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.memory.database import SessionLocal, init_db, engine
from src.contacts.models import ContactRecord
from src.ai_gateway.bypass import is_valid_contact_phone
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("evolution_sync")


def ensure_column_exists():
    """Garante que a coluna last_interaction_at existe na tabela contacts."""
    is_sqlite = str(engine.url).startswith("sqlite")
    stmt = (
        "ALTER TABLE contacts ADD COLUMN last_interaction_at TIMESTAMP"
        if is_sqlite
        else "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS last_interaction_at TIMESTAMP WITH TIME ZONE"
    )
    try:
        with engine.begin() as conn:
            conn.execute(text(stmt))
    except Exception:
        pass


def parse_iso_datetime(dt_str: str) -> datetime:
    """Converte string ISO 8601 da Evolution API para objeto datetime em UTC."""
    if not dt_str:
        return datetime.now(timezone.utc)
    try:
        # Trata formato Z ou offsets
        clean = dt_str.replace("Z", "+00:00")
        return datetime.fromisoformat(clean)
    except Exception:
        return datetime.now(timezone.utc)


def sync_evolution_interactions(
    evolution_url: str = "http://100.74.64.89:8080",
    evolution_token: str = "8c114ae397eb273edfe82e05728be8b4e17cc25649d7e26df40c438c67c368b0",
    instance_name: str = "hermes",
    vps_api_url: str = "http://179.197.73.80:8005",
):
    """Executa a sincronização pesada inicial dos chats da Evolution para a VPS/Local."""
    logger.info("=" * 65)
    logger.info("🚀 Sincronização Inicial de Interações da Evolution API para o Hermes")
    logger.info(f"📡 Evolution Host: {evolution_url} (Instância: {instance_name})")
    logger.info(f"🌐 VPS API Host:   {vps_api_url}")
    logger.info("=" * 65)

    # 1. Busca todos os chats na Evolution API
    chats_url = f"{evolution_url.rstrip('/')}/chat/findChats/{instance_name}"
    req = urllib.request.Request(
        chats_url,
        data=b'{"where":{}}',
        headers={"apikey": evolution_token, "Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            chats_data = json.load(resp)
    except Exception as e:
        logger.error(f"❌ Falha ao consultar Evolution API em '{chats_url}': {e}")
        return

    logger.info(f"📥 Recebidos {len(chats_data)} registros de chat da Evolution.")

    # 2. Processa e mapeia contatos válidos e timestamp mais recente
    contact_interactions: Dict[str, Dict[str, Any]] = {}
    for c in chats_data:
        remote_jid = str(c.get("remoteJid") or c.get("id") or "")
        # Ignora grupos, newsletters e canais de transmissão
        if "@g.us" in remote_jid or "@broadcast" in remote_jid or "@newsletter" in remote_jid or "@lid" in remote_jid:
            continue

        digits = re.sub(r"\D", "", remote_jid.split("@")[0])
        if not (10 <= len(digits) <= 15):
            continue

        raw_updated = c.get("updatedAt") or c.get("createdAt")
        dt_val = parse_iso_datetime(raw_updated)
        push_name = c.get("pushName")

        if digits not in contact_interactions or dt_val > contact_interactions[digits]["last_interaction_at"]:
            contact_interactions[digits] = {
                "phone": digits,
                "remote_jid": remote_jid,
                "push_name": push_name,
                "last_interaction_at": dt_val,
                "iso_interaction": dt_val.isoformat(),
            }

    logger.info(f"🎯 Mapeados {len(contact_interactions)} contatos únicos com histórico de interação.")

    # 3. Atualiza no Banco de Dados Local / SQL
    init_db()
    ensure_column_exists()
    db = SessionLocal()

    local_updated = 0
    try:
        all_contacts = db.query(ContactRecord).all()
        by_phone = {c.phone_number: c for c in all_contacts if c.phone_number}
        by_suffix = {c.phone_number[-8:]: c for c in all_contacts if c.phone_number and len(c.phone_number) >= 8}

        for phone_digits, data in contact_interactions.items():
            match = by_phone.get(phone_digits) or by_suffix.get(phone_digits[-8:])
            if match:
                match.last_interaction_at = data["last_interaction_at"]
                local_updated += 1

        db.commit()
        logger.info(f"💾 Banco Local: {local_updated} contatos atualizados com a data da última interação.")
    finally:
        db.close()

    # 4. Atualiza na VPS via API REST em lotes (sem necessidade de porta de banco aberta)
    vps_updated = 0
    if vps_api_url:
        logger.info(f"📡 Atualizando contatos na VPS ({vps_api_url})...")
        vps_patch_url = f"{vps_api_url.rstrip('/')}/api/v1/contacts"

        for phone_digits, data in contact_interactions.items():
            c_id = f"wa_{phone_digits}"
            patch_payload = {
                "last_interaction_at": data["iso_interaction"],
            }
            if data["push_name"]:
                patch_payload["nickname"] = data["push_name"]

            req_patch = urllib.request.Request(
                f"{vps_patch_url}/{c_id}",
                data=json.dumps(patch_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="PATCH",
            )
            try:
                with urllib.request.urlopen(req_patch, timeout=5) as r:
                    if r.status in (200, 201):
                        vps_updated += 1
            except Exception:
                # Tenta match por telefone
                try:
                    req_patch_phone = urllib.request.Request(
                        f"{vps_patch_url}/{phone_digits}",
                        data=json.dumps(patch_payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="PATCH",
                    )
                    with urllib.request.urlopen(req_patch_phone, timeout=5) as r:
                        if r.status in (200, 201):
                            vps_updated += 1
                except Exception:
                    pass

        logger.info(f"🌐 VPS Produção: {vps_updated} contatos sincronizados com 'last_interaction_at'!")

    logger.info("=" * 65)
    logger.info("🎉 Sincronização de Interações Concluída com Sucesso!")
    logger.info("=" * 65)


if __name__ == "__main__":
    evo_url = sys.argv[1] if len(sys.argv) > 1 else "http://100.74.64.89:8080"
    vps_url = sys.argv[2] if len(sys.argv) > 2 else "http://179.197.73.80:8005"
    sync_evolution_interactions(evolution_url=evo_url, vps_api_url=vps_url)
