"""Motor de Mineração Terminológica, Sugestão de Dicionário e Geração Fonética com spaCy.

Responsável por:
1. Extração autônoma de sintagmas nominais e jargões técnicos em conversas (Termhood / C-Value);
2. Geração heurística de variações fonéticas prováveis do Whisper em português;
3. Inferência de categoria por dependência sintática do contexto de fala.
"""

import logging
import re
import unicodedata
from collections import Counter
from typing import Dict, Any, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

from src.memory.task_sentiment_analyzer import get_spacy_nlp

logger = logging.getLogger(__name__)

# Stopwords e palavras puramente conversacionais que nunca formam termos de domínio isolados
COMMON_STOPWORDS = {
    "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas", "para", "por", "com",
    "sem", "um", "uma", "uns", "umas", "o", "a", "os", "as", "e", "ou", "mas", "que",
    "como", "se", "mais", "muito", "pouco", "já", "ainda", "quando", "onde", "aqui",
    "ali", "lá", "isso", "aquilo", "este", "esta", "esse", "essa", "aquele", "aquela",
    "meu", "minha", "seu", "sua", "nosso", "nossa", "bom", "boa", "dia", "tarde", "noite",
    "favor", "obrigado", "obrigada", "valeu", "falou", "ok", "beleza", "blz", "tá", "ta",
    "sim", "não", "nao", "coisa", "algo", "gente", "pessoal", "hoje", "ontem", "amanhã",
}

# Verbos indicadores de categorias específicas
CATEGORY_VERB_MAP = {
    "EQUIPAMENTO": {"calibrar", "ligar", "desligar", "instalar", "trocar", "consertar", "quebrar", "medir", "aferir", "conectar", "queimar", "quebrou"},
    "SISTEMAS": {"lançar", "abrir", "acessar", "logar", "cadastrar", "integrar", "salvar", "exportar", "importar", "gerar", "emitir", "consultar", "digitar"},
    "ZOOTECNIA": {"alimentar", "pesar", "vacinar", "alojar", "abater", "morrer", "crescer", "ingerir", "medicar", "tratar", "apanhar"},
    "LOGISTICA": {"transportar", "carregar", "descarregar", "entregar", "enviar", "despachar", "rastrear", "pesar", "embarcar"},
    "AGRONEGOCIO": {"cooperar", "integrar", "comprar", "vender", "faturar", "fechar", "negociar", "plantar", "colher"},
}


class TermSuggestion(BaseModel):
    """Modelo de sugestão inteligente de termo para o Dicionário Léxico."""
    term: str = Field(..., description="Termo canônico sugerido")
    phonetic_variations: List[str] = Field(default_factory=list, description="Variações fonéticas geradas para o Whisper")
    category: str = Field(default="AGRONEGOCIO", description="Categoria inferida por contexto")
    expansion: str = Field(default="", description="Expansão provável ou definição do termo")
    frequency: int = Field(default=1, description="Número de ocorrências encontradas no histórico")
    sample_contexts: List[str] = Field(default_factory=list, description="Frases de exemplo onde o termo foi falado")
    confidence_score: float = Field(default=0.85, description="Pontuação de relevância técnica do termo")


class PhoneticVariationGenerator:
    """Gerador de variações fonéticas e ortográficas simulando a transcrição do Whisper."""

    @staticmethod
    def normalize_ascii(text: str) -> str:
        """Remove acentos e caracteres especiais mantendo alfanuméricos simples."""
        nfkd = unicodedata.normalize("NFKD", text)
        return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()

    def generate(self, term: str) -> List[str]:
        """Gera um conjunto rico de variações fonéticas prováveis para o termo em português."""
        if not term or len(term.strip()) < 2:
            return []

        raw = term.strip()
        variations: Set[str] = set()

        # 1. Variações diretas de caixa e pontuação
        variations.add(raw.lower())
        ascii_clean = self.normalize_ascii(raw)
        variations.add(ascii_clean)

        # 2. Variação de siglas com pontos / traços / espaços (ex: 'C.Vale' -> 'cvale', 'c vale', 'sevale')
        if "." in raw or "-" in raw or "/" in raw:
            no_punct = re.sub(r"[.\-_/]", "", raw).lower()
            space_punct = re.sub(r"[.\-_/]", " ", raw).lower()
            space_clean = re.sub(r"\s+", " ", space_punct).strip()
            variations.add(no_punct)
            variations.add(space_clean)

        # 3. Tratamento fonético específico para nomes estrangeiros / tecnológicos
        lower_term = raw.lower()

        # Epêntese vocálica inicial antes de consoante (ex: 'mtech' -> 'emitech', 'm-tech', 'mtequi')
        if re.match(r"^[a-z][A-Z]", raw) or lower_term.startswith("m") or lower_term.startswith("e"):
            # Variações tipo 'mtech'
            if "tech" in lower_term:
                base = lower_term.replace("tech", "")
                variations.add(f"{base}teck")
                variations.add(f"{base}tequi")
                variations.add(f"{base}tech")
                if base.startswith("m"):
                    variations.add(f"emi{base[1:]}tech")
                    variations.add(f"emi{base[1:]}tequi")
                    variations.add(f"m-tech")
                    variations.add(f"m tech")

        # 4. Alternâncias fonéticas comuns do português falado
        # C/S/Z alternâncias (ex: 'C.Vale' -> 'sevale', 'cevale', 'sivale')
        if lower_term.startswith("c") and len(lower_term) > 2 and lower_term[1] in ("e", "i", "."):
            val_part = re.sub(r"^c[.\s]?", "", lower_term)
            variations.add(f"se{val_part}")
            variations.add(f"ce{val_part}")
            variations.add(f"si{val_part}")
            variations.add(f"se {val_part}")
            variations.add(f"c {val_part}")

        # Inserção de espaço em palavras compostas (ex: 'agrocenter' -> 'agro center', 'agrocênter')
        if "center" in lower_term:
            variations.add(lower_term.replace("center", " center"))
            variations.add(lower_term.replace("center", "senter"))
            variations.add(lower_term.replace("center", " senter"))

        if "produtor" in lower_term and (lower_term.startswith("e") or lower_term.startswith("e-")):
            variations.add("eprodutor")
            variations.add("e-produtor")
            variations.add("e produtor")
            variations.add("aplicativo do produtor")

        # 5. Siglas e acrônimos soletrados (ex: 'TMS' -> 'tê-eme-esse', 'tms', 't m s')
        if raw.isupper() and len(raw) in (2, 3, 4):
            variations.add(" ".join(list(raw.lower())))
            variations.add("-".join(list(raw.lower())))

        # Remove o próprio termo exato das variações e termos vazios
        clean_vars = [v for v in sorted(list(variations)) if v and v != raw]
        return clean_vars[:8]


class SpacyTermMiner:
    """Minerador sintático de termos técnicos e sugestões léxicas com spaCy."""

    def __init__(self):
        self.nlp = get_spacy_nlp()
        self.phonetic_gen = PhoneticVariationGenerator()

    def infer_category(self, term_doc, sentence_doc) -> str:
        """Infere a categoria do termo analisando os verbos e o contexto da sentença."""
        if not sentence_doc:
            return "AGRONEGOCIO"

        # Analisa os lemas dos verbos presentes na sentença
        verb_lemmas = {token.lemma_.lower() for token in sentence_doc if token.pos_ in ("VERB", "AUX")}

        for category, target_verbs in CATEGORY_VERB_MAP.items():
            if verb_lemmas.intersection(target_verbs):
                return category

        # Checagens por palavras-chave zootécnicas / industriais
        sent_lower = sentence_doc.text.lower()
        if any(w in sent_lower for w in ["frango", "ave", "lote", "aviário", "granja", "ração", "peso"]):
            return "ZOOTECNIA"
        if any(w in sent_lower for w in ["software", "sistema", "mtech", "amino", "erp", "app"]):
            return "SISTEMAS"
        if any(w in sent_lower for w in ["silo", "sensor", "balança", "câmara", "painel", "exaustor"]):
            return "EQUIPAMENTO"
        if any(w in sent_lower for w in ["caminhão", "abatedouro", "entrega", "transporte", "rota"]):
            return "LOGISTICA"

        return "AGRONEGOCIO"

    def extract_candidate_terms_from_texts(
        self,
        texts_with_context: List[Dict[str, str]],
        existing_terms: Optional[Set[str]] = None,
        min_occurrences: int = 1,
    ) -> List[TermSuggestion]:
        """Varre uma lista de textos de mensagens e extrai candidatos a termos técnicos com spaCy."""
        if not self.nlp or not texts_with_context:
            return []

        existing_lower = {t.lower() for t in (existing_terms or set())}
        term_counter: Counter = Counter()
        term_contexts: Dict[str, List[str]] = {}
        term_categories: Dict[str, List[str]] = {}

        for item in texts_with_context:
            text = item.get("text", "")
            speaker = item.get("speaker", "")
            if not text or len(text.strip()) < 5:
                continue

            doc = self.nlp(text)

            # 1. Extrai sintagmas nominais (noun chunks)
            for chunk in doc.noun_chunks:
                chunk_clean = chunk.text.strip()
                chunk_lower = chunk_clean.lower()

                # Ignora stopwords puras ou pronomes
                words = [w for w in chunk_lower.split() if w not in COMMON_STOPWORDS]
                if not words or len(chunk_clean) < 3:
                    continue

                # Ignora números puros ou termos já cadastrados
                if chunk_clean.isdigit() or chunk_lower in existing_lower:
                    continue

                # Seleciona sintagmas técnicos com boa densidade:
                # Ex: 'pressão estática', 'sensor de silo', 'curva de crescimento', 'ração peletizada'
                has_noun = any(t.pos_ in ("NOUN", "PROPN") for t in chunk)
                if has_noun and len(words) <= 4:
                    canonical_term = " ".join([w.capitalize() if idx == 0 or w not in ("de", "do", "da", "dos", "das") else w for idx, w in enumerate(chunk_clean.split())])
                    term_counter[canonical_term] += 1
                    
                    if canonical_term not in term_contexts:
                        term_contexts[canonical_term] = []
                        term_categories[canonical_term] = []

                    if len(term_contexts[canonical_term]) < 3:
                        term_contexts[canonical_term].append(f"{speaker}: \"{text}\"" if speaker else f"\"{text}\"")

                    category = self.infer_category(chunk, doc)
                    term_categories[canonical_term].append(category)

            # 2. Extrai siglas ou nomes próprios técnicos em maiúsculas (ex: GASP, FMIM, BRIM, TMS)
            for token in doc:
                t_text = token.text.strip()
                if t_text.isupper() and len(t_text) in (3, 4, 5) and t_text.lower() not in existing_lower:
                    if t_text not in COMMON_STOPWORDS:
                        term_counter[t_text] += 2  # Siglas recebem peso maior
                        if t_text not in term_contexts:
                            term_contexts[t_text] = []
                            term_categories[t_text] = []
                        if len(term_contexts[t_text]) < 3:
                            term_contexts[t_text].append(f"{speaker}: \"{text}\"" if speaker else f"\"{text}\"")
                        term_categories[t_text].append(self.infer_category(token, doc))

        # Compila os resultados finais ordenados por relevância
        suggestions: List[TermSuggestion] = []
        for term, count in term_counter.most_common(25):
            if count < min_occurrences:
                continue

            # Categoria mais votada
            cats = term_categories.get(term, ["AGRONEGOCIO"])
            dominant_category = Counter(cats).most_common(1)[0][0] if cats else "AGRONEGOCIO"

            # Gera variações fonéticas com o gerador spaCy
            phonetics = self.phonetic_gen.generate(term)

            # Calcula score de relevância técnica
            confidence = min(0.98, 0.70 + (count * 0.05))

            suggestions.append(
                TermSuggestion(
                    term=term,
                    phonetic_variations=phonetics,
                    category=dominant_category,
                    expansion=f"Termo técnico identificado automaticamente via spaCy ({dominant_category}).",
                    frequency=count,
                    sample_contexts=term_contexts.get(term, []),
                    confidence_score=round(confidence, 2),
                )
            )

        return suggestions


spacy_term_miner = SpacyTermMiner()
phonetic_variation_generator = PhoneticVariationGenerator()
