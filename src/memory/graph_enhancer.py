"""Módulo de Otimização e Canonicidade de Grafos com spaCy (NetworkX Enhancer).

Responsável por:
1. Extração de Núcleos Nominais (Noun Chunk Root) com spaCy;
2. Simplificação e unificação de termos compostos prolixos (ex: 'Sensores de Silos' -> 'Sensor de Silo');
3. Mapeamento hierárquico de instâncias e subsistemas (ex: 'Silo 3' -> 'Silo').
"""

import logging
import re
from typing import Dict, Any, List, Optional, Set, Tuple

from src.ai_gateway.entity_sanitizer import entity_sanitizer
from src.memory.task_sentiment_analyzer import get_spacy_nlp

logger = logging.getLogger(__name__)


class GraphEnhancerEngine:
    """Motor de enriquecimento, simplificação e canonicidade de nós NetworkX com spaCy."""

    # Termos canônicos base e raízes de equipamentos/sistemas
    EQUIPMENT_ROOT_PATTERNS = {
        r"\bsilo(\s+[0-9]+|\s+[a-z]+)?\b": "Silo",
        r"\bsensores?\s+de\s+silos?\b": "Sensor de Silo",
        r"\bsensores?\b": "Sensor",
        r"\bavi[aá]rio(\s+[0-9]+|\s+[a-z]+)?\b": "Aviário",
        r"\bbalan[cç]a(\s+[0-9]+|\s+[a-z]+)?\b": "Balança",
        r"\bgranja(\s+[0-9]+|\s+[a-z]+)?\b": "Granja",
        r"\bnotas?\s+fiscais?\b": "Nota Fiscal",
        r"\bgasp\b": "GASP",
        r"\btelemetria\b": "Telemetria",
        r"\brastreador\b": "Rastreador",
        r"\btermometria\b": "Termometria",
    }

    def __init__(self):
        self.nlp = get_spacy_nlp()

    def find_canonical_term(self, text: str) -> Optional[str]:
        """Verifica se o texto corresponde a uma raiz canônica pré-definida."""
        if not text:
            return None
        text_clean = text.strip()
        for pattern, canonical in self.EQUIPMENT_ROOT_PATTERNS.items():
            if re.fullmatch(pattern, text_clean, re.IGNORECASE):
                # Se for uma instância específica como "Silo 3" ou "Aviário 556", mantém o identificador
                # mas normaliza a grafia
                if re.search(r"\b(silo|avi[aá]rio|balan[cç]a|granja)\s+([0-9]+|[a-z]+)\b", text_clean, re.IGNORECASE):
                    parts = text_clean.split()
                    root = canonical
                    num = parts[-1].upper() if parts[-1].isdigit() else parts[-1].capitalize()
                    return f"{root} {num}"
                return canonical
        return None

    def simplify_compound_node(self, name: str, existing_nodes: Optional[Set[str]] = None) -> Tuple[str, Optional[str]]:
        """Simplifica palavras compostas usando spaCy noun chunks e busca nós já existentes.
        
        Retorna: (canonical_name: str, parent_concept: Optional[str])
        """
        clean_name = entity_sanitizer.clean_raw_string(name)
        if not clean_name:
            return "", None

        # 1. Checa padrões canônicos diretos
        canonical_match = self.find_canonical_term(clean_name)
        if canonical_match:
            # Se for "Silo 3", o conceito pai é "Silo"
            if " " in canonical_match and canonical_match.split()[0] in ("Silo", "Aviário", "Balança", "Granja"):
                return canonical_match, canonical_match.split()[0]
            return canonical_match, None

        # 2. Análise de Sintagma Nominal (Noun Chunk) com spaCy
        if self.nlp:
            doc = self.nlp(clean_name)
            
            # Se for uma frase composta prolixa (ex: "Geração de nota fiscal", "Coleta de dados da balança")
            chunks = list(doc.noun_chunks)
            if chunks and len(doc) > 2:
                # Pega o núcleo do último chunk ou chunk principal
                main_chunk = chunks[-1].text.strip()
                if main_chunk and len(main_chunk.split()) < len(clean_name.split()):
                    # Checa se o núcleo corresponde a um nó simples já existente
                    if existing_nodes:
                        for exist in existing_nodes:
                            if exist.lower() == main_chunk.lower():
                                return exist, None

        # 3. Tratamento de Singular / Plural (Lematização)
        PROTECTED_PROPER_NOUNS = {"C.Vale", "eProdutor", "Mtech", "FAL", "TMS", "BRIM", "FMIM", "Plasson", "Vascão"}
        if clean_name in PROTECTED_PROPER_NOUNS or any(clean_name.lower() == p.lower() for p in PROTECTED_PROPER_NOUNS):
            for p in PROTECTED_PROPER_NOUNS:
                if clean_name.lower() == p.lower():
                    return p, None

        if self.nlp:
            doc = self.nlp(clean_name)
            tokens = [t for t in doc]
            if len(tokens) == 1 and tokens[0].pos_ in ("NOUN", "PROPN"):
                lemma = tokens[0].lemma_.capitalize()
                clean_name = lemma
            elif len(tokens) == 2 and tokens[0].pos_ == "NOUN" and tokens[1].pos_ in ("NOUN", "ADJ"):
                # Ex: "Sensores silos" -> "Sensor Silo"
                clean_name = f"{tokens[0].lemma_.capitalize()} {tokens[1].lemma_.capitalize()}"

        return clean_name, None


graph_enhancer = GraphEnhancerEngine()
