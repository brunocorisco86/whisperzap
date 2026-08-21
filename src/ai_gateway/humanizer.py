"""Módulo de Humanização e Sanitização de Respostas do Agente Hermes & Oráculo Melpômene.

Utiliza spaCy NLP e o Dicionário Léxico de Polímnia para remover lixo técnico
(UUIDs, tags de banco, triplas brutas, metadados de agenda) e harmonizar a resposta final.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from src.dictionary.service import dictionary_service
from src.memory.task_sentiment_analyzer import get_spacy_nlp

logger = logging.getLogger(__name__)


class HermesResponseHumanizer:
    """Sanitizador e humanizador de respostas geradas pelo assistente Hermes."""

    def __init__(self):
        self.nlp = get_spacy_nlp()
        self.dict_service = dictionary_service

    def strip_technical_junk(self, text: str) -> str:
        """Remove padrões técnicos, UUIDs, IDs de banco, campos vCard e triplas brutas."""
        if not text:
            return ""

        cleaned = text

        # 1. Remove menções a IDs de mensagens ou entidades: [ID: ...] ou UUIDs puros
        cleaned = re.sub(r"\[ID:\s*[a-f0-9\-]{8,}\]", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\(ID:\s*[a-f0-9\-]{8,}\)", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\b", "", cleaned)

        # 2. Remove tags residuais de vCard e notas importadas
        cleaned = re.sub(r"ID Yahoo:[^\n]+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\[Nota Importada\]:[^\n]+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"Importado via Google vCard", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"Contato identificado via WhatsApp", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"Contato Oficial:\s*", "", cleaned)

        # 3. Limpa metadados de entidades tabulados com barras verticais (Entidade: X | Categoria: Y ...)
        cleaned = re.sub(r"Entidade:\s*", "", cleaned)
        cleaned = re.sub(r"\|\s*Categoria:\s*[A-Z_]+", "", cleaned)
        cleaned = re.sub(r"\|\s*Cargo:\s*[A-Z_]+", "", cleaned)
        cleaned = re.sub(r"\|\s*Telefone:\s*\d+", "", cleaned)
        cleaned = re.sub(r"\|\s*Info:\s*", "— ", cleaned)

        # 4. Remove triplas de grafo cruas se vazarem no texto corrido
        cleaned = re.sub(r"([A-Za-z0-9\s]+)\s*-\[[A-Z_]+\]->\s*([A-Za-z0-9\s]+)", r"\1 conectado a \2", cleaned)

        # 5. Remove múltiplos pipes ou traços órfãos resultantes das limpezas
        cleaned = re.sub(r"\|\s*\|+", "|", cleaned)
        cleaned = re.sub(r"\|\s*$", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"^\s*\|\s*", "", cleaned, flags=re.MULTILINE)

        # 6. Normaliza quebras de linha excessivas e espaços
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def canonicalize_domain_terms(self, text: str) -> str:
        """Aplica a grafia oficial e padronizada dos termos e siglas do dicionário Polímnia."""
        if not text:
            return ""

        result = text
        terms = self.dict_service.get_all_terms()
        for t in terms:
            canonical = t.term
            all_forms = [canonical] + (t.phonetic_variations or [])
            for form in all_forms:
                if not form:
                    continue
                pattern = rf"\b{re.escape(form)}\b"
                result = re.sub(pattern, canonical, result, flags=re.IGNORECASE)

        return result

    def polish_syntax_with_spacy(self, text: str) -> str:
        """Refina pontuação, capitalização e parágrafos utilizando spaCy."""
        if not text or not self.nlp:
            return text

        lines = text.split("\n")
        polished_lines = []

        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                polished_lines.append("")
                continue

            # Mantém cabeçalhos markdown ou marcadores de tópicos intactos
            if trimmed.startswith(("#", "•", "-", "*", "💬", "📋", "🌾", "🔗", "📌")):
                # Se for um item de lista, garante espaçamento após marcador
                trimmed = re.sub(r"^([•\-\*])\s*", r"• ", trimmed)
                polished_lines.append(trimmed)
                continue

            doc = self.nlp(trimmed)
            sents = [s.text.strip() for s in doc.sents if s.text.strip()]
            fixed_sents = []
            for s in sents:
                # Garante primeira letra maiúscula
                if len(s) > 1:
                    s = s[0].upper() + s[1:]
                # Garante pontuação final
                if s and s[-1] not in (".", "!", "?", ":", ";"):
                    s += "."
                fixed_sents.append(s)

            polished_lines.append(" ".join(fixed_sents))

        return "\n".join(polished_lines)

    def humanize(self, raw_answer: str, parsed: Optional[Any] = None) -> str:
        """Executa a esteira completa de humanização e despoluição da resposta."""
        if not raw_answer:
            return "Não foram encontrados registros suficientes para responder a esta consulta."

        # 1. Filtro Anti-Lixo Técnico
        cleaned = self.strip_technical_junk(raw_answer)

        # 2. Padronização Léxica de Domínio com Polímnia
        canonicalized = self.canonicalize_domain_terms(cleaned)

        # 3. Polimento Sintático com spaCy
        polished = self.polish_syntax_with_spacy(canonicalized)

        # 4. Ajustes finais de formatação
        final_text = re.sub(r"\n{3,}", "\n\n", polished).strip()
        return final_text


# Instância singleton
hermes_response_humanizer = HermesResponseHumanizer()
