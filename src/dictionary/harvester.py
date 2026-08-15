"""Agente Pescador Léxico (Active Learning / Self-Improving Lexicon) para o Hermes.

Varre o buffer de termos não compreendidos/ambíguos capturados ao longo do dia,
analisa seu valor com LLM especialista no domínio (Avicultura, C.Vale, TMS, Mtech)
e promove termos técnicos e variações fonéticas para o Dicionário Oficial.
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from src.ai_gateway.prompts import HARVESTER_SYSTEM_PROMPT, HARVESTER_USER_TEMPLATE
from src.ai_gateway.providers import get_ai_provider
from src.dictionary.schemas import DictionaryTermCreate
from src.dictionary.service import dictionary_service
from src.memory.database import SessionLocal
from src.memory.models import LexicalCandidateRecord, LexicalHarvestResult

logger = logging.getLogger(__name__)


class LexicalHarvester:
    """Agente Especialista em Pesca e Aprendizado de Termos Léxicos."""

    def __init__(self):
        self.provider = get_ai_provider(task="extract")

    def _extract_json_array(self, text: str) -> list[dict]:
        """Extrai array JSON de resposta da LLM."""
        raw = text.strip()
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
        if json_match:
            raw = json_match.group(1).strip()

        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else [parsed]
        except Exception:
            start = raw.find("[")
            end = raw.rfind("]")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(raw[start : end + 1])
                except Exception:
                    pass
            return []

    async def harvest_pending_candidates(
        self, db: Session | None = None
    ) -> LexicalHarvestResult:
        """Executa a rotina diária das 19:00 de análise e promoção de termos dúbios."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            candidates = (
                db.query(LexicalCandidateRecord)
                .filter(LexicalCandidateRecord.status == "PENDING")
                .all()
            )

            now_utc = datetime.now(timezone.utc)
            if not candidates:
                return LexicalHarvestResult(
                    harvested_at=now_utc,
                    total_candidates_analyzed=0,
                    promoted_terms_count=0,
                    rejected_terms_count=0,
                    promoted_terms=[],
                    details=[],
                )

            # Prepara payload estruturado para o LLM
            candidates_payload = [
                {
                    "candidate_id": c.id,
                    "raw_term": c.raw_term,
                    "suggested_term": c.suggested_term or "",
                    "context": c.context or "",
                    "speaker": c.speaker or "",
                    "category": c.category or "GERAL",
                    "occurrences": c.occurrence_count or 1,
                    "reason": c.reason or "",
                }
                for c in candidates
            ]

            prompt = HARVESTER_USER_TEMPLATE.format(
                candidates_json=json.dumps(candidates_payload, ensure_ascii=False, indent=2)
            )

            raw_response = await self.provider.generate_text(
                prompt=prompt,
                system_instruction=HARVESTER_SYSTEM_PROMPT,
                temperature=0.1,
            )

            decisions = self._extract_json_array(raw_response)

            promoted_terms = []
            details = []
            promoted_count = 0
            rejected_count = 0

            cand_map = {c.id: c for c in candidates}
            raw_map = {c.raw_term.strip().lower(): c for c in candidates}

            for dec in decisions:
                cid = dec.get("candidate_id")
                target_cand = cand_map.get(cid)
                if not target_cand:
                    term_key = (dec.get("term") or "").strip().lower()
                    target_cand = raw_map.get(term_key)

                action = (dec.get("action") or "REJECTED").upper()
                term_name = (dec.get("term") or (target_cand.suggested_term if target_cand else "") or "").strip()

                if action == "PROMOTED" and term_name:
                    phonetic_vars = dec.get("phonetic_variations", [])
                    if target_cand and target_cand.raw_term not in phonetic_vars:
                        phonetic_vars.append(target_cand.raw_term)

                    # Adiciona ao Dicionário Oficial
                    try:
                        dictionary_service.add_term(
                            DictionaryTermCreate(
                                term=term_name,
                                phonetic_variations=list(set(phonetic_vars)),
                                expansion=dec.get("expansion"),
                                category=dec.get("category", "GERAL") or "GERAL",
                                description=dec.get("description") or dec.get("reason"),
                            )
                        )
                        promoted_count += 1
                        promoted_terms.append(term_name)
                    except Exception as exc:
                        logger.error(f"Erro ao promover termo '{term_name}': {exc}")

                    if target_cand:
                        target_cand.status = "HARVESTED"
                        target_cand.resolution_notes = dec.get("reason", "Promovido pelo Agente Harvester")
                        target_cand.updated_at = now_utc
                else:
                    rejected_count += 1
                    if target_cand:
                        target_cand.status = "REJECTED"
                        target_cand.resolution_notes = dec.get("reason", "Rejeitado pelo Agente Harvester")
                        target_cand.updated_at = now_utc

                details.append(dec)

            # Para candidatos que a LLM não mencionou explicitamente, mantém PENDING ou avalia por fallback
            for c in candidates:
                if c.status == "PENDING" and (c.occurrence_count or 1) >= 3:
                    # Termo repetido várias vezes sem decisão -> promove provisoriamente
                    term_name = c.suggested_term or c.raw_term
                    try:
                        dictionary_service.add_term(
                            DictionaryTermCreate(
                                term=term_name,
                                phonetic_variations=[c.raw_term],
                                category=c.category or "GERAL",
                                description=f"Auto-promovido por alta frequência ({c.occurrence_count}x)",
                            )
                        )
                        c.status = "HARVESTED"
                        c.resolution_notes = f"Auto-promovido por recorrência ({c.occurrence_count}x)"
                        c.updated_at = now_utc
                        promoted_count += 1
                        promoted_terms.append(term_name)
                    except Exception:
                        pass

            db.commit()

            return LexicalHarvestResult(
                harvested_at=now_utc,
                total_candidates_analyzed=len(candidates),
                promoted_terms_count=promoted_count,
                rejected_terms_count=rejected_count,
                promoted_terms=promoted_terms,
                details=details,
            )
        finally:
            if should_close:
                db.close()


lexical_harvester = LexicalHarvester()
