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

# Termos padrão iniciais do domínio de agronegócio, avicultura, C.Vale, Mtech e homelab
DEFAULT_TERMS = [
    {
        "term": "C.Vale",
        "phonetic_variations": ["Sevala", "sevala", "Sevale", "sevale", "cvale", "c vale", "cevale", "ce vale", "se vale", "sivale", "civale", "si vale"],
        "expansion": "Cooperativa Agroindustrial C.Vale",
        "category": "AGRONEGOCIO",
        "description": "Cooperativa agroindustrial de integração avícola e grãos.",
    },
    {
        "term": "Agrocenter",
        "phonetic_variations": ["agrocenter", "agro center", "agrocênter", "agro-center", "agro senter"],
        "expansion": "Portal Agrocenter C.Vale",
        "category": "SISTEMAS",
        "description": "Portal ERP e centralizador de pedidos de ração e insumos agropecuários.",
    },
    {
        "term": "eProdutor",
        "phonetic_variations": ["e-produtor", "eprodutor", "e produtor", "aplicativo do produtor"],
        "expansion": "Aplicativo eProdutor C.Vale",
        "category": "SISTEMAS",
        "description": "Aplicativo mobile utilizado pelos cooperados e integrados para lançamento de dados de campo.",
    },
    {
        "term": "Mtech",
        "phonetic_variations": ["emitech", "emitequi", "m-tech", "m tech", "mtequi", "m-teck", "mtech systems"],
        "expansion": "Mtech Systems",
        "category": "SISTEMAS",
        "description": "Software global de gestão de integração e rastreabilidade avícola.",
    },
    {
        "term": "Amino",
        "phonetic_variations": ["amíno", "amino software", "mtech amino", "banco amino", "amino sql"],
        "expansion": "Mtech Amino ERP",
        "category": "SISTEMAS",
        "description": "Banco de dados MS SQL Server e backend do ecossistema Mtech Systems.",
    },
    {
        "term": "BRIM",
        "phonetic_variations": ["brin", "brim", "b r i m", "módulo brim", "modulo brim"],
        "expansion": "Broiler Integration Module (Mtech)",
        "category": "SISTEMAS",
        "description": "Módulo de controle zootécnico e acompanhamento de lotes de frango de corte.",
    },
    {
        "term": "FMIM",
        "phonetic_variations": ["fmin", "fmim", "f m i m", "módulo fmim", "modulo fmim"],
        "expansion": "Feed Mill Integration Module (Mtech)",
        "category": "SISTEMAS",
        "description": "Módulo de gestão de fábrica de ração e formulação nutricional.",
    },
    {
        "term": "TMS",
        "phonetic_variations": ["tms", "t m s", "têemeésse", "sistema tms", "roteirizador"],
        "expansion": "Transportation Management System",
        "category": "LOGISTICA",
        "description": "Sistema de gestão e otimização de rotas e frotas para entrega de ração nos silos.",
    },
    {
        "term": "Silos e Ração",
        "phonetic_variations": ["sensor de racao", "sensor do silo", "nivel de racao", "silo de racao", "telemetria de silo", "sensores de silos"],
        "expansion": "Monitoramento de Nível de Silos de Ração",
        "category": "EQUIPAMENTOS",
        "description": "Sensores IoT de pesagem e nível nos silos de armazenagem de ração.",
    },
    {
        "term": "FAL",
        "phonetic_variations": ["FAU", "fau", "fao", "fal", "falo", "Falo", "folha de lote", "folha do lote", "ficha de lote", "ficha do lote", "ficha de acompanhamento", "ficha de acompanhamento de lote"],
        "expansion": "Ficha de Acompanhamento de Lote",
        "category": "ZOOTECNIA",
        "description": "Documento e registro diário com mortalidade, consumo de ração e peso das aves.",
    },
    {
        "term": "IEP",
        "phonetic_variations": ["iep", "i e p", "indice de eficiencia produtiva", "índice de eficiência produtiva"],
        "expansion": "Índice de Eficiência Produtiva",
        "category": "ZOOTECNIA",
        "description": "Métrica zootécnica de desempenho global do lote avícola.",
    },
    {
        "term": "Conversão Alimentar",
        "phonetic_variations": ["conversao alimentar", "ca", "c.a.", "c a", "taxa de conversao"],
        "expansion": "Taxa de Conversão Alimentar (CA)",
        "category": "ZOOTECNIA",
        "description": "Quilogramas de ração consumida por quilograma de peso vivo produzido.",
    },
    {
        "term": "Mortalidade",
        "phonetic_variations": ["mhotilidade", "hotelidade", "motilidade", "mortalidade das aves", "perda de lote"],
        "expansion": "Mortalidade Diária do Aviário",
        "category": "ZOOTECNIA",
        "description": "Contagem de perdas diárias no lote avícola.",
    },
    {
        "term": "Vazio Sanitário",
        "phonetic_variations": ["vazio sanitario", "intervalo sanitário", "vazio de lote", "intervalo de lote"],
        "expansion": "Período de Vazio Sanitário",
        "category": "ZOOTECNIA",
        "description": "Período de desinfecção, descanso e preparação do aviário entre lotes sucessivos.",
    },
    {
        "term": "Pintainhos",
        "phonetic_variations": ["pintinho", "pintinhos", "pintainho", "alojamento de pintos", "alojamento"],
        "expansion": "Alojamento de Pintainhos de 1 Dia",
        "category": "ZOOTECNIA",
        "description": "Chegada e recepção do lote de aves no aviário com aquecimento e forragem.",
    },
    {
        "term": "Apanha e Abate",
        "phonetic_variations": ["apanha", "abate", "previsao de abate", "apanha de frangos", "carregamento"],
        "expansion": "Programação de Apanha e Abate de Frangos",
        "category": "LOGISTICA",
        "description": "Operação de captura, pesagem final e transporte de aves para o frigorífico.",
    },
    {
        "term": "Hermes",
        "phonetic_variations": ["hermes", "érmes", "agente hermes", "copiloto hermes"],
        "expansion": "Hermes Voice Memory & Reasoning Agent",
        "category": "TECNOLOGIA",
        "description": "Agente cognitivo com RAG híbrido, memória vetorial e grafo de conhecimento.",
    },
    {
        "term": "James",
        "phonetic_variations": ["james", "djeimes", "jeimes", "mordomo james", "mordomo virtual"],
        "expansion": "James (Mordomo de Transcrição de Voz)",
        "category": "TECNOLOGIA",
        "description": "Módulo de recepção, transcrição e revisão léxica de áudios do WhatsApp.",
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
