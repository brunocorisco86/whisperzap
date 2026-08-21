"""Módulo de Entendimento Inteligente e Pré-Processamento de Consultas para o Oráculo Melpômene (Hermes Q&A).

Combina análise sintática e morfossintática do spaCy com o Dicionário Léxico de Polímnia
e a base de contatos para extrair intenções, interlocutores, termos de domínio e pistas temporais.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from src.dictionary.service import dictionary_service
from src.memory.task_sentiment_analyzer import get_spacy_nlp

logger = logging.getLogger(__name__)

# Stopwords conversacionais e funcionais em português para descarte
CONVERSATIONAL_STOPWORDS: Set[str] = {
    "que", "para", "com", "como", "onde", "qual", "quais", "quem", "hoje", "ontem",
    "amanha", "amanhã", "queria", "disse", "pediu", "falou", "conversou", "conversa",
    "conversando", "recente", "recentemente", "sobre", "comigo", "contigo", "dele", "dela",
    "eles", "elas", "meu", "minha", "nosso", "nossa", "isso", "aquilo", "estava", "estou",
    "estao", "tudo", "nada", "mais", "menos", "algum", "alguma", "falar", "saber", "passar",
    "me", "te", "se", "lhe", "nos", "vos", "lhes", "voce", "você", "sr", "sra", "viu", "olha",
    "por", "favor", "dar", "tem", "ha", "há", "quando", "porque", "porquê", "tipo", "coisa"
}

DIALOGUE_VERB_LEMMAS: Set[str] = {
    "conversar", "falar", "dizer", "pedir", "mandar", "avisar", "comentar", "perguntar",
    "solicitar", "discutir", "alinhar", "reclamar", "tratar", "explicar", "relatar", "passar"
}

TASK_LOOKUP_LEMMAS: Set[str] = {
    "tarefa", "pendencia", "pendência", "prazo", "afazer", "acao", "ação", "fazer", "entregar",
    "ficar", "combinado", "acordo", "prioridade", "aberto", "fechado"
}


@dataclass
class ParsedHermesQuery:
    """Estrutura semântica resultante da análise da pergunta."""
    raw_query: str
    intent: str  # "INTERLOCUTOR_DIALOGUE", "CONCEPT_STATUS", "TASK_LOOKUP", "TIME_FILTER", "GENERAL"
    target_speaker: Optional[str] = None
    target_speaker_full_name: Optional[str] = None
    domain_terms: List[Dict[str, Any]] = field(default_factory=list)
    clean_seed_entities: List[str] = field(default_factory=list)
    is_recent: bool = False
    is_today: bool = False
    action_focus: Optional[str] = None


class HermesQueryUnderstanding:
    """Motor de interpretação morfossintática e semântica de consultas."""

    def __init__(self):
        self.nlp = get_spacy_nlp()
        self.dict_service = dictionary_service

    def analyze_query(self, query: str, db: Optional[Any] = None) -> ParsedHermesQuery:
        """Executa a análise completa da pergunta do usuário."""
        raw_query = query.strip()
        if not raw_query:
            return ParsedHermesQuery(raw_query="", intent="GENERAL")

        # 1. Análise Léxica de Tokens e Pistas Temporais
        raw_tokens = [w for w in re.findall(r"\w+", raw_query.lower()) if len(w) >= 2]
        clean_tokens = [w for w in raw_tokens if w not in CONVERSATIONAL_STOPWORDS and len(w) >= 3]

        is_today = any(t in ("hoje", "atual") for t in raw_tokens)
        is_recent = is_today or any(t in ("recente", "recentemente", "ultimamente", "agora", "ontem") for t in raw_tokens)

        # 2. Análise Morfossintática com spaCy
        spacy_persons: List[str] = []
        spacy_orgs_and_misc: List[str] = []
        dialogue_verb_detected = False
        task_intent_detected = False

        if self.nlp:
            doc = self.nlp(raw_query)
            # Entidades nomeadas formais
            for ent in doc.ents:
                clean_ent = ent.text.strip().strip("\"'“”`.,;:")
                if ent.label_ in ("PER", "PERSON"):
                    spacy_persons.append(clean_ent)
                elif ent.label_ in ("ORG", "LOC", "MISC"):
                    spacy_orgs_and_misc.append(clean_ent)

            # Verbos e dependências
            for token in doc:
                lemma = token.lemma_.lower()
                if lemma in DIALOGUE_VERB_LEMMAS:
                    dialogue_verb_detected = True
                if lemma in TASK_LOOKUP_LEMMAS:
                    task_intent_detected = True

                # Identifica sujeitos próprios mesmo que o NER tenha falhado
                if token.pos_ == "PROPN" and token.dep_ in ("nsubj", "nsubj:pass", "pobj", "obl", "ROOT"):
                    clean_propn = token.text.strip()
                    if clean_propn.lower() not in CONVERSATIONAL_STOPWORDS and len(clean_propn) >= 3:
                        if clean_propn not in spacy_persons:
                            spacy_persons.append(clean_propn)

        # 3. Mapeamento de Domínio com Polímnia (Dicionário Léxico)
        matched_domain_terms: List[Dict[str, Any]] = []
        all_dict_terms = self.dict_service.get_all_terms()

        for term_obj in all_dict_terms:
            t_canonical = term_obj.term
            t_norm = t_canonical.lower()
            all_variants = [t_norm] + [v.lower() for v in (term_obj.phonetic_variations or [])]

            matched = False
            for v in all_variants:
                if " " in v:
                    if v in raw_query.lower():
                        matched = True
                        break
                else:
                    if v in raw_tokens:
                        matched = True
                        break

            if matched:
                matched_domain_terms.append({
                    "term": t_canonical,
                    "expansion": term_obj.expansion,
                    "category": term_obj.category,
                    "description": term_obj.description,
                })

        # 4. Resolução Dinâmica de Interlocutor / Pessoa Alvo
        matched_speaker = None
        matched_full_name = None

        if db is not None:
            from src.contacts.models import ContactRecord
            from src.memory.models import MessageRecord

            all_contacts = db.query(ContactRecord).all()
            distinct_speakers = [s[0] for s in db.query(MessageRecord.speaker).distinct().all() if s[0]]

            # 4.1 Prioriza pessoas extraídas pelo spaCy
            candidate_names = spacy_persons + clean_tokens

            for cand in candidate_names:
                cand_lower = cand.lower()
                # Verifica tabela de contatos
                for c in all_contacts:
                    c_name_lower = (c.name or "").lower()
                    c_first = c_name_lower.split()[0] if c_name_lower else ""
                    c_nick = (c.nickname or "").lower()

                    if cand_lower == c_first or cand_lower == c_nick or cand_lower == c_name_lower or (len(cand_lower) >= 4 and cand_lower in c_name_lower):
                        matched_speaker = c_first.capitalize()
                        matched_full_name = c.name
                        break
                if matched_speaker:
                    break

                # Verifica locutores já existentes nas mensagens
                for spk in distinct_speakers:
                    spk_lower = spk.lower()
                    spk_first = spk_lower.split()[0]
                    if cand_lower == spk_first or cand_lower == spk_lower or (len(cand_lower) >= 4 and cand_lower in spk_lower):
                        matched_speaker = spk_first.capitalize()
                        matched_full_name = spk
                        break
                if matched_speaker:
                    break

        # 5. Classificação de Intenção Global da Pergunta
        if matched_speaker and (dialogue_verb_detected or is_recent or not task_intent_detected):
            intent = "INTERLOCUTOR_DIALOGUE"
        elif task_intent_detected:
            intent = "TASK_LOOKUP"
        elif matched_domain_terms or spacy_orgs_and_misc:
            intent = "CONCEPT_STATUS"
        elif is_today or is_recent:
            intent = "TIME_FILTER"
        else:
            intent = "GENERAL"

        # 6. Sementes Limpas para GraphRAG
        clean_seeds: Set[str] = set()
        if matched_full_name:
            clean_seeds.add(matched_full_name)
        elif matched_speaker:
            clean_seeds.add(matched_speaker)

        for dt in matched_domain_terms:
            clean_seeds.add(dt["term"])

        for org in spacy_orgs_and_misc:
            if org.lower() not in CONVERSATIONAL_STOPWORDS:
                clean_seeds.add(org)

        for tok in clean_tokens:
            if tok not in CONVERSATIONAL_STOPWORDS and len(tok) >= 4:
                clean_seeds.add(tok.capitalize())

        return ParsedHermesQuery(
            raw_query=raw_query,
            intent=intent,
            target_speaker=matched_speaker,
            target_speaker_full_name=matched_full_name,
            domain_terms=matched_domain_terms,
            clean_seed_entities=list(clean_seeds)[:6],
            is_recent=is_recent,
            is_today=is_today,
        )


# Instância singleton
hermes_query_understanding = HermesQueryUnderstanding()
