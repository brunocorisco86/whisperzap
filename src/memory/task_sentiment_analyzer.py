"""Módulo de Análise Linguística e de Sentimento de Tarefas com spaCy.

Extrai características sintáticas, morfossintáticas e de sentimento para
distinguir tarefas genuínas de ruídos de conversação, observações descritivas
e relatos de status ignorados pelo usuário.
"""

import logging
import re
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)

# Carregamento resiliente do spaCy
_nlp = None


def get_spacy_nlp():
    """Carrega o pipeline spaCy para português com fallback seguro."""
    global _nlp
    if _nlp is not None:
        return _nlp

    try:
        import spacy
        _nlp = spacy.load("pt_core_news_sm")
        logger.info("Modelo spaCy 'pt_core_news_sm' carregado com sucesso.")
    except Exception as e:
        logger.warning(f"Não foi possível carregar pt_core_news_sm: {e}. Usando spaCy blank('pt').")
        try:
            import spacy
            _nlp = spacy.blank("pt")
        except Exception:
            _nlp = None

    return _nlp


class TaskSentimentAnalyzer:
    """Analisador de sentimento e viabilidade acionável de tarefas extraídas."""

    # Verbos acionáveis comuns em português (lemmas)
    ACTION_VERB_LEMMAS = {
        "agendar", "alinhar", "analisar", "apontar", "aprovar", "assinar", "atualizar",
        "auditar", "buscar", "cadastrar", "calcular", "calibrar", "cancelar", "chamar",
        "cobrar", "coletar", "comprar", "conferir", "configurar", "confirmar", "consertar",
        "consultar", "contatar", "contratar", "controlar", "corrigir", "cotar", "criar",
        "definir", "delegar", "desenvolver", "emitir", "entregar", "enviar", "escrever",
        "estruturar", "examinar", "executar", "falar", "fazer", "fechar", "finalizar",
        "gerar", "implantar", "implementar", "informar", "instalar", "investigar", "lembrar",
        "liberar", "ligar", "limpar", "mandar", "mapear", "monitorar", "montar", "notificar",
        "organizar", "pagar", "passar", "pedir", "planejar", "preparar", "processar",
        "programar", "publicar", "realizar", "receber", "recolher", "reestruturar",
        "registrar", "regular", "reivindicar", "reparar", "repassar", "responder",
        "revisar", "solicitar", "testar", "transferir", "validar", "verificar", "visitar",
    }

    # Marcadores de atualização de status / espera passiva
    STATUS_UPDATE_PATTERNS = [
        r"\b(ainda\s+n[ãa]o\s+(me\s+)?(deram|responderam|entregaram))\b",
        r"\b(t[oô]\s+no\s+(abatedouro|escrit[oó]rio|trânsito|hospital|carro|campo))\b",
        r"\b(estou\s+(esperando|aguardando|na\s+espera))\b",
        r"\b(era\s+pra\s+(hoje|ontem)\s+foi\s+pra)\b",
        r"\b(j[aá]\s+(foi\s+feita?|conclu[ií]do|resolvido|entregue))\b",
        r"\b(n[ãa]o\s+sei\s+n[ãa]o)\b",
        r"\b(s[oó]\s+avisando|passando\s+pra\s+avisar)\b",
    ]

    # Marcadores hipotéticos / condicionais / conselhos vagos
    HYPOTHETICAL_PATTERNS = [
        r"\b(a\s+menos\s+que\s+(eles\s+)?(exijam|pe[çc]am|falem))\b",
        r"\b(se\s+caso\s+(der|for|precisar))\b",
        r"\b(talvez\s+(seja|d[eê]|possa))\b",
        r"\b(acho\s+que\s+(n[ãa]o|d[aá]))\b",
        r"\b(tenta\s+falar\s+com\s+.*que\s+ela\s+pode)\b",
    ]

    # Marcadores de conversas de roadmap / ideias conceituais sem compromisso
    ROADMAP_CHAT_PATTERNS = [
        r"\b(t[aá]\s+no\s+roadmap)\b",
        r"\b(pra\s+mostrar\s+quem\s+mais\s+t[aá]\s+gerando)\b",
        r"\b(seria\s+legal\s+(se|fazer))\b",
        r"\b(ideia\s+futura|no\s+futuro)\b",
        r"\b(pensando\s+em\s+fazer)\b",
    ]

    # Léxico de sentimento e polaridade
    SENTIMENT_LEXICON = {
        "positivo": {
            "ótimo", "excelente", "perfeito", "maravilha", "obrigado", "valeu", "parabéns",
            "sucesso", "aprovado", "concluído", "rápido", "show", "combinado", "certo",
        },
        "negativo_urgente": {
            "urgente", "problema", "erro", "falha", "crítico", "parado", "quebrou", "estragou",
            "atrasado", "prejuízo", "vazando", "risco", "morte", "alerta",
        },
        "passivo_frustracao": {
            "ainda", "esperando", "ninguém", "demora", "não me deram", "travado",
            "complicado", "difícil", "não sei", "enrolado", "esqueceram",
        },
    }

    def __init__(self):
        self.nlp = get_spacy_nlp()

    def analyze_task_text(self, title: str, source_text: str = "") -> Dict[str, Any]:
        """Realiza análise profunda sintática, léxica e de sentimento da tarefa."""
        clean_title = (title or "").strip()
        clean_source = (source_text or "").strip()
        combined_text = f"{clean_title}. {clean_source}".strip()

        # 1. Análise spaCy
        doc_title = self.nlp(clean_title) if (self.nlp and clean_title) else None
        doc_source = self.nlp(clean_source) if (self.nlp and clean_source) else None

        # Contagem de tokens e verbos
        tokens_title = [t for t in doc_title] if doc_title else []
        verb_tokens_title = [t for t in tokens_title if t.pos_ in ("VERB", "AUX")] if doc_title else []
        root_token_title = [t for t in tokens_title if t.dep_ == "ROOT"] if doc_title else []
        root_pos_title = root_token_title[0].pos_ if root_token_title else "UNKNOWN"
        root_lemma_title = root_token_title[0].lemma_.lower() if root_token_title else ""

        tokens_source = [t for t in doc_source] if doc_source else []
        verb_tokens_source = [t for t in tokens_source if t.pos_ in ("VERB", "AUX")] if doc_source else []
        root_token_source = [t for t in tokens_source if t.dep_ == "ROOT"] if doc_source else []
        root_pos_source = root_token_source[0].pos_ if root_token_source else "UNKNOWN"

        # Verifica se o ROOT ou os verbos são acionáveis no título e na mensagem de origem
        has_action_verb = any(t.lemma_.lower() in self.ACTION_VERB_LEMMAS for t in verb_tokens_title)
        if not has_action_verb and root_lemma_title in self.ACTION_VERB_LEMMAS:
            has_action_verb = True

        has_action_verb_source = any(t.lemma_.lower() in self.ACTION_VERB_LEMMAS for t in verb_tokens_source)

        word_count_source = len(clean_source.split())
        word_count_title = len(clean_title.split())

        # Detecta frases puramente nominais / observações isoladas no texto de origem
        source_is_pure_observation = (
            word_count_source > 0
            and word_count_source <= 6
            and not has_action_verb_source
            and root_pos_source in ("NOUN", "PROPN", "ADJ", "UNKNOWN")
        )

        # 2. Padrões de Ruído Específicos
        noise_category = None
        for pattern in self.STATUS_UPDATE_PATTERNS:
            if re.search(pattern, combined_text, re.IGNORECASE):
                noise_category = "STATUS_UPDATE"
                break

        if not noise_category:
            for pattern in self.HYPOTHETICAL_PATTERNS:
                if re.search(pattern, combined_text, re.IGNORECASE):
                    noise_category = "HYPOTHETICAL_ADVICE"
                    break

        if not noise_category:
            for pattern in self.ROADMAP_CHAT_PATTERNS:
                if re.search(pattern, combined_text, re.IGNORECASE):
                    noise_category = "ROADMAP_CHAT"
                    break

        if not noise_category and source_is_pure_observation:
            noise_category = "FIELD_OBSERVATION_FRAGMENT"

        # 3. Sentimento e Polaridade
        text_lower = combined_text.lower()
        pos_hits = sum(1 for w in self.SENTIMENT_LEXICON["positivo"] if w in text_lower)
        neg_urg_hits = sum(1 for w in self.SENTIMENT_LEXICON["negativo_urgente"] if w in text_lower)
        pass_hits = sum(1 for w in self.SENTIMENT_LEXICON["passivo_frustracao"] if w in text_lower)

        if neg_urg_hits > 0:
            sentiment_tone = "URGENT_PROBLEM"
            sentiment_polarity = -0.6
        elif pass_hits > 0:
            sentiment_tone = "PASSIVE_WAITING"
            sentiment_polarity = -0.4
        elif pos_hits > 0:
            sentiment_tone = "POSITIVE_ALIGNED"
            sentiment_polarity = 0.6
        else:
            sentiment_tone = "NEUTRAL"
            sentiment_polarity = 0.0

        # 4. Cálculo do Escore de Acionabilidade (0.0 a 1.0)
        actionability_score = 0.65  # Base

        if has_action_verb:
            actionability_score += 0.25
        else:
            actionability_score -= 0.30

        if noise_category == "STATUS_UPDATE":
            actionability_score -= 0.45
        elif noise_category == "FIELD_OBSERVATION_FRAGMENT":
            actionability_score -= 0.40
        elif noise_category == "ROADMAP_CHAT":
            actionability_score -= 0.35
        elif noise_category == "HYPOTHETICAL_ADVICE":
            actionability_score -= 0.30

        # Penalidade para fragmentos curtíssimos sem verbo
        if word_count_source <= 3 and not has_action_verb:
            actionability_score -= 0.25

        # Bônus para datas ou prazos explícitos
        if re.search(r"\b(amanh[ãa]|segunda|ter[çc]a|quarta|quinta|sexta|s[áa]bado|domingo|hoje|[0-9]{1,2}/[0-9]{1,2}|at[ée]\s+[0-9]+)\b", combined_text, re.IGNORECASE):
            actionability_score += 0.15

        actionability_score = max(0.0, min(1.0, round(actionability_score, 2)))

        return {
            "title": clean_title,
            "source_snippet": clean_source,
            "root_pos": root_pos_title,
            "root_lemma": root_lemma_title,
            "has_action_verb": has_action_verb,
            "is_pure_noun_phrase": source_is_pure_observation,
            "noise_category": noise_category,
            "sentiment_tone": sentiment_tone,
            "sentiment_polarity": sentiment_polarity,
            "actionability_score": actionability_score,
            "is_likely_noise": (actionability_score < 0.45 or noise_category is not None),
        }

    def is_actionable_task(self, title: str, source_text: str = "", threshold: float = 0.45) -> bool:
        """Determina se uma tarefa extraída é suficientemente acionável para ser salva no banco."""
        analysis = self.analyze_task_text(title, source_text)
        return analysis["actionability_score"] >= threshold and analysis["noise_category"] is None

    def extract_task_tags(
        self,
        title: str,
        source_text: str = "",
        existing_entities: Optional[List[str]] = None,
        priority: Optional[str] = None,
    ) -> List[str]:
        """Extrai tags contextuais da tarefa via spaCy NLP e dicionário de domínio (zero custo de API)."""
        tags: List[str] = []
        clean_title = (title or "").strip()
        clean_source = (source_text or "").strip()
        full_text = f"{clean_title}. {clean_source}".strip()

        if not full_text:
            return tags

        # 1. Tags de domínio Agro / Logística / Corporativo baseadas em palavras-chave e lemas
        domain_keywords_map = {
            "Logística": ["logistica", "entrega", "transporte", "caminhao", "frete", "embarque", "descarga", "rota", "expedicao", "rastreio"],
            "Ração": ["racao", "farelo", "milho", "soja", "nutricao", "alimentacao", "fabrica de racao"],
            "Silos": ["silo", "silos", "armazenamento", "sensor", "capacidade", "nivel de silo", "abastecimento"],
            "Granja": ["granja", "aviario", "galpao", "lote", "aves", "frango", "pintainho", "produtor"],
            "TMS": ["tms", "sistema de transporte", "despacho", "gestao de frotas"],
            "C.Vale": ["cvale", "c.vale", "cooperativa", "cooperado", "associado"],
            "Financeiro": ["financeiro", "pagamento", "boleto", "nota fiscal", "nf", "faturamento", "cobranca", "banco", "custo", "preco", "orcamento"],
            "Reunião": ["reuniao", "alinhamento", "call", "encontro", "briefing", "conversa", "pauta"],
            "Contratos": ["contrato", "acordo", "termo", "assinatura", "juridico", "clausula"],
            "Compras": ["compra", "cotacao", "fornecedor", "aquisicao", "pedido de compra"],
            "Manutenção": ["manutencao", "reparo", "conserto", "calibracao", "eletrica", "mecanica", "peca", "troca"],
            "Qualidade": ["qualidade", "auditoria", "laudo", "inspecao", "padrao", "conformidade"],
            "Abatedouro": ["abatedouro", "frigorifico", "abate", "rendimento", "pesagem", "evisceracao"],
            "TI & Automação": ["sistema", "servidor", "api", "software", "dashboard", "banco de dados", "integracao", "n8n", "evolution", "homelab"],
        }

        from src.ai_gateway.bypass import normalize_text
        norm_text = normalize_text(full_text)

        for tag_label, kw_list in domain_keywords_map.items():
            for kw in kw_list:
                kw_norm = normalize_text(kw)
                if re.search(r"\b" + re.escape(kw_norm) + r"\b", norm_text):
                    if tag_label not in tags:
                        tags.append(tag_label)
                    break

        # 2. Entidades nomeadas spaCy (NER)
        if self.nlp:
            try:
                doc = self.nlp(clean_title)
                for ent in doc.ents:
                    ent_text = ent.text.strip()
                    if ent.label_ in ("ORG", "LOC", "MISC", "PER") and len(ent_text) >= 3:
                        # Limpa pontuações e artigos
                        ent_clean = re.sub(r"^[oOaAeEmMdD]s?\s+", "", ent_text).strip().title()
                        if ent_clean and ent_clean not in tags and len(ent_clean) >= 3:
                            if len(tags) < 6:
                                tags.append(ent_clean)
            except Exception as e:
                logger.debug(f"Erro ao extrair entidades spaCy para tags: {e}")

        # 3. Entidades já extraídas passadas explicitamente
        if existing_entities:
            for ent_str in existing_entities:
                if ent_str and len(ent_str.strip()) >= 3:
                    clean_ent = ent_str.strip().title()
                    if clean_ent not in tags and len(tags) < 6:
                        tags.append(clean_ent)

        # 4. Tag de Prioridade / Urgência
        if priority and priority.upper() in ("URGENT", "HIGH"):
            p_tag = "⚡ Urgente" if priority.upper() == "URGENT" else "🔥 Alta Prioridade"
            if p_tag not in tags:
                tags.insert(0, p_tag)

        # Fallback genérico se nenhuma tag foi encontrada
        if not tags:
            tags.append("Operacional")

        return tags[:5]

    def compute_task_similarity(
        self,
        title_a: str,
        notes_a: str,
        title_b: str,
        notes_b: str,
    ) -> float:
        """Calcula similaridade lexical e semântica entre duas tarefas com spaCy e SequenceMatcher."""
        import difflib
        from src.ai_gateway.bypass import normalize_text

        text_a = f"{title_a or ''} {notes_a or ''}".strip()
        text_b = f"{title_b or ''} {notes_b or ''}".strip()

        if not text_a or not text_b:
            return 0.0

        norm_a = normalize_text(text_a)
        norm_b = normalize_text(text_b)

        # 1. Similaridade direta de caracteres (SequenceMatcher)
        seq_sim = difflib.SequenceMatcher(None, norm_a, norm_b).ratio()

        # 2. Similaridade de Jaccard sobre lemas / tokens significativos
        tokens_a = set()
        tokens_b = set()

        if self.nlp:
            try:
                doc_a = self.nlp(text_a)
                doc_b = self.nlp(text_b)
                tokens_a = {t.lemma_.lower() for t in doc_a if not t.is_stop and not t.is_punct and len(t.text) > 2}
                tokens_b = {t.lemma_.lower() for t in doc_b if not t.is_stop and not t.is_punct and len(t.text) > 2}
            except Exception:
                tokens_a = {w for w in norm_a.split() if len(w) > 2}
                tokens_b = {w for w in norm_b.split() if len(w) > 2}
        else:
            tokens_a = {w for w in norm_a.split() if len(w) > 2}
            tokens_b = {w for w in norm_b.split() if len(w) > 2}

        jaccard_sim = 0.0
        if tokens_a and tokens_b:
            intersection = len(tokens_a.intersection(tokens_b))
            union = len(tokens_a.union(tokens_b))
            jaccard_sim = intersection / union if union > 0 else 0.0

        # Ponderação híbrida: 60% Jaccard lemas + 40% SequenceMatcher
        final_sim = (0.60 * jaccard_sim) + (0.40 * seq_sim)
        return round(final_sim, 4)

    def find_similar_existing_task(
        self,
        candidate_title: str,
        candidate_context: str,
        existing_tasks: List[Any],
        similarity_threshold: float = 0.60,
    ) -> Optional[Tuple[Any, float]]:
        """Busca entre as tarefas existentes uma que seja semanticamente equivalente usando spaCy.
        
        Retorna uma tupla (tarefa_existente, score_similaridade) ou None se não houver similaridade suficiente.
        """
        if not candidate_title or not existing_tasks:
            return None

        best_match = None
        highest_sim = 0.0

        for task in existing_tasks:
            task_title = getattr(task, "title", "") or ""
            task_notes = getattr(task, "notes", "") or ""
            sim = self.compute_task_similarity(
                candidate_title, candidate_context, task_title, task_notes
            )
            if sim >= similarity_threshold and sim > highest_sim:
                highest_sim = sim
                best_match = task

        if best_match is not None:
            return (best_match, highest_sim)
        return None


task_sentiment_analyzer = TaskSentimentAnalyzer()
