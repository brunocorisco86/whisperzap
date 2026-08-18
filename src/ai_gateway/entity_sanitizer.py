"""Módulo de Guardrail, Sanitização e Correção Ortográfica de Entidades do AI Gateway.

Utiliza spaCy, lematização morfológica, correções fonéticas do Whisper e
regras ortográficas para evitar que erros de digitação (ex: 'Fihlos') ou
alucinações fonéticas (ex: 'Macau' -> 'Call') virem nós no Grafo NetworkX.
"""

import logging
import re
import unicodedata
from typing import Dict, Any, List, Optional, Tuple

from src.memory.task_sentiment_analyzer import get_spacy_nlp

logger = logging.getLogger(__name__)

# Tabela de correções fonéticas e erros ortográficos conhecidos (Whisper & Digitação)
KNOWN_TYPOS_AND_PHONETIC_FIXES = {
    # Erros ortográficos / typos de digitação
    "fihlos": "Filhos",
    "fihlo": "Filho",
    "fihla": "Filha",
    "abateodouro": "Abatedouro",
    "abatedoro": "Abatedouro",
    "avíario": "Aviário",
    "aviario": "Aviário",
    "racao": "Ração",
    "raçao": "Ração",
    "balanca": "Balança",
    "balanço": "Balanço",
    "granja": "Granja",
    "produtor": "Produtor",
    "cooperado": "Cooperado",
    "relatorio": "Relatório",
    "camara": "Câmara",
    "silo": "Silo",
    "sensores": "Sensor",
    "sensor": "Sensor",
    "telemetria": "Telemetria",
    "amonia": "Amônia",
    "temperatura": "Temperatura",
    "umidade": "Umidade",
    "fal": "FAL",
    "tms": "TMS",
    "plasson": "Plasson",

    # Alucinações fonéticas clássicas do Whisper em português
    "macau": "Call",
    "uma call": "Call",
    "uma col": "Call",
    "a call": "Call",
    "call": "Call",
    "sevala": "C.Vale",
    "sevale": "C.Vale",
    "cevale": "C.Vale",
    "cvale": "C.Vale",
    "c vale": "C.Vale",
    "agrocenter": "Agrocenter",
    "agrocênter": "Agrocenter",
    "agro center": "Agrocenter",
    "eprodutor": "eProdutor",
    "e-produtor": "eProdutor",
    "e produtor": "eProdutor",
    "emitech": "Mtech",
    "emitequi": "Mtech",
    "m-tech": "Mtech",
    "m tech": "Mtech",
    "mtequi": "Mtech",
    "vascão": "Vascão",
    "vascao": "Vascão",
}

# Entidades e termos geográficos remotos que costumam ser alucinações sem contexto local
SUSPICIOUS_GEOGRAPHIC_HALLUCINATIONS = {
    "macau", "tóquio", "toquio", "madagascar", "singapura", "cazaquistão",
    "nova iorque", "paris", "londres", "berlim", "roma", "pequim",
}


class EntitySanitizerGuardrail:
    """Guardrail inteligente de sanitização e canonicidade de entidades para IA e Grafo."""

    def __init__(self):
        self.nlp = get_spacy_nlp()

    def clean_raw_string(self, text: str) -> str:
        """Limpa aspas, pontuações excedentes e espaços duplicados."""
        if not text:
            return ""
        clean = text.strip().strip("\"'“”`.,;:")
        clean = re.sub(r"\s+", " ", clean)
        return clean.strip()

    def sanitize_entity_name(self, name: str, category: str = "OTHER") -> Tuple[str, str, bool]:
        """Sanitiza o nome da entidade, corrigindo typos, alucinações e capitalização.
        
        Retorna: (sanitized_name: str, sanitized_category: str, was_modified: bool)
        """
        clean_name = self.clean_raw_string(name)
        if not clean_name:
            return "", category, False

        lower_name = clean_name.lower()
        modified = False

        # 1. Checagem direta de typos conhecidos e correções fonéticas do Whisper
        if lower_name in KNOWN_TYPOS_AND_PHONETIC_FIXES:
            fixed_name = KNOWN_TYPOS_AND_PHONETIC_FIXES[lower_name]
            # Se 'Macau' virar 'Call', ajusta categoria para CONCEPT/SYSTEM
            new_cat = "CONCEPT" if fixed_name == "Call" else category
            return fixed_name, new_cat, True

        # 2. Bloqueio de alucinações geográficas do Whisper (ex: "Macau" como LOCATION)
        if category == "LOCATION" and lower_name in SUSPICIOUS_GEOGRAPHIC_HALLUCINATIONS:
            logger.info(f"🛡️ [Guardrail] Alucinação geográfica detectada: '{clean_name}'")
            # Converte para termo conceituais ou descarta se for espúrio
            if lower_name == "macau":
                return "Call", "CONCEPT", True
            return "", "OTHER", True

        # 3. Análise morfológica com spaCy (Lematização e Remoção de Plural em Entidades Genéricas)
        if self.nlp:
            doc = self.nlp(clean_name)
            tokens = [t for t in doc]
            
            # Se for um substantivo plural genérico (ex: "Sensores" -> "Sensor", "Aviários" -> "Aviário")
            if len(tokens) == 1 and tokens[0].pos_ in ("NOUN", "PROPN") and category not in ("PERSON", "COMPANY"):
                lemma = tokens[0].lemma_.capitalize()
                # Verifica se há correção ortográfica no lemma
                lemma_lower = lemma.lower()
                if lemma_lower in KNOWN_TYPOS_AND_PHONETIC_FIXES:
                    lemma = KNOWN_TYPOS_AND_PHONETIC_FIXES[lemma_lower]
                if lemma != clean_name:
                    return lemma, category, True

            # Correção interna de palavras com typo dentro de termos compostos (ex: "Alimentação dos fihlos")
            fixed_words = []
            word_changed = False
            for t in tokens:
                t_lower = t.text.lower()
                if t_lower in KNOWN_TYPOS_AND_PHONETIC_FIXES:
                    fixed_words.append(KNOWN_TYPOS_AND_PHONETIC_FIXES[t_lower])
                    word_changed = True
                else:
                    fixed_words.append(t.text)

            if word_changed:
                clean_name = " ".join(fixed_words)
                modified = True

        # 4. Formatação de Capitalização Padrão (Title Case para substantivos próprios)
        if category in ("PERSON", "COMPANY", "LOCATION", "PROJECT"):
            # Preserva casing de siglas (FAL, TMS, C.Vale, eProdutor)
            if not any(clean_name == acronym for acronym in ("C.Vale", "eProdutor", "Mtech", "FAL", "TMS", "BRIM", "FMIM")):
                if clean_name.islower() or clean_name.isupper():
                    clean_name = clean_name.title()
                    modified = True

        return clean_name, category, modified

    def sanitize_extracted_entities(self, entities: List[Any]) -> List[Any]:
        """Aplica o guardrail sobre a lista de entidades extraídas pela IA."""
        sanitized = []
        seen_names = set()

        for ent in entities:
            if isinstance(ent, dict):
                name = ent.get("name", "")
                cat = ent.get("category", "OTHER")
                details = ent.get("details")
            else:
                name = getattr(ent, "name", "")
                cat = getattr(ent, "category", "OTHER")
                details = getattr(ent, "details", None)

            clean_n, clean_cat, _ = self.sanitize_entity_name(name, cat)
            if not clean_n or clean_n.lower() in seen_names:
                continue

            seen_names.add(clean_n.lower())
            if isinstance(ent, dict):
                ent["name"] = clean_n
                ent["category"] = clean_cat
                sanitized.append(ent)
            else:
                setattr(ent, "name", clean_n)
                setattr(ent, "category", clean_cat)
                sanitized.append(ent)

        return sanitized


entity_sanitizer = EntitySanitizerGuardrail()
