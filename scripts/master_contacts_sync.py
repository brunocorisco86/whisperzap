"""Sincronizador Mestre de Contatos: Google Contacts (vCard) + WhatsApp Evolution API (PostgreSQL/Raspberry).

1. Lê e faz o parse de todos os contatos do Google (data/vcards/contacts.vcf).
2. Extrai os 1.952 contatos do WhatsApp, fotos de perfil (profilePicUrl), pushNames e timestamps
   diretamente do banco PostgreSQL da Evolution API na Raspberry Pi.
3. Funde os dados por número E.164 (dando preferência para nomes oficiais da sua agenda + fotos do WhatsApp + data de interação).
4. Envia a base consolidada para a VPS de Produção (100.106.3.81:8005) e grava no Banco Local.
"""

import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from typing import Dict, Any, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.contacts.parser import parse_vcard_text
from src.ai_gateway.bypass import is_valid_contact_phone, normalize_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("master_sync")


def normalize_phone_digits(raw: str) -> str:
    """Normaliza para formato numérico limpo com DDD/DDI."""
    if not raw:
        return ""
    digits = re.sub(r"\D", "", str(raw).split("@")[0])
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0") and len(digits) in (13, 14):
        digits = digits[3:]
    elif digits.startswith("0") and len(digits) in (11, 12):
        digits = digits[1:]
    if len(digits) in (10, 11) and not digits.startswith("55"):
        digits = f"55{digits}"
    return digits


def fetch_evolution_contacts_from_api(
    evo_url: str = "http://100.74.64.89:8080",
    evo_token: str = "8c114ae397eb273edfe82e05728be8b4e17cc25649d7e26df40c438c67c368b0",
    instance: str = "hermes",
) -> List[Dict[str, Any]]:
    """Extrai os contatos, fotos de perfil (profilePicUrl) e chats via Evolution API."""
    logger.info(f"📡 Conectando à Evolution API ({evo_url})...")
    
    headers = {"apikey": evo_token, "Content-Type": "application/json"}
    
    # 1. Busca contatos
    contacts_url = f"{evo_url.rstrip('/')}/chat/findContacts/{instance}"
    req_contacts = urllib.request.Request(contacts_url, data=b'{"where":{}}', headers=headers, method="POST")
    
    contacts_list = []
    try:
        with urllib.request.urlopen(req_contacts, timeout=20) as resp:
            contacts_list = json.load(resp)
        logger.info(f"📥 Recebidos {len(contacts_list)} contatos da Evolution API.")
    except Exception as e:
        logger.error(f"Erro ao buscar contatos da Evolution: {e}")

    # 2. Busca chats para timestamps de última interação
    chats_url = f"{evo_url.rstrip('/')}/chat/findChats/{instance}"
    req_chats = urllib.request.Request(chats_url, data=b'{"where":{}}', headers=headers, method="POST")
    
    chats_map = {}
    try:
        with urllib.request.urlopen(req_chats, timeout=20) as resp:
            chats_list = json.load(resp)
            for ch in chats_list:
                r_jid = ch.get("remoteJid") or ch.get("id")
                if r_jid:
                    chats_map[r_jid] = ch.get("updatedAt") or ch.get("createdAt")
        logger.info(f"📥 Recebidos {len(chats_map)} chats ativos com timestamp de interação.")
    except Exception as e:
        logger.warning(f"Aviso ao buscar chats da Evolution: {e}")

    results = []
    for c in contacts_list:
        r_jid = str(c.get("remoteJid") or c.get("id") or "")
        if "@g.us" in r_jid or "@broadcast" in r_jid or "@newsletter" in r_jid or "@lid" in r_jid:
            continue
        
        chat_ts = chats_map.get(r_jid) or c.get("updatedAt") or c.get("createdAt")
        results.append({
            "remoteJid": r_jid,
            "pushName": c.get("pushName"),
            "profilePicUrl": c.get("profilePicUrl"),
            "last_interaction": chat_ts,
        })

    logger.info(f"🎯 Extraídos {len(results)} contatos privados válidos do WhatsApp.")
    return results


def run_master_sync(
    vcf_path: str = "data/vcards/contacts.vcf",
    pi_ip: str = "100.74.64.89",
    vps_api_url: str = "http://100.106.3.81:8005",
):
    logger.info("=" * 65)
    logger.info("🚀 Sincronizador Mestre: Google Contacts + WhatsApp Evolution")
    logger.info("=" * 65)

    # 1. Carrega contatos do Google vCard
    google_contacts_map: Dict[str, Dict[str, Any]] = {}
    if os.path.exists(vcf_path):
        with open(vcf_path, "r", encoding="utf-8", errors="ignore") as f:
            vcf_content = f.read()
        parsed_google = parse_vcard_text(vcf_content)
        for c in parsed_google:
            digits = normalize_phone_digits(c.phone_number)
            if digits and len(digits) >= 8:
                google_contacts_map[digits] = {
                    "name": c.name,
                    "phone_number": digits,
                    "company": c.company,
                    "nickname": c.nickname,
                    "notes": c.notes,
                    "role": c.role.value if hasattr(c.role, "value") else str(c.role),
                }
        logger.info(f"📖 Google Contacts: {len(google_contacts_map)} contatos com telefone mapeados.")

    # 2. Carrega contatos da Evolution API (Raspberry Pi)
    evolution_contacts = fetch_evolution_contacts_from_api(f"http://{pi_ip}:8080")
    
    # 3. Faz o Merge Inteligente
    master_contacts: Dict[str, Dict[str, Any]] = {}

    # Insere contatos do Google como base oficial
    for digits, g_contact in google_contacts_map.items():
        master_contacts[digits] = {
            "name": g_contact["name"],
            "phone_number": digits,
            "company": g_contact["company"],
            "nickname": g_contact["nickname"],
            "notes": g_contact["notes"],
            "role": g_contact["role"],
            "avatar_url": None,
            "last_interaction_at": None,
        }

    # Enriquece ou adiciona novos contatos vindos do WhatsApp (Evolution)
    added_from_whatsapp = 0
    enriched_from_whatsapp = 0

    for evo in evolution_contacts:
        digits = normalize_phone_digits(evo["remoteJid"])
        if not digits or len(digits) < 10 or len(digits) > 15:
            continue

        raw_last = evo.get("last_interaction")
        last_dt_iso = None
        if raw_last:
            try:
                clean_ts = str(raw_last).replace(" ", "T")
                if not clean_ts.endswith("Z") and "+" not in clean_ts:
                    clean_ts += "+00:00"
                last_dt_iso = datetime.fromisoformat(clean_ts.replace("Z", "+00:00")).isoformat()
            except Exception:
                pass

        if digits in master_contacts:
            # Já existe no Google: enriquece com foto, apelido e última interação
            if evo.get("profilePicUrl"):
                master_contacts[digits]["avatar_url"] = evo["profilePicUrl"]
            if evo.get("pushName") and not master_contacts[digits]["nickname"]:
                master_contacts[digits]["nickname"] = evo["pushName"]
            if last_dt_iso:
                master_contacts[digits]["last_interaction_at"] = last_dt_iso
            enriched_from_whatsapp += 1
        else:
            # Novo contato que estava só no WhatsApp
            name = evo["pushName"] or digits
            master_contacts[digits] = {
                "name": name,
                "phone_number": digits,
                "company": None,
                "nickname": evo["pushName"],
                "notes": "Contato identificado via WhatsApp",
                "role": "UNKNOWN",
                "avatar_url": evo["profilePicUrl"],
                "last_interaction_at": last_dt_iso,
            }
            added_from_whatsapp += 1

    logger.info(f"✨ Total Mestre Consolidado: {len(master_contacts)} contatos únicos.")
    logger.info(f"📸 Contatos enriquecidos com fotos/apelidos do WhatsApp: {enriched_from_whatsapp}")
    logger.info(f"➕ Novos contatos adicionados exclusivamente do WhatsApp: {added_from_whatsapp}")

    # 4. Envia para a VPS de Produção em lotes de 100
    endpoint = f"{vps_api_url.rstrip('/')}/api/v1/contacts/batch-import"
    all_items = list(master_contacts.values())
    batch_size = 100
    batches = [all_items[i : i + batch_size] for i in range(0, len(all_items), batch_size)]

    logger.info(f"🌐 Enviando {len(all_items)} contatos para a VPS em {len(batches)} lotes...")
    start_time = time.time()

    total_imp = 0
    total_upd = 0

    for idx, batch in enumerate(batches, 1):
        payload_data = {"content": json.dumps(batch)}
        data_json = json.dumps(payload_data).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data_json,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = json.loads(r.read().decode("utf-8"))
                imp = body.get("imported_count", 0)
                upd = body.get("updated_count", 0)
                total_imp += imp
                total_upd += upd
                logger.info(f"[{idx}/{len(batches)}] ✅ Lote: +{imp} novos, {upd} atualizados")
        except Exception as e:
            logger.error(f"[{idx}/{len(batches)}] ❌ Falha no lote: {e}")

    elapsed = round(time.time() - start_time, 2)
    logger.info("=" * 65)
    logger.info(f"🎉 Sincronização Mestre Concluída em {elapsed}s!")
    logger.info(f"✨ Novos contatos inseridos na VPS: {total_imp}")
    logger.info(f"🔄 Contatos atualizados na VPS:     {total_upd}")
    logger.info(f"👥 Total de contatos na VPS:        {len(all_items)}")
    logger.info("=" * 65)


if __name__ == "__main__":
    v_url = sys.argv[1] if len(sys.argv) > 1 else "http://100.106.3.81:8005"
    run_master_sync(vps_api_url=v_url)
