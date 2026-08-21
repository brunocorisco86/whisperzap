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

    def merge_similar_terms(self, similarity_threshold: float = 0.80) -> list[dict]:
        """Mescla termos semelhantes, duplicados ou flexionados (ex: singular/plural) usando spaCy NLP."""
        import difflib
        from src.ai_gateway.bypass import normalize_text
        from src.memory.task_sentiment_analyzer import get_spacy_nlp

        nlp = get_spacy_nlp()
        term_list = list(self.terms.values())
        if len(term_list) < 2:
            return []

        visited_ids = set()
        merged_clusters = []

        for i, t1 in enumerate(term_list):
            if t1.id in visited_ids:
                continue

            cluster = [t1]
            t1_norm = normalize_text(t1.term)
            t1_lemma = ""
            if nlp:
                try:
                    doc1 = nlp(t1.term)
                    t1_lemma = " ".join([token.lemma_.lower() for token in doc1 if not token.is_punct])
                except Exception:
                    t1_lemma = t1_norm
            else:
                t1_lemma = t1_norm

            t1_vars_norm = {normalize_text(v) for v in t1.phonetic_variations}

            for j, t2 in enumerate(term_list):
                if i == j or t2.id in visited_ids:
                    continue

                t2_norm = normalize_text(t2.term)
                t2_lemma = ""
                if nlp:
                    try:
                        doc2 = nlp(t2.term)
                        t2_lemma = " ".join([token.lemma_.lower() for token in doc2 if not token.is_punct])
                    except Exception:
                        t2_lemma = t2_norm
                else:
                    t2_lemma = t2_norm

                t2_vars_norm = {normalize_text(v) for v in t2.phonetic_variations}

                # Critérios de similaridade para agrupamento:
                # 1. Mesma forma normalizada (independente de maiúsculas/minúsculas e acentos)
                is_same_norm = (t1_norm == t2_norm)

                # 2. Mesmo lema via spaCy (ex: 'silo' e 'silos', 'clorador' e 'cloradores')
                is_same_lemma = bool(t1_lemma and t2_lemma and t1_lemma == t2_lemma)

                # 3. Intersecção de variações fonéticas
                is_in_variations = (t2_norm in t1_vars_norm or t1_norm in t2_vars_norm)

                # 4. Alta similaridade de caracteres (SequenceMatcher >= threshold)
                char_ratio = difflib.SequenceMatcher(None, t1_norm, t2_norm).ratio()
                is_fuzzy_similar = (char_ratio >= similarity_threshold and len(t1_norm) >= 4 and len(t2_norm) >= 4)

                if is_same_norm or is_same_lemma or is_in_variations or is_fuzzy_similar:
                    cluster.append(t2)
                    visited_ids.add(t2.id)

            if len(cluster) > 1:
                visited_ids.add(t1.id)

                # Determina termo canônico ideal
                # Preferência: 1. Sigla em maiúsculas (ex: FAL, TMS) 2. TitleCase 3. Termo com mais metadados
                def score_canonical(term_obj: DictionaryTerm) -> int:
                    score = 0
                    raw = term_obj.term
                    if raw.isupper() and len(raw) <= 6:
                        score += 50
                    elif raw[0].isupper() if raw else False:
                        score += 25
                    if term_obj.expansion:
                        score += 20
                    if term_obj.description:
                        score += 10
                    if term_obj.category and term_obj.category.upper() != "GERAL":
                        score += 15
                    score += len(term_obj.phonetic_variations)
                    return score

                cluster.sort(key=score_canonical, reverse=True)
                canonical = cluster[0]

                # Consolida metadados de todos os termos do cluster
                all_variations = set(canonical.phonetic_variations)
                merged_term_names = []

                for other in cluster[1:]:
                    merged_term_names.append(other.term)
                    # Adiciona o próprio nome do termo secundário como variação do canônico
                    if other.term.lower() != canonical.term.lower():
                        all_variations.add(other.term)
                    all_variations.update(other.phonetic_variations)

                    # Preserva expansão se a canônica não tiver
                    if other.expansion and not canonical.expansion:
                        canonical.expansion = other.expansion

                    # Preserva descrição se a canônica não tiver
                    if other.description:
                        if not canonical.description:
                            canonical.description = other.description
                        elif other.description not in canonical.description:
                            canonical.description = f"{canonical.description} | {other.description}"

                    # Preserva categoria especializada
                    if other.category and other.category.upper() != "GERAL" and canonical.category == "GERAL":
                        canonical.category = other.category

                    # Remove termo secundário
                    if other.id in self.terms:
                        del self.terms[other.id]

                # Limpa e formata as variações fonéticas consolidadas
                all_variations.discard(canonical.term)
                canonical.phonetic_variations = sorted(list(all_variations))
                self.terms[canonical.id] = canonical

                merged_clusters.append({
                    "canonical_term": canonical.term,
                    "merged_terms": merged_term_names,
                    "phonetic_variations_total": len(canonical.phonetic_variations),
                    "category": canonical.category,
                })

        if merged_clusters:
            self._save()

        return merged_clusters

    def get_available_categories(self) -> list[dict]:
        """Retorna as categorias dinâmicas disponíveis com contagem de termos ativos."""
        counts = {}
        for t in self.terms.values():
            cat = t.category.upper() if t.category else "GERAL"
            counts[cat] = counts.get(cat, 0) + 1

        result = []
        # Adiciona categorias conhecidas do registro
        for code, info in DYNAMIC_CATEGORIES_REGISTRY.items():
            result.append({
                "code": code,
                "label": info["label"],
                "description": info["description"],
                "terms_count": counts.get(code, 0),
            })

        # Adiciona qualquer outra categoria presente nos dados
        known_codes = set(DYNAMIC_CATEGORIES_REGISTRY.keys())
        for cat_code, count in counts.items():
            if cat_code not in known_codes:
                result.append({
                    "code": cat_code,
                    "label": f"📁 {cat_code.title()}",
                    "description": f"Categoria customizada: {cat_code}",
                    "terms_count": count,
                })

        return result

    def rationalize_and_expand_categories(self, max_categories: int = 12) -> dict:
        """Racionaliza e reclassifica os termos do dicionário usando o grafo neural de Urânia e spaCy NLP."""
        from src.ai_gateway.bypass import normalize_text
        from src.memory.graph import knowledge_graph
        from src.memory.task_sentiment_analyzer import get_spacy_nlp

        nlp = get_spacy_nlp()
        reclassified_count = 0

        # Coleta nós e conexões do grafo de Urânia para enriquecimento contextual
        urania_nodes = set(knowledge_graph.graph.nodes()) if knowledge_graph.graph else set()

        for term_obj in self.terms.values():
            old_cat = term_obj.category.upper() if term_obj.category else "GERAL"
            best_cat = "GERAL"
            best_score = 0.0

            # 1. Monta texto completo do termo para análise semântica
            full_text = f"{term_obj.term} {term_obj.expansion or ''} {term_obj.description or ''} {' '.join(term_obj.phonetic_variations)}"
            norm_full = normalize_text(full_text)

            lemmas = set()
            if nlp:
                try:
                    doc = nlp(full_text)
                    lemmas = {token.lemma_.lower() for token in doc if not token.is_punct and not token.is_stop}
                except Exception:
                    lemmas = set(norm_full.split())
            else:
                lemmas = set(norm_full.split())

            # 2. Conhecimento neural do Grafo de Urânia (verifica nós vizinhos e relações)
            graph_boosts = {}
            term_norm = normalize_text(term_obj.term)
            for node in urania_nodes:
                node_norm = normalize_text(node)
                if node_norm in term_norm or term_norm in node_norm:
                    try:
                        neighbors = list(knowledge_graph.graph.neighbors(node))
                        neighbor_text = " ".join([normalize_text(n) for n in neighbors])
                        for cat_code, cat_info in DYNAMIC_CATEGORIES_REGISTRY.items():
                            for kw in cat_info["keywords"]:
                                if kw in neighbor_text:
                                    graph_boosts[cat_code] = graph_boosts.get(cat_code, 0.0) + 1.5
                    except Exception:
                        pass

            # 3. Calcula pontuação para cada categoria dinâmica
            for cat_code, cat_info in DYNAMIC_CATEGORIES_REGISTRY.items():
                if cat_code == "GERAL":
                    continue

                score = 0.0
                keywords = cat_info["keywords"]

                # A. Casamento direto de palavras-chave / lemas
                for kw in keywords:
                    if kw in lemmas:
                        score += 3.0
                    elif kw in norm_full:
                        score += 1.5

                # B. Boost do grafo de Urânia
                score += graph_boosts.get(cat_code, 0.0)

                # C. Mapeamento legado de categorias anteriores
                if old_cat == "ZOOTECNIA" and cat_code in ("ZOOTECNIA_MANEJO", "NUTRICAO_RACAO", "SANIDADE_QUALIDADE", "FRIGORIFICO_ABATE"):
                    score += 0.8
                elif old_cat == "LOGISTICA" and cat_code in ("LOGISTICA_SILOS", "FRIGORIFICO_ABATE"):
                    score += 0.8
                elif old_cat == "SISTEMAS" and cat_code in ("SISTEMAS_ERP", "IA_AUTOMACAO"):
                    score += 0.8
                elif old_cat == "EQUIPAMENTOS" and cat_code in ("AMBIENCIA_CLIMA", "EQUIPAMENTOS_IOT"):
                    score += 0.8
                elif old_cat == "AGRONEGOCIO" and cat_code in ("AGRONEGOCIO_COOP", "FINANCEIRO_GESTAO"):
                    score += 0.8
                elif old_cat == "TECNOLOGIA" and cat_code in ("IA_AUTOMACAO", "SISTEMAS_ERP"):
                    score += 0.8

                if score > best_score:
                    best_score = score
                    best_cat = cat_code

            # Se encontrou uma categoria com pontuação satisfatória (> 1.0) e diferente da atual
            if best_score >= 1.0 and best_cat != old_cat:
                term_obj.category = best_cat
                reclassified_count += 1
            elif old_cat in DYNAMIC_CATEGORIES_REGISTRY:
                term_obj.category = old_cat
            elif old_cat == "ZOOTECNIA":
                term_obj.category = "ZOOTECNIA_MANEJO"
                reclassified_count += 1
            elif old_cat == "LOGISTICA":
                term_obj.category = "LOGISTICA_SILOS"
                reclassified_count += 1
            elif old_cat == "SISTEMAS":
                term_obj.category = "SISTEMAS_ERP"
                reclassified_count += 1
            elif old_cat == "EQUIPAMENTOS":
                term_obj.category = "EQUIPAMENTOS_IOT"
                reclassified_count += 1
            elif old_cat == "AGRONEGOCIO":
                term_obj.category = "AGRONEGOCIO_COOP"
                reclassified_count += 1
            elif old_cat == "TECNOLOGIA":
                term_obj.category = "IA_AUTOMACAO"
                reclassified_count += 1

        if reclassified_count > 0:
            self._save()

        categories_summary = self.get_available_categories()

        return {
            "reclassified_terms_count": reclassified_count,
            "total_categories_count": len(categories_summary),
            "max_categories_limit": max_categories,
            "categories": categories_summary,
            "message": (
                f"{reclassified_count} termo(s) reclassificados em {len(categories_summary)} categorias dinâmicas "
                f"com o Grafo de Urânia e spaCy NLP."
                if reclassified_count > 0
                else f"Categorias já estavam otimizadas ({len(categories_summary)} categorias ativas)."
            ),
        }


# Taxonomia Dinâmica e Registro de Categorias Especializadas (Teto: 12 Categorias)
DYNAMIC_CATEGORIES_REGISTRY = {
    "ZOOTECNIA_MANEJO": {
        "label": "🐥 Zootecnia & Manejo de Lotes",
        "description": "FAL, Pintainhos, Alojamento, IEP, Mortalidade, Densidade, CA e pesagens",
        "keywords": {"fal", "lote", "aves", "pintainho", "pintinho", "iep", "mortalidade", "alojamento", "peso", "zootecnia", "viabilidade", "densidade", "pesagem"},
    },
    "NUTRICAO_RACAO": {
        "label": "🌾 Nutrição & Fábrica de Ração",
        "description": "Formulação, fábrica de ração, farelo, soja, milho, premix, aditivos e conversão alimentar",
        "keywords": {"racao", "nutricao", "conversao", "alimentar", "fabrica", "farelo", "soja", "milho", "premix", "aditivo", "ingrediente", "fmim"},
    },
    "LOGISTICA_SILOS": {
        "label": "🚚 Logística, Frotas & Silos",
        "description": "TMS, Roteirização, Sensores de Silo, Nível de Ração, Frotas, Caminhões e Despacho",
        "keywords": {"tms", "silo", "silos", "logistica", "frota", "caminhao", "entrega", "transporte", "despacho", "motorista", "roteirizador", "capacidade"},
    },
    "AGRONEGOCIO_COOP": {
        "label": "🏛️ Agronegócio & C.Vale",
        "description": "Cooperativa C.Vale, Cooperados, Integrados, Agrocenter, Contratos e Governança",
        "keywords": {"c.vale", "cvale", "sevale", "agrocenter", "cooperativa", "cooperado", "integrado", "associado", "agronegocio", "contrato", "parceria", "assembleia"},
    },
    "SISTEMAS_ERP": {
        "label": "💻 Sistemas, Mtech & ERPs",
        "description": "Mtech Systems, Amino, BRIM, FMIM, eProdutor, Agrocenter ERP, Bancos de Dados e APIs",
        "keywords": {"mtech", "amino", "brim", "fmim", "eprodutor", "software", "sistema", "erp", "banco", "sql", "api", "modulo", "app"},
    },
    "AMBIENCIA_CLIMA": {
        "label": "🌡️ Ambiência & Climatização",
        "description": "Dark House, Pressão Negativa, Exaustores, Placas Evaporativas, Aquecedores e Temperatura",
        "keywords": {"dark", "house", "climatizado", "exaustor", "placa", "evaporativa", "aquecedor", "temperatura", "umidade", "pressao", "negativa", "ventilador", "ambiencia"},
    },
    "EQUIPAMENTOS_IOT": {
        "label": "⚙️ Equipamentos & Telemetria IoT",
        "description": "Cloradores, Dosadores de Cloro, Sensores LoRa, Balanças, Motores e Telemetria",
        "keywords": {"clorador", "dosador", "sensor", "telemetria", "iot", "lora", "balanca", "motor", "equipamento", "maquina", "hardware"},
    },
    "SANIDADE_QUALIDADE": {
        "label": "🛡️ Sanidade & Biosseguridade",
        "description": "Vazio Sanitário, Desinfecção, Vacinas, Biosseguridade, Coletas e Laudos Sanitários",
        "keywords": {"vazio", "sanitario", "desinfeccao", "vacina", "sanidade", "biosseguridade", "laudo", "veterinario", "qualidade", "coleta", "analise", "sangue"},
    },
    "FRIGORIFICO_ABATE": {
        "label": "🍗 Abatedouro & Industrialização",
        "description": "Apanha de Frangos, Programação de Abate, Rendimento de Carcaça e Frigorífico",
        "keywords": {"abate", "apanha", "frigorifico", "industrializacao", "carcaca", "rendimento", "pesagem", "evisceracao", "escaldagem"},
    },
    "FINANCEIRO_GESTAO": {
        "label": "💰 Financeiro & Liquidação",
        "description": "Faturamento, Crédito Rural, Liquidação de Lote, Bonificações, Custos e Pagamentos",
        "keywords": {"financeiro", "liquidacao", "faturamento", "credito", "custo", "pagamento", "preco", "bonificacao", "resultado", "margem"},
    },
    "IA_AUTOMACAO": {
        "label": "🧠 IA, Copiloto Hermes & Homelab",
        "description": "Hermes Voice Agent, Whisper, n8n, Evolution API, RAG Híbrido e Automações Homelab",
        "keywords": {"hermes", "whisper", "ia", "inteligencia", "copiloto", "rag", "n8n", "evolution", "homelab", "docker", "pipeline", "automacao", "webhook"},
    },
    "GERAL": {
        "label": "📋 Geral & Administrativo",
        "description": "Conceitos gerais, recados administrativos e termos operacionais transversais",
        "keywords": {"geral", "administrativo", "operacional", "reuniao", "tarefa", "informe"},
    },
}

dictionary_service = DictionaryService()
