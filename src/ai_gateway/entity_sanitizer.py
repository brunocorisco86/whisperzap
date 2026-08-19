"""Módulo de Guardrail, Sanitização, Validação Fonotática e Correção Ortográfica Universal.

Responsável por:
1. Validação fonotática universal em Língua Portuguesa (dígrafos inválidos, repetições, ausência de vogais);
2. Auto-correção fuzzy (Rapidfuzz) contra léxico da língua e vocabulário técnico do agro;
3. Bloqueio estrito: qualquer entidade que contenha erros ortográficos não resolvíveis NÃO vira nó no Grafo.
"""

import logging
import re
import unicodedata
from typing import Dict, Any, List, Optional, Tuple, Set

from rapidfuzz import process, fuzz
from src.memory.task_sentiment_analyzer import get_spacy_nlp

logger = logging.getLogger(__name__)

# Siglas legítimas e marcas com grafia específica que devem ser preservadas
LEGITIMATE_ACRONYMS_AND_BRANDS = {
    "C.Vale", "eProdutor", "Mtech", "FAL", "TMS", "BRIM", "FMIM", "Plasson",
    "Vascão", "GASP", "TI", "RH", "ERP", "IoT", "GPS", "CNPJ", "CPF", "CEP", "API",
    "SQL", "APP", "WEB", "JBS", "BRF", "SMS", "PDF", "XLS", "PIX", "NFe",
}

# Tabela direta de correções de alta prioridade (Whisper & Erros Frequentes)
KNOWN_TYPOS_AND_PHONETIC_FIXES = {
    "fihlos": "Filhos",
    "fihlo": "Filho",
    "fihla": "Filha",
    "fihlas": "Filhas",
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
    "realtorio": "Relatório",
    "camara": "Câmara",
    "silo": "Silo",
    "sensores": "Sensor",
    "senosr": "Sensor",
    "sensor": "Sensor",
    "telemetria": "Telemetria",
    "amonia": "Amônia",
    "temperatura": "Temperatura",
    "umidade": "Umidade",
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

# Entidades de sistema/bot que NUNCA devem virar nós ou poluir o Grafo de Conhecimento
SYSTEM_BLOCKED_ENTITIES = {
    "james", "djeimes", "jeimes", "mordomo", "mordomo virtual", "james mordomo",
    "mnemosine", "mnemosyne", "calíope", "caliope", "urânia", "urania",
    "terpsícore", "terpsicore", "erato", "polímnia", "polimnia", "tália", "thalia",
    "clio", "euterpe", "melpômene", "melpomene", "hermes", "hermes agent",
    "bot", "assistente", "transcrição", "transcricao", "áudio", "audio", "musa", "musas",
    "sistema", "feedback", "transcrever", "gravação", "gravacao",
}

# Léxico de referência em Português para correção fuzzy de palavras
REFERENCE_PORTUGUESE_LEXICON = [
    "abatedouro", "acerto", "acompanhamento", "administração", "agendamento", "agrocenter",
    "agronegócio", "ajuste", "alimentação", "alinhamento", "alta", "aluguel", "amônia", "análise",
    "aplicativo", "apontamento", "aprovado", "arquivo", "assistência", "atendimento", "auditoria",
    "automação", "aviário", "avicultura", "aviso", "baixa", "balança", "banco", "bloqueio",
    "boleto", "cálculo", "calibração", "call", "câmara", "caminhão", "campo", "carga",
    "carregamento", "carteira", "certificado", "chamado", "cheque", "cliente", "coleta",
    "combustível", "comitê", "comissão", "comodato", "comprovante", "comunicação", "conferência",
    "configuração", "consolidação", "conta", "contabilidade", "contato", "contrato", "controle",
    "cooperado", "cooperativa", "correção", "corte", "crédito", "cronograma", "custo",
    "dashboard", "dados", "data", "débito", "declaração", "defeito", "definição", "demanda",
    "departamento", "depósito", "descarregamento", "desconto", "desempenho", "despesa",
    "devolução", "diagnóstico", "dicionário", "diretoria", "dispositivo", "documento", "duplicata",
    "embarque", "emissão", "empresa", "energia", "entrega", "envio", "eprodutor", "equipamento",
    "escala", "especificação", "estoque", "estratégia", "estudo", "etapa", "evento",
    "exigência", "expedição", "extrato", "fábrica", "faturamento", "fechamento", "filha", "filho",
    "financeiro", "fiscal", "fluxo", "fornecedor", "frango", "frequência", "funcionário",
    "garantia", "geração", "gerência", "gestão", "granja", "grupo", "guia", "homologação",
    "horário", "identificação", "iluminação", "implementação", "importação", "imposto", "impressão",
    "indicador", "informação", "infraestrutura", "inspeção", "instalação", "instrução", "insumo",
    "integração", "interface", "internet", "investimento", "lançamento", "laudo", "leitura",
    "lembrete", "licença", "ligação", "limpeza", "linha", "liquidação", "lista", "local",
    "localização", "logística", "lote", "manutenção", "mapa", "marcação", "margem", "medida",
    "medição", "mensagem", "meta", "método", "métrica", "modelo", "módulo", "monitoramento",
    "montagem", "mortalidade", "motorista", "movimentação", "mtech", "negociação", "nível",
    "nota", "notificação", "núcleo", "número", "obrigação", "observação", "operação",
    "orçamento", "ordem", "organização", "pagamento", "painel", "parâmetro", "parcela",
    "parecer", "participação", "pedido", "pendência", "percentual", "período", "pesagem",
    "peso", "pesquisa", "plano", "planta", "plataforma", "política", "portal", "prazo",
    "preço", "prestação", "previsão", "processamento", "processo", "produção", "produtor",
    "projeto", "proposta", "protocolo", "qualidade", "quantidade", "quadro", "quitação",
    "ração", "rastreabilidade", "rastreador", "recebimento", "receita", "recibo", "recurso",
    "reembolso", "registro", "regra", "relatório", "remanejamento", "remessa", "rendimento",
    "reparação", "repasse", "reposição", "reprodução", "requisição", "reserva", "resíduo",
    "resolução", "resultado", "retorno", "reunião", "revisão", "rota", "saldo", "saúde",
    "segmento", "segurança", "seleção", "semana", "semáforo", "sensor", "serviço", "servidor",
    "setor", "silo", "simulação", "sinal", "sistema", "situação", "solicitação", "status",
    "substituição", "suporte", "tabela", "talão", "tarefa", "taxa", "tecnologia", "telefone",
    "telemetria", "temperatura", "tempo", "tendência", "título", "tolerância", "transação",
    "transferência", "transporte", "tratamento", "triagem", "troca", "umidade", "unidade",
    "urgência", "usuário", "vacinação", "validação", "validade", "valor", "vazão", "veículo",
    "vencimento", "venda", "ventilação", "verificação", "viagem", "vistoria", "volume", "voto",
]


class EntitySanitizerGuardrail:
    """Guardrail inteligente de validação fonotática, sanitização e bloqueio estrito de erros."""

    def __init__(self):
        self.nlp = get_spacy_nlp()
        self.lexicon = REFERENCE_PORTUGUESE_LEXICON

    def clean_raw_string(self, text: str) -> str:
        """Limpa aspas, pontuações excedentes e espaços duplicados."""
        if not text:
            return ""
        clean = text.strip().strip("\"'“”`.,;:")
        clean = re.sub(r"\s+", " ", clean)
        return clean.strip()

    def has_phonotactic_violation(self, word: str) -> bool:
        """Detecta se uma palavra viola regras fonotáticas e ortográficas da língua portuguesa."""
        w = word.lower().strip()
        if len(w) < 2:
            return False

        # Preserva siglas legítimas
        if any(w == acronym.lower() for acronym in LEGITIMATE_ACRONYMS_AND_BRANDS):
            return False

        # 1. Dígrafos invertidos ou ilegais no português (ex: 'hl', 'hn', 'hc', 'hr', 'hs')
        if re.search(r"(hl|hn|hc|hr|hs)", w):
            return True

        # 2. Consoantes duplicadas ilegais no português (bb, dd, ff, gg, jj, kk, ll, mm, nn, pp, tt, vv, ww, xx, yy, zz)
        if re.search(r"(bb|dd|ff|gg|jj|kk|ll|mm|nn|pp|tt|vv|ww|xx|yy|zz)", w):
            return True

        # 3. 3 ou mais caracteres idênticos consecutivos (ex: 'aaa', 'ssss')
        if re.search(r"([a-zA-Z])\1\1+", w):
            return True

        # 4. Sequência de 4 ou mais consoantes consecutivas sem nenhuma vogal (keyboard mash / lixo léxico)
        if re.search(r"[b-df-hj-np-tv-z]{4,}", w):
            return True

        return False

    def fuzzy_correct_word(self, word: str) -> Optional[str]:
        """Tenta corrigir um erro de digitação/fonética buscando a correspondência mais próxima no léxico."""
        w = word.lower().strip()
        if not w or len(w) < 3:
            return None

        # Checagem direta no dicionário de correções conhecidas
        if w in KNOWN_TYPOS_AND_PHONETIC_FIXES:
            return KNOWN_TYPOS_AND_PHONETIC_FIXES[w]

        # Se for um plural regular de uma palavra existente no léxico (ex: 'silos', 'projetos'), é válido
        if w.endswith("s") and w[:-1] in self.lexicon:
            return word

        # Se for um plural regular com 'es' (ex: 'sensores', 'motores'), é válido
        if w.endswith("es") and w[:-2] in self.lexicon:
            return word

        # Busca com Rapidfuzz no léxico oficial
        match = process.extractOne(w, self.lexicon, scorer=fuzz.ratio)
        if match:
            best_term, score, _ = match
            # Exige alta similaridade (>= 85%) e diferença de tamanho pequena
            if score >= 85.0 and abs(len(w) - len(best_term)) <= 2:
                # Mantém capitalização se a palavra original era capitalizada
                return best_term.capitalize() if word[0].isupper() else best_term

        return None

    def is_valid_node_entity(self, name: str, category: str = "OTHER") -> Tuple[bool, str, Optional[str]]:
        """Valida universalmente se um termo é ortograficamente legítimo para ser nó no NetworkX.
        
        Retorna: (is_valid: bool, reason: str, sanitized_name: Optional[str])
        """
        clean_name = self.clean_raw_string(name)
        if not clean_name:
            return False, "empty_entity_name", None

        # 0. Bloqueio estrito de personas de sistema/bot (ex: James, Mordomo, Mnemosine, Calíope, etc.)
        lower_name = clean_name.lower().strip()
        if lower_name in SYSTEM_BLOCKED_ENTITIES or any(lower_name == b for b in SYSTEM_BLOCKED_ENTITIES):
            return False, "system_bot_entity_blocked", None

        # 1. Siglas e marcas consagradas são sempre aprovadas
        if clean_name in LEGITIMATE_ACRONYMS_AND_BRANDS or any(clean_name.lower() == b.lower() for b in LEGITIMATE_ACRONYMS_AND_BRANDS):
            for b in LEGITIMATE_ACRONYMS_AND_BRANDS:
                if clean_name.lower() == b.lower():
                    return True, "legitimate_brand_or_acronym", b
            return True, "legitimate_brand_or_acronym", clean_name

        # 2. Bloqueio de alucinações geográficas descontextualizadas
        lower_name = clean_name.lower()
        if category == "LOCATION" and lower_name in SUSPICIOUS_GEOGRAPHIC_HALLUCINATIONS:
            if lower_name == "macau":
                return True, "phonetic_hallucination_fixed", "Call"
            return False, "geographic_hallucination_blocked", None

        # 3. Analisa as palavras do termo
        words = clean_name.split()
        fixed_words = []
        has_unresolvable_error = False

        for w in words:
            # Ignora números puros ou identificadores curtos
            if w.isdigit() or len(w) <= 1:
                fixed_words.append(w)
                continue

            # Se a palavra tem violação fonotática (ex: 'fihlos', 'senosr', 'xyzt')
            if self.has_phonotactic_violation(w):
                corrected = self.fuzzy_correct_word(w)
                if corrected:
                    fixed_words.append(corrected)
                else:
                    logger.info(f"🚫 [Guardrail] Violação fonotática sem correção encontrada: '{w}' no termo '{clean_name}'")
                    has_unresolvable_error = True
                    break
            else:
                # Palavra sem violação óbvia: checa se há correção conhecida (ex: 'abateodouro' -> 'Abatedouro')
                corrected = self.fuzzy_correct_word(w)
                if corrected:
                    fixed_words.append(corrected)
                else:
                    fixed_words.append(w)

        if has_unresolvable_error:
            return False, "unresolvable_orthographic_error", None

        final_sanitized = " ".join(fixed_words)
        return True, "valid_entity", final_sanitized

    def sanitize_entity_name(self, name: str, category: str = "OTHER") -> Tuple[str, str, bool]:
        """Sanitiza o nome da entidade, corrigindo typos e capitalização.
        
        Se a entidade for inválida e não puder ser corrigida, retorna string vazia para bloquear.
        """
        is_valid, reason, sanitized_name = self.is_valid_node_entity(name, category)
        if not is_valid or not sanitized_name:
            return "", category, True

        clean_name = sanitized_name
        clean_cat = "CONCEPT" if sanitized_name == "Call" and category == "LOCATION" else category
        modified = (clean_name != name)

        # Capitalização padrão para nomes próprios e conceitos
        if clean_cat in ("PERSON", "COMPANY", "LOCATION", "PROJECT"):
            if not any(clean_name == acronym for acronym in LEGITIMATE_ACRONYMS_AND_BRANDS):
                if clean_name.islower() or clean_name.isupper():
                    clean_name = clean_name.title()
                    modified = True

        return clean_name, clean_cat, modified

    def sanitize_extracted_entities(self, entities: List[Any]) -> List[Any]:
        """Aplica o guardrail sobre a lista de entidades extraídas pela IA."""
        sanitized = []
        seen_names = set()

        for ent in entities:
            if isinstance(ent, dict):
                name = ent.get("name", "")
                cat = ent.get("category", "OTHER")
            else:
                name = getattr(ent, "name", "")
                cat = getattr(ent, "category", "OTHER")

            clean_n, clean_cat, _ = self.sanitize_entity_name(name, cat)
            # Se for inválido ou repetido, descarta
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
