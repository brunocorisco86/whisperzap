"""Módulo de Economia Prévia de Tokens com spaCy (Pre-LLM Token Economy).

Reduz os custos de chamadas de IA e latência através de:
1. Bypass de Mensagens Fáticas/Triviais (0 tokens gastos);
2. Remoção de disfluências, vícios de fala e hesitações em áudios longos;
3. Pré-extração léxica local.
"""

import logging
import re
from typing import Dict, Any, List, Optional, Tuple

from src.memory.task_sentiment_analyzer import get_spacy_nlp

logger = logging.getLogger(__name__)

# Expressões puramente fáticas/sociais de saudação e encerramento
PHATIC_EXPRESSIONS = {
    "bom dia", "boa tarde", "boa noite", "olá", "ola", "oi", "oie", "opa", "e ai", "e aí",
    "obrigado", "obrigada", "valeu", "falou", "ok", "beleza", "blz",
    "tá bom", "ta bom", "combinado", "certo", "show", "perfeito", "joia", "jóia",
    "sim", "não", "nao", "s", "n", "tudo", "bem", "bom", "tudo bem", "tudo bom", "como vai",
    "olá tudo bem", "ola tudo bem", "oi tudo bem", "olá tudo bom", "ola tudo bom", "oi tudo bom",
    "até mais", "ate mais", "abraço", "tchau", "valeu obrigado", "obrigado valeu",
}

# Padrões de disfluência de fala e vícios de linguagem comuns em notas de voz
DISFLUENCY_PATTERNS = [
    r"\b(é{2,}|eh{1,}|hum{1,}|hã{1,}|ahn{1,})\b",
    r"\b(tipo\s+assim|tipo)\b",
    r"\b(n[ée](\s+n[ée])?)\b",
    r"\b(como\s+(que\s+)?se\s+diz|como\s+[eé]\s+que\s+fala)\b",
    r"\b(sabe\s+n[ée]|sabe\s+como\s+[eé])\b",
    r"\b(ent[ãa]o\s+assim|a[ií]\s+tipo)\b",
]


class TokenEconomyEngine:
    """Motor de otimização de tokens e filtragem pré-LLM com spaCy."""

    def __init__(self):
        self.nlp = get_spacy_nlp()

    def is_phatic_or_trivial(self, text: str) -> Tuple[bool, str]:
        """Detecta se uma mensagem é puramente social/fática, dispensando chamada a LLM.
        
        Retorna: (is_trivial: bool, reason: str)
        """
        if not text:
            return True, "empty_text"

        clean = re.sub(r"[^\w\s]", "", text.lower()).strip()
        clean_single_spaces = re.sub(r"\s+", " ", clean)

        # 1. Match exato com expressões fáticas
        if clean_single_spaces in PHATIC_EXPRESSIONS:
            return True, f"phatic_expression_'{clean_single_spaces}'"

        words = clean_single_spaces.split()
        if len(words) <= 3 and all(w in PHATIC_EXPRESSIONS for w in words):
            return True, "short_phatic_combination"

        # 2. Análise Morfossintática com spaCy
        if self.nlp and len(words) <= 4:
            doc = self.nlp(text)
            # Se não tem nenhum substantivo (NOUN/PROPN) nem verbo de ação (VERB)
            has_content_word = any(t.pos_ in ("NOUN", "PROPN", "VERB") for t in doc)
            if not has_content_word:
                return True, "no_content_nouns_or_verbs"

        return False, "substantive_content"

    def prune_disfluencies(self, text: str) -> Tuple[str, int]:
        """Remove hesitações e disfluências de áudio antes de enviar para o AI Gateway.
        
        Retorna: (pruned_text: str, words_saved: int)
        """
        if not text or len(text.strip()) < 10:
            return text, 0

        original_word_count = len(text.split())
        cleaned = text

        # 1. Remove padrões de disfluência conhecidos
        for pattern in DISFLUENCY_PATTERNS:
            cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)

        # 2. Remove gagueira / repetição de palavras idênticas seguidas (ex: "o o sensor", "vamos vamos fazer")
        cleaned = re.sub(r"\b(\w+)\s+\1\b", r"\1", cleaned, flags=re.IGNORECASE)

        # 3. Normaliza espaços excedentes e pontuações duplicadas
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = re.sub(r"\s+([,.;!?])", r"\1", cleaned)

        new_word_count = len(cleaned.split())
        words_saved = max(0, original_word_count - new_word_count)

        if words_saved > 0:
            logger.info(f"💰 [Token Economy] Disfluências podadas: {words_saved} palavras/tokens economizados.")

        return cleaned, words_saved


token_economy = TokenEconomyEngine()
