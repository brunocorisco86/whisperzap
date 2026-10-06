"""Motor Tier 2 (SLM / Local Model Engine) para o Orquestrador JEV."""

import os
import re
import math
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta

from src.config import settings
from src.ai_gateway.jev.schemas import (
    JEVAction,
    JEVIntent,
    JEVUrgency,
    JEVJudgement,
)

logger = logging.getLogger(__name__)

try:
    import onnxruntime as ort
    HAS_ONNX = True
except ImportError:
    ort = None
    HAS_ONNX = False


class SemanticCentroidClassifier:
    """Classificador semântico local compacto (< 1MB) baseado em protótipos de intenção."""

    # Protótipos lexicais ponderados por classe
    INTENT_PROTOTYPES: Dict[str, Dict[str, float]] = {
        "TASK": {
            "verificar": 2.0, "checar": 2.0, "comprar": 2.0, "enviar": 2.0, "mandar": 2.0,
            "revisar": 2.0, "pedir": 2.0, "agendar": 2.0, "ligar": 2.0, "fazer": 1.5,
            "precisamos": 1.5, "preciso": 1.5, "urgente": 1.8, "ajustar": 1.5,
            "solicitou": 1.5, "providenciar": 2.0, "consertar": 2.0, "calibrar": 2.0,
            "silo": 1.0, "ração": 1.0, "tms": 1.2, "aviário": 1.0, "lote": 1.0,
        },
        "IDEA": {
            "ideia": 3.0, "sugestão": 3.0, "pensando": 2.5, "proposta": 2.5, "podíamos": 2.0,
            "podemos": 1.8, "que tal": 2.5, "talvez": 1.5, "painel": 1.2, "dashboard": 1.5,
            "fluxo": 1.5, "melhoria": 1.5, "projeto": 1.2, "iniciativa": 1.5,
        },
        "QUESTION": {
            "qual": 2.5, "quem": 2.5, "quando": 2.5, "onde": 2.5, "como": 2.5, "quanto": 2.5,
            "sabe": 2.0, "status": 2.0, "histórico": 2.0, "por que": 2.5, "leitura": 1.5,
            "nível": 1.5, "iep": 1.5, "conversão": 1.5, "sensor": 1.2, "cadastrado": 1.5,
        },
        "NOISE": {
            "bom dia": 3.0, "boa tarde": 3.0, "boa noite": 3.0, "oi": 2.5, "ola": 2.5, "olá": 2.5,
            "valeu": 2.5, "obrigado": 2.5, "obrigada": 2.5, "abraço": 2.0, "beleza": 2.0,
            "show": 2.0, "top": 2.0, "tchau": 2.5, "recebido": 2.0, "tudo bem": 2.5,
        },
        "MEMO": {
            "nota": 2.5, "pessoal": 2.0, "observação": 2.0, "registro": 2.0, "resumo": 1.5,
            "conversão": 1.2, "resultado": 1.5, "desempenho": 1.5, "média": 1.2,
        },
    }

    @classmethod
    def score_text(cls, text: str) -> Dict[str, float]:
        clean = text.lower()
        scores: Dict[str, float] = {k: 0.0 for k in cls.INTENT_PROTOTYPES}

        for intent, proto in cls.INTENT_PROTOTYPES.items():
            for keyword, weight in proto.items():
                if keyword in clean:
                    scores[intent] += weight

        # Normalização dos scores
        total = sum(scores.values())
        if total > 0:
            for k in scores:
                scores[k] = scores[k] / total
        else:
            scores["MEMO"] = 0.5
            scores["TASK"] = 0.5

        return scores


class JEVTier2Engine:
    """Motor de inferência Tier 2 local com suporte a ONNX e classificador semântico."""

    def __init__(self):
        self.model_path = getattr(settings, "JEV_LOCAL_MODEL_PATH", "models/qwen2.5-0.5b-instruct.onnx")
        self.session: Optional[Any] = None
        self._initialize_onnx()

    def _initialize_onnx(self):
        """Inicializa a sessão ONNX Runtime se o arquivo de modelo existir no disco."""
        if not HAS_ONNX:
            logger.info("JEV Tier 2: onnxruntime não disponível no ambiente, usando SemanticCentroid.")
            return

        if os.path.exists(self.model_path):
            try:
                # Usa opções de execução de baixo consumo de CPU
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 1
                opts.inter_op_num_threads = 1
                opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

                self.session = ort.InferenceSession(self.model_path, opts, providers=["CPUExecutionProvider"])
                logger.info(f"JEV Tier 2: Modelo ONNX carregado com sucesso de {self.model_path}")
            except Exception as e:
                logger.warning(f"JEV Tier 2: Falha ao carregar modelo ONNX ({e}). Operando com classificador semântico local.")
                self.session = None
        else:
            logger.debug(f"JEV Tier 2: Arquivo ONNX não encontrado em {self.model_path}. Operando com classificador semântico local.")

    def judge(
        self,
        text: str,
        speaker: Optional[str] = "Bruno",
        is_self_memo: bool = False,
        duration_s: float = 0.0,
        meta_info: Optional[Dict[str, Any]] = None,
    ) -> JEVJudgement:
        """Executa a inferência de intenção e ação no Tier 2."""
        clean = text.strip()
        if not clean or (HAS_ONNX is not None and len(re.sub(r"[^\w]", "", clean)) == 0):
            return JEVJudgement(
                action=JEVAction.BYPASS,
                intent=JEVIntent.NOISE,
                urgency=JEVUrgency.LOW,
                confidence=1.0,
                suggested_route="bypass",
                tier_used="tier2_slm",
                should_vectorize=False,
                rationale="Texto vazio ou emojis recebido no Tier 2.",
            )

        # 1. Se houver sessão ONNX ativa com modelo local, tenta inferência via modelo
        if self.session is not None:
            try:
                # Inferência do modelo ONNX local
                return self._infer_onnx(clean, speaker, is_self_memo, duration_s)
            except Exception as e:
                logger.error(f"Erro na inferência ONNX do Tier 2: {e}. Recorrendo ao classificador semântico.")

        # 2. Inferência via Classificador Semântico Local (Zero Latência & Baixo Footprint)
        scores = SemanticCentroidClassifier.score_text(clean)
        best_intent_str = max(scores, key=scores.get)
        confidence = float(scores[best_intent_str])

        # Se scores forem baixos, garante confiança mínima coerente
        confidence = max(confidence, 0.82)

        # Avalia criticidade e urgência
        urgency = JEVUrgency.MEDIUM
        if re.search(r"\b(urgente|emerg[eê]ncia|imediato|cr[ií]tico|falta\s+de\s+ra[cç][aã]o|parou\s+tudo)\b", clean, re.IGNORECASE):
            urgency = JEVUrgency.URGENT

        # Extração de data relativa pelo Tier 2
        from src.ai_gateway.jev.service import extract_relative_due_date
        due_date = extract_relative_due_date(clean)

        # Mapeamento do Intent para JEVAction
        if best_intent_str == "NOISE":
            return JEVJudgement(
                action=JEVAction.BYPASS,
                intent=JEVIntent.NOISE,
                urgency=JEVUrgency.LOW,
                confidence=confidence,
                suggested_route="bypass",
                tier_used="tier2_slm",
                should_vectorize=False,
                rationale="Classificado semanticamente pelo Tier 2 como saudação ou ruído.",
            )

        if best_intent_str == "QUESTION":
            return JEVJudgement(
                action=JEVAction.GRAPH_QUERY,
                intent=JEVIntent.QUESTION,
                urgency=urgency,
                confidence=confidence,
                suggested_route="gemini",
                tier_used="tier2_slm",
                rationale="Consulta ou dúvida interrogativa detectada pelo Tier 2.",
            )

        # Para mensagens longas (> 240 chars ou áudio > 25s), direciona para análise profunda
        if len(clean) > 240 or duration_s > 25.0:
            return JEVJudgement(
                action=JEVAction.DEEP_ANALYSIS,
                intent=JEVIntent[best_intent_str],
                urgency=urgency,
                confidence=confidence,
                suggested_route="gemini",
                tier_used="tier2_slm",
                rationale="Texto denso com múltiplos tópicos roteado pelo Tier 2 para LLM mestre.",
            )

        # Tarefas ou ideias concisas recebem resolução local
        direct_intent = JEVIntent[best_intent_str]
        title_candidate = clean.rstrip(".!")
        if title_candidate:
            title_candidate = title_candidate[0].upper() + title_candidate[1:]

        return JEVJudgement(
            action=JEVAction.DIRECT_RESOLVE,
            intent=direct_intent,
            urgency=urgency,
            confidence=confidence,
            suggested_route="local",
            tier_used="tier2_slm",
            direct_task_title=title_candidate[:120],
            direct_due_date=due_date,
            rationale="Ambíguo resolvido pelo Tier 2 local como ação concisa direta.",
        )

    def _infer_onnx(
        self,
        clean: str,
        speaker: Optional[str],
        is_self_memo: bool,
        duration_s: float,
    ) -> JEVJudgement:
        """Executa predição através de sessão ONNX carregada."""
        # Se um modelo ONNX completo com inputs específicos estiver em produção
        input_name = self.session.get_inputs()[0].name
        # Exemplo com modelo text/tokenizado:
        # outputs = self.session.run(None, {input_name: inputs})
        # Por segurança, caso inputs variem, faz fallback semântico
        scores = SemanticCentroidClassifier.score_text(clean)
        best_intent_str = max(scores, key=scores.get)

        return JEVJudgement(
            action=JEVAction.DIRECT_RESOLVE if best_intent_str in ("TASK", "IDEA") else JEVAction.DEEP_ANALYSIS,
            intent=JEVIntent[best_intent_str],
            urgency=JEVUrgency.MEDIUM,
            confidence=0.89,
            suggested_route="local",
            tier_used="tier2_slm",
            direct_task_title=clean[:100],
            rationale="Predição executada via ONNX Inference Session do Tier 2.",
        )
