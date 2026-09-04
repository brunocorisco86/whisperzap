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
    is_yesterday: bool = False
    time_filter_mode: Optional[str] = None  # "today", "yesterday", "recent", None
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

        is_today = any(t in ("hoje", "atual") for t in raw_tokens) or ("de hoje" in raw_query.lower())
        is_yesterday = ("ontem" in raw_tokens) or ("de ontem" in raw_query.lower())
        is_recent = is_today or is_yesterday or any(t in ("recente", "recentemente", "ultimamente", "agora") for t in raw_tokens)

        time_filter_mode = None
        if is_today:
            time_filter_mode = "today"
        elif is_yesterday:
            time_filter_mode = "yesterday"
        elif is_recent:
            time_filter_mode = "recent"

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

        # 4.1 Resolução de Relações Familiares e Afetivas (Esposa, Mãe, Sogra, Sogro)
        FAMILY_RELATION_DEFINITIONS = {
            "esposa": ("Debora", "Debora Patel", ["esposa", "mulher", "patroa", "amor"]),
            "mae": ("Jussara", "Jussara Conter", ["mãe", "mae", "mamae", "mamãe"]),
            "sogra": ("Joceli", "Joceli Patel", ["sogra"]),
            "sogro": ("Dirceu", "Dirceu Patel", ["sogro"]),
        }
        FAMILY_WORDS_SET = {
            "esposa", "mulher", "patroa", "esposas", "mulheres",
            "mãe", "mae", "maes", "mães", "mamae", "mamãe",
            "sogra", "sogras", "sogro", "sogros",
            "pai", "pais", "filho", "filha", "filhos", "filhas",
            "irmão", "irmao", "irmã", "irma"
        }

        query_lower_str = raw_query.lower()
        family_found = False

        for rel_key, (def_first, def_full, kws) in FAMILY_RELATION_DEFINITIONS.items():
            # Casamento estrito de palavras-chave familiares
            matched_kw = False
            for kw in kws:
                if " " in kw:
                    if kw in query_lower_str:
                        matched_kw = True
                        break
                else:
                    if kw in raw_tokens:
                        matched_kw = True
                        break

            if matched_kw:
                matched_speaker = def_first
                matched_full_name = def_full
                family_found = True

                # Se db disponível, busca confirmação e enriquecimento nas tags dos contatos familiares
                if db is not None:
                    try:
                        from src.contacts.models import ContactRecord
                        if rel_key == "esposa":
                            c = db.query(ContactRecord).filter(
                                ContactRecord.role.in_(["FAMILY_CORE", "FAMILY"]),
                                (
                                    (ContactRecord.notes.ilike("%esposa%"))
                                    | (ContactRecord.nickname == "Amor")
                                    | (ContactRecord.name.ilike("%débora%"))
                                    | (ContactRecord.name.ilike("%debora%"))
                                )
                            ).first()
                            if c:
                                matched_speaker = "Debora"
                                matched_full_name = "Debora Patel"
                        elif rel_key == "mae":
                            c = db.query(ContactRecord).filter(
                                ContactRecord.role.in_(["FAMILY_CORE", "FAMILY"]),
                                (
                                    (ContactRecord.nickname.ilike("%mãe%"))
                                    | (ContactRecord.nickname.ilike("%mae%"))
                                    | (ContactRecord.notes.ilike("%mãe%"))
                                    | (ContactRecord.name.ilike("%jussara%"))
                                )
                            ).first()
                            if c:
                                matched_speaker = "Jussara"
                                matched_full_name = "Jussara Conter"
                        elif rel_key == "sogra":
                            c = db.query(ContactRecord).filter(
                                ContactRecord.role.in_(["FAMILY_CORE", "FAMILY"]),
                                (
                                    (ContactRecord.nickname.ilike("%sogra%"))
                                    | (ContactRecord.notes.ilike("%sogra%"))
                                    | (ContactRecord.name.ilike("%joceli%"))
                                )
                            ).first()
                            if c:
                                matched_speaker = "Joceli"
                                matched_full_name = "Joceli Patel"
                        elif rel_key == "sogro":
                            c = db.query(ContactRecord).filter(
                                ContactRecord.role.in_(["FAMILY_CORE", "FAMILY"]),
                                (
                                    (ContactRecord.notes.ilike("%sogro%"))
                                    | (ContactRecord.name.ilike("%dirceu%"))
                                )
                            ).first()
                            if c:
                                matched_speaker = "Dirceu"
                                matched_full_name = "Dirceu Patel"
                    except Exception as exc:
                        logger.debug(f"Aviso ao consultar tags familiares no banco: {exc}")
                break

        # 4.2 Se não for parentesco familiar, executa busca e ranking ponderado de contatos
        if not family_found and db is not None:
            from src.contacts.models import ContactRecord
            from src.memory.models import MessageRecord

            all_contacts = db.query(ContactRecord).all()
            distinct_speakers = [s[0] for s in db.query(MessageRecord.speaker).distinct().all() if s[0]]

            candidate_names = spacy_persons + clean_tokens
            best_match = None
            best_score = 0

            for cand in candidate_names:
                cand_lower = cand.lower()
                if cand_lower in FAMILY_WORDS_SET or len(cand_lower) < 3:
                    continue

                # A. Prioridade Máxima: locutores com mensagens já registradas
                for spk in distinct_speakers:
                    spk_lower = spk.lower()
                    spk_parts = spk_lower.split()
                    spk_first = spk_parts[0] if spk_parts else ""

                    if cand_lower == spk_lower:
                        score = 150
                    elif cand_lower == spk_first:
                        score = 120
                    elif len(cand_lower) >= 4 and any(cand_lower == p for p in spk_parts):
                        score = 100
                    else:
                        score = 0

                    if score > best_score:
                        best_score = score
                        best_match = (spk_first.capitalize(), spk)

                # B. Contatos da Agenda (vCard e cadastrados)
                for c in all_contacts:
                    c_name_lower = (c.name or "").lower()
                    c_parts = c_name_lower.split()
                    c_first = c_parts[0] if c_parts else ""
                    c_nick = (c.nickname or "").lower()

                    score = 0
                    chosen_first = c_first.capitalize()
                    chosen_full = c.name

                    if cand_lower == c_nick and c_nick:
                        score = 140
                    elif cand_lower == c_name_lower:
                        score = 130
                    elif cand_lower == c_first:
                        score = 110
                    elif len(cand_lower) >= 4 and any(cand_lower == p for p in c_parts):
                        # Match em palavra intermediária do nome (ex: "Débora" em "Jair DEBORA SCHLEMMER")
                        # NUNCA usa o primeiro nome prefixo do contato se a busca foi por outra palavra!
                        score = 50
                        chosen_first = cand.capitalize()
                        chosen_full = f"{cand.capitalize()} ({c.name})"

                    if score > best_score:
                        best_score = score
                        best_match = (chosen_first, chosen_full)

            if best_match:
                matched_speaker, matched_full_name = best_match

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
        clean_seeds_list: List[str] = []
        if matched_full_name:
            clean_seeds_list.append(matched_full_name)
        elif matched_speaker:
            clean_seeds_list.append(matched_speaker)

        for dt in matched_domain_terms:
            if dt["term"] not in clean_seeds_list:
                clean_seeds_list.append(dt["term"])

        for org in spacy_orgs_and_misc:
            if org.lower() not in CONVERSATIONAL_STOPWORDS and org not in clean_seeds_list:
                clean_seeds_list.append(org)

        for tok in clean_tokens:
            if tok not in CONVERSATIONAL_STOPWORDS and len(tok) >= 4:
                cap_tok = tok.capitalize()
                if cap_tok not in clean_seeds_list:
                    clean_seeds_list.append(cap_tok)

        return ParsedHermesQuery(
            raw_query=raw_query,
            intent=intent,
            target_speaker=matched_speaker,
            target_speaker_full_name=matched_full_name,
            domain_terms=matched_domain_terms,
            clean_seed_entities=clean_seeds_list[:10],
            is_recent=is_recent,
            is_today=is_today,
            is_yesterday=is_yesterday,
            time_filter_mode=time_filter_mode,
        )


# Instância singleton
hermes_query_understanding = HermesQueryUnderstanding()
