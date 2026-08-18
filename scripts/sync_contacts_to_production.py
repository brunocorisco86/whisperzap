"""Script de Sincronização de Contatos do vCard para a API de Produção (VPS / Cloud / Tailscale).

Lê o arquivo data/vcards/contacts.vcf, processa através do parser resiliente
e envia em lotes para a API Hermes em produção (http://179.197.73.80:8005 ou customizada).
"""

import json
import logging
import os
import sys
import time
import urllib.request
import urllib.error
from typing import List, Dict, Any

# Adiciona raiz ao PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.contacts.parser import parse_vcard_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("prod_sync")


def sync_to_production(
    vcf_path: str = "data/vcards/contacts.vcf",
    api_url: str = "http://179.197.73.80:8005",
    batch_size: int = 100,
):
    """Envia todos os contatos do vCard para o servidor de produção em lotes."""
    if not os.path.exists(vcf_path):
        logger.error(f"Arquivo '{vcf_path}' não encontrado.")
        return

    logger.info(f"🚀 Iniciando Sincronização com o ambiente de PRODUÇÃO: {api_url}")
    logger.info(f"📖 Lendo '{vcf_path}'...")

    with open(vcf_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    contacts = parse_vcard_text(content)
    # Filtra apenas contatos com telefone
    contacts_with_phone = [c for c in contacts if c.phone_number]
    logger.info(f"📋 Total de contatos válidos com telefone: {len(contacts_with_phone)}")

    endpoint = f"{api_url.rstrip('/')}/api/v1/contacts/batch-import"
    total_imported = 0
    total_updated = 0
    total_errors = 0

    batches = [contacts_with_phone[i : i + batch_size] for i in range(0, len(contacts_with_phone), batch_size)]
    logger.info(f"📦 Dividido em {len(batches)} lotes de até {batch_size} contatos.")

    start_time = time.time()

    for idx, batch in enumerate(batches, 1):
        batch_payload = [
            {
                "name": c.name,
                "phone_number": c.phone_number,
                "nickname": c.nickname,
                "role": c.role.value if hasattr(c.role, "value") else str(c.role),
                "company": c.company,
                "notes": c.notes,
            }
            for c in batch
        ]

        data_json = json.dumps({"content": json.dumps(batch_payload)}).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data_json,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        success = False
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    res_body = json.loads(response.read().decode("utf-8"))
                    imp = res_body.get("imported_count", 0)
                    upd = res_body.get("updated_count", 0)
                    errs = len(res_body.get("errors", []))
                    total_imported += imp
                    total_updated += upd
                    total_errors += errs
                    logger.info(f"[{idx}/{len(batches)}] ✅ Lote enviado: +{imp} novos, {upd} atualizados")
                    success = True
                    break
            except Exception as e:
                logger.warning(f"[{idx}/{len(batches)}] Tentativa {attempt + 1}/3 falhou: {e}. Aguardando 2s...")
                time.sleep(2)

        if not success:
            logger.error(f"[{idx}/{len(batches)}] ❌ Falha definitiva no lote {idx}.")

    elapsed = round(time.time() - start_time, 2)
    logger.info("=" * 60)
    logger.info(f"🎉 Sincronização com Produção finalizada em {elapsed}s!")
    logger.info(f"✨ Novos contatos em Produção:      {total_imported}")
    logger.info(f"🔄 Contatos atualizados em Produção: {total_updated}")
    if total_errors:
        logger.info(f"⚠️ Erros reportados:                 {total_errors}")
    logger.info("=" * 60)


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://179.197.73.80:8005"
    file_p = sys.argv[2] if len(sys.argv) > 2 else "data/vcards/contacts.vcf"
    sync_to_production(vcf_path=file_p, api_url=url)
