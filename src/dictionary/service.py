"""Serviço de Dicionário Léxico e Glossário de Domínio Hermes."""

import json
import logging
import os
import re
from datetime import datetime, timezone
from uuid import uuid4

from src.config import settings
from src.dictionary.schemas import DictionaryTerm, DictionaryTermCreate

logger = logging.getLogger(__name__)

# Termos padrão iniciais do domínio de agronegócio, avicultura e homelab
DEFAULT_TERMS = [
    {
        "term": "FAL",
        "phonetic_variations": ["FAU", "fau", "fao", "fal", "folha de lote"],
        "expansion": "Ficha de Acompanhamento de Lote",
        "category": "ZOOTECNIA",
        "description": "Documento e registro diário com mortalidade, consumo de ração e peso das aves.",
    },
    {
        "term": "eProdutor",
        "phonetic_variations": ["e-produtor", "eprodutor", "e produtor", "aplicativo do produtor"],
        "expansion": "Aplicativo eProdutor",
        "category": "SISTEMAS",
        "description": "Aplicativo mobile utilizado pelos cooperados e integrados para lançamento de dados de campo.",
    },
    {
        "term": "C.Vale",
        "phonetic_variations": ["Sevale", "cvale", "c vale", "cevale", "se vale", "sivale"],
        "expansion": "Cooperativa Agroindustrial C.Vale",
        "category": "AGRONEGOCIO",
        "description": "Cooperativa agroindustrial de integração avícola e grãos.",
    },
    {
        "term": "Mortalidade",
        "phonetic_variations": ["mhotilidade", "hotelidade", "motilidade", "mortalidade das aves"],
        "expansion": "Mortalidade Diária do Aviário",
        "category": "ZOOTECNIA",
        "description": "Contagem de perdas diárias no lote avícola.",
    },
    {
        "term": "Vazio Sanitário",
        "phonetic_variations": ["vazio sanitario", "intervalo sanitário", "vazio de lote"],
        "expansion": "Período de Vazio Sanitário",
        "category": "ZOOTECNIA",
        "description": "Período de desinfecção, descanso e preparação do aviário entre lotes sucessivos.",
    },
    {
        "term": "Silos e Ração",
        "phonetic_variations": ["sensor de racao", "sensor do silo", "nivel de racao", "silo de racao"],
        "expansion": "Monitoramento de Nível de Silos de Ração",
        "category": "EQUIPAMENTOS",
        "description": "Sensores IoT de pesagem e nível nos silos de armazenagem de ração.",
    },
    {
        "term": "IEP",
        "phonetic_variations": ["iep", "i e p", "indice de eficiencia produtiva"],
        "expansion": "Índice de Eficiência Produtiva",
        "category": "ZOOTECNIA",
        "description": "Métrica zootécnica de desempenho global do lote avícola.",
    },
    {
        "term": "Conversão Alimentar",
        "phonetic_variations": ["conversao alimentar", "ca", "c a"],
        "expansion": "Taxa de Conversão Alimentar (CA)",
        "category": "ZOOTECNIA",
        "description": "Quilogramas de ração consumida por quilograma de peso vivo produzido.",
    },
]


class DictionaryService:
    """Gerenciador do Dicionário Léxico com persistência em JSON."""

    def __init__(self, persistence_path: str = settings.DICTIONARY_PERSISTENCE_PATH):
        self.persistence_path = persistence_path
        self.terms: dict[str, DictionaryTerm] = {}
        self._load_or_initialize()

    def _load_or_initialize(self) -> None:
        """Carrega termos persistidos ou inicializa com o vocabulário padrão."""
        if os.path.exists(self.persistence_path):
            try:
                with open(self.persistence_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        term_obj = DictionaryTerm(**item)
                        self.terms[term_obj.id] = term_obj
                logger.info(f"Dicionário léxico carregado com {len(self.terms)} termos de {self.persistence_path}")
                return
            except Exception as e:
                logger.warning(f"Falha ao carregar dicionário de {self.persistence_path}: {e}. Inicializando padrões.")

        # Inicializa com padrões
        os.makedirs(os.path.dirname(self.persistence_path) or ".", exist_ok=True)
        for item in DEFAULT_TERMS:
            term_id = str(uuid4())[:8]
            term_obj = DictionaryTerm(
                id=term_id,
                created_at=datetime.now(timezone.utc).isoformat(),
                **item,
            )
            self.terms[term_id] = term_obj
        self._save()

    def _save(self) -> None:
        """Persiste o dicionário atual no disco."""
        try:
            os.makedirs(os.path.dirname(self.persistence_path) or ".", exist_ok=True)
            with open(self.persistence_path, "w", encoding="utf-8") as f:
                json.dump([t.model_dump() for t in self.terms.values()], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Erro ao salvar dicionário léxico: {e}")

    def list_terms(self, category: str | None = None) -> list[DictionaryTerm]:
        """Lista termos cadastrados, opcionalmente filtrados por categoria."""
        terms = list(self.terms.values())
        if category:
            terms = [t for t in terms if t.category.upper() == category.upper()]
        return sorted(terms, key=lambda t: t.term)

    def get_term(self, term_id: str) -> DictionaryTerm | None:
        """Obtém um termo por ID."""
        return self.terms.get(term_id)

    def add_term(self, data: DictionaryTermCreate) -> DictionaryTerm:
        """Adiciona um novo termo ao dicionário."""
        # Verifica se já existe termo igual
        for existing in self.terms.values():
            if existing.term.lower() == data.term.lower():
                existing.phonetic_variations = list(set(existing.phonetic_variations + data.phonetic_variations))
                if data.expansion:
                    existing.expansion = data.expansion
                if data.description:
                    existing.description = data.description
                if data.category:
                    existing.category = data.category
                self._save()
                return existing

        term_id = str(uuid4())[:8]
        new_term = DictionaryTerm(
            id=term_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            **data.model_dump(),
        )
        self.terms[term_id] = new_term
        self._save()
        return new_term

    def delete_term(self, term_id: str) -> bool:
        """Remove um termo do dicionário."""
        if term_id in self.terms:
            del self.terms[term_id]
            self._save()
            return True
        return False

    def get_whisper_initial_prompt(self) -> str:
        """Gera string de palavras-chave para guiar o Whisper STT."""
        keywords: list[str] = []
        for t in self.terms.values():
            keywords.append(t.term)
            if t.expansion:
                keywords.append(t.expansion)
        return ", ".join(keywords)

    def get_prompt_context_hint(self) -> str:
        """Gera bloco de texto formatado com o glossário de domínio para os prompts LLM."""
        if not self.terms:
            return ""

        lines = ["### Glossário de Termos e Jargões do Domínio:"]
        for t in self.terms.values():
            variations = f" (variações comuns de áudio: {', '.join(t.phonetic_variations)})" if t.phonetic_variations else ""
            expansion = f" = {t.expansion}" if t.expansion else ""
            desc = f" — {t.description}" if t.description else ""
            lines.append(f"- **{t.term}**{expansion}{variations}{desc}")

        return "\n".join(lines)

    def apply_lexical_corrections(self, text: str) -> str:
        """Aplica substituições determinísticas de variações fonéticas grosseiras."""
        corrected = text
        for t in self.terms.values():
            for var in t.phonetic_variations:
                if len(var) >= 3:
                    # Substitui correspondência de palavra inteira preservando caso base
                    pattern = re.compile(rf"\b{re.escape(var)}\b", re.IGNORECASE)
                    corrected = pattern.sub(t.term, corrected)
        return corrected


dictionary_service = DictionaryService()
