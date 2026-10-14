"""Analisador de Sentimento Híbrido e Ultra-Leve (Pure Python & Regex).

Executa em < 0.1ms sem consumo adicional de memória RAM (zero novos modelos ou LLMs).
Fornece classificação emocional de alta sensibilidade para calibrar saídas que
anteriormente colapsavam em 'NEUTRAL'.
"""

import re
from typing import Optional, Tuple
from pydantic import BaseModel, Field


class FastSentimentResult(BaseModel):
    sentiment: str = Field(..., description="Tom emocional: POSITIVE, CONFIDENT, NEUTRAL, URGENT, ANXIOUS, FRUSTRATED")
    sentiment_score: float = Field(..., description="Score numérico de -1.0 a +1.0")
    confidence: float = Field(..., description="Nível de confiança na classificação (0.0 a 1.0)")
    dominant_category: str = Field(default="NEUTRAL")


class FastSentimentAnalyzer:
    """Classificador léxico-sintático calibrado para português em mensagens de WhatsApp."""

    # Expressões e palavras-chave por sentimento (com pesos de intensidade)
    POSITIVE_TERMS = {
        "obrigado": 1.0, "obrigada": 1.0, "valeu": 0.9, "show": 0.9, "ótimo": 1.1, "otimo": 1.1,
        "excelente": 1.2, "perfeito": 1.2, "maravilha": 1.1, "parabéns": 1.1, "parabens": 1.1,
        "sucesso": 1.0, "aprovado": 1.0, "beleza": 0.8, "top": 0.8, "tranquilo": 0.8,
        "agradeço": 1.0, "agradeco": 1.0, "sensacional": 1.2, "muito bom": 1.1, "bom dia": 0.4,
        "boa tarde": 0.4, "boa noite": 0.4, "bom trabalho": 1.0, "tudo certo": 0.8, "tudo bem": 0.5,
        "combinado": 0.7, "certo": 0.5, "fechado": 0.7, "consegui": 0.9, "ajudou muito": 1.2,
        "sensacional": 1.2, "recomendo": 0.9, "adorei": 1.1, "legal": 0.7, "bacana": 0.7,
    }

    CONFIDENT_TERMS = {
        "garantido": 1.2, "resolvido": 1.2, "certeza": 1.1, "fechamos": 1.0, "com certeza": 1.2,
        "sem falta": 1.1, "em dia": 0.9, "alinhado": 0.9, "pronto": 0.9, "finalizado": 1.0,
        "sob controle": 1.2, "pode deixar": 1.1, "vou resolver": 1.1, "já providenciei": 1.2,
        "ja providenciei": 1.2, "combinadíssimo": 1.1, "combinadissimo": 1.1, "assumo": 0.9,
        "sem dúvida": 1.1, "sem duvida": 1.1, "garanto": 1.2, "implantado": 1.0, "concluído": 1.0,
        "concluido": 1.0, "tudo dominado": 1.3, "firme": 0.8, "definido": 0.9,
    }

    URGENT_TERMS = {
        "urgente": 1.3, "urgência": 1.3, "urgencia": 1.3, "emergência": 1.4, "emergencia": 1.4,
        "socorro": 1.5, "crítico": 1.3, "critico": 1.3, "imediatamente": 1.3, "agora mesmo": 1.2,
        "rápido": 1.0, "rapido": 1.0, "asap": 1.2, "gravíssimo": 1.4, "gravissimo": 1.4,
        "parou": 1.1, "travou": 1.1, "quebrou": 1.2, "vazando": 1.2, "risco": 1.1, "perigo": 1.2,
        "alerta": 1.1, "corre": 1.0, "grave": 1.1, "prejuízo iminente": 1.4, "acidente": 1.3,
        "tombou": 1.3, "pegando fogo": 1.5, "morte": 1.4, "crise": 1.2, "bloqueado": 1.0,
    }

    ANXIOUS_TERMS = {
        "dúvida": 0.8, "duvida": 0.8, "dúvidas": 0.8, "duvidas": 0.8, "preocupado": 1.2,
        "preocupada": 1.2, "preocupação": 1.1, "preocupacao": 1.1, "receio": 1.0, "medo": 1.1,
        "inseguro": 1.1, "não sei se": 0.9, "nao sei se": 0.9, "cadê": 1.0, "cade": 1.0,
        "quando vai": 0.9, "aguardando retorno": 1.1, "nenhum retorno": 1.2, "alguma novidade": 0.9,
        "será que": 0.8, "sera que": 0.8, "alguma posição": 0.9, "alguma posicao": 0.9,
        "demora": 0.9, "ainda não responderam": 1.2, "ainda nao responderam": 1.2, "sem resposta": 1.1,
        "angústia": 1.3, "angustia": 1.3, "apreensivo": 1.2, "ansioso": 1.1, "ansiosa": 1.1,
    }

    FRUSTRATED_TERMS = {
        "problema": 1.0, "problemas": 1.0, "erro": 1.1, "erros": 1.1, "falha": 1.1, "falhas": 1.1,
        "atrasado": 1.1, "atraso": 1.0, "reclamação": 1.2, "reclamacao": 1.2, "estragou": 1.2,
        "prejuízo": 1.3, "prejuizo": 1.3, "complicado": 0.9, "difícil": 0.9, "dificil": 0.9,
        "ruim": 1.0, "péssimo": 1.4, "pessimo": 1.4, "inadmissível": 1.5, "inadmissivel": 1.5,
        "absurdo": 1.4, "de novo": 1.0, "novamente com erro": 1.3, "não funciona": 1.2,
        "nao funciona": 1.2, "travando": 1.0, "cansado de pedir": 1.4, "vergonha": 1.3,
        "palhaçada": 1.4, "palhacada": 1.4, "porcaria": 1.3, "descaso": 1.3, "decepcionado": 1.3,
    }

    # Emojis associados
    POSITIVE_EMOJIS = {"😊", "😃", "😄", "😁", "👏", "👍", "🙏", "🎉", "❤️", "🚀", "✨", "🙌", "💪", "🔝"}
    NEGATIVE_EMOJIS = {"😠", "😡", "🤬", "😤", "🤦", "👎", "💔", "💩"}
    ANXIOUS_EMOJIS = {"😟", "😰", "😥", "😨", "🤔", "🧐", "🥺"}
    URGENT_EMOJIS = {"🚨", "⚠️", "🔥", "⚡", "🆘", "‼️"}

    # Padrões de negação que neutralizam ou invertem termos negativos
    NEGATION_PATTERN = re.compile(
        r"\b(não|nao|sem|nem|nunca|jamais)\s+(ter\s+|tem\s+|haver\s+|há\s+|ha\s+)?(problema|erro|falha|estresse|dúvida|duvida|crise|reclamação|reclamacao)\b",
        re.IGNORECASE,
    )

    def analyze(
        self,
        text: str,
        summary: str = "",
        urgency: str = "MEDIUM",
        prosody_tone: Optional[str] = None,
        acoustic_score: Optional[float] = None,
    ) -> FastSentimentResult:
        """Classifica sentimento e polaridade de forma ultra-rápida e resiliente."""
        raw_text = (text or "").strip()
        raw_summary = (summary or "").strip()
        full_text = f"{raw_text} {raw_summary}".strip()

        if not full_text:
            return FastSentimentResult(sentiment="NEUTRAL", sentiment_score=0.0, confidence=0.0, dominant_category="NEUTRAL")

        lower_text = full_text.lower()

        # 1. Pré-processamento: Neutraliza falsos negativos como "sem problema", "não tem erro"
        cleaned_text = self.NEGATION_PATTERN.sub("tudo_positivo_tranquilo", lower_text)

        # 2. Contagem e pontuação por categoria
        pos_score = 0.0
        conf_score = 0.0
        urg_score = 0.0
        anx_score = 0.0
        fru_score = 0.0

        # Termos positivos
        for term, weight in self.POSITIVE_TERMS.items():
            if term in cleaned_text:
                pos_score += weight

        # Termos confiantes
        for term, weight in self.CONFIDENT_TERMS.items():
            if term in cleaned_text:
                conf_score += weight

        # Termos urgentes
        for term, weight in self.URGENT_TERMS.items():
            if term in cleaned_text:
                urg_score += weight

        # Termos ansiosos
        for term, weight in self.ANXIOUS_TERMS.items():
            if term in cleaned_text:
                anx_score += weight

        # Termos frustrados
        for term, weight in self.FRUSTRATED_TERMS.items():
            if term in cleaned_text:
                fru_score += weight

        # 3. Análise de Emojis
        for ch in full_text:
            if ch in self.POSITIVE_EMOJIS:
                pos_score += 0.8
            elif ch in self.NEGATIVE_EMOJIS:
                fru_score += 1.0
            elif ch in self.ANXIOUS_EMOJIS:
                anx_score += 0.8
            elif ch in self.URGENT_EMOJIS:
                urg_score += 1.2

        # 4. Análise de Pontuação e Formatação de Texto
        exclamation_count = full_text.count("!")
        question_count = full_text.count("?")

        if exclamation_count >= 2:
            if urg_score > 0 or fru_score > 0:
                urg_score += 0.6
                fru_score += 0.4
            elif pos_score > 0 or conf_score > 0:
                pos_score += 0.5
                conf_score += 0.3

        if question_count >= 2 and (anx_score > 0 or "quando" in lower_text or "cadê" in lower_text):
            anx_score += 0.6

        # Caixa alta enfática (Grito/Tensão em palavras relevantes)
        words_all_caps = [w for w in re.findall(r"\b[A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ]{4,}\b", full_text) if w not in ("HTTP", "HTTPS", "JSON", "HTML")]
        if words_all_caps:
            for w in words_all_caps:
                wl = w.lower()
                if wl in self.URGENT_TERMS or wl in ("URGENTE", "AGORA", "SOCORRO", "PAROU"):
                    urg_score += 1.0
                elif wl in self.FRUSTRATED_TERMS or wl in ("ERRO", "FALHA", "ABSURDO"):
                    fru_score += 1.0

        # 5. Influência Multimodal (Prosódia Acústica e Urgência do Sistema)
        if prosody_tone:
            pt = prosody_tone.upper()
            if pt == "TENSO_URGENTE":
                urg_score += 1.4
                fru_score += 0.5
            elif pt == "ENERGICO":
                pos_score += 0.8
                conf_score += 0.5
            elif pt == "HESITANTE":
                anx_score += 0.9
            elif pt == "CALMO_ESTAVEL":
                pos_score += 0.4
                conf_score += 0.4

        if acoustic_score is not None:
            if acoustic_score <= -0.5:
                urg_score += 0.5
                fru_score += 0.3
            elif acoustic_score >= 0.5:
                pos_score += 0.3

        # Urgência externa do sistema (só amplifica se já houver pistas de urgência/frustração ou tom tenso)
        urgency_upper = (urgency or "MEDIUM").upper()
        if urg_score > 0 or fru_score > 0:
            if urgency_upper == "URGENT":
                urg_score += 1.0
            elif urgency_upper == "HIGH":
                urg_score += 0.4

        # 6. Decisão de Categoria Dominante e Score Final
        scores = {
            "URGENT": urg_score,
            "FRUSTRATED": fru_score,
            "ANXIOUS": anx_score,
            "CONFIDENT": conf_score,
            "POSITIVE": pos_score,
        }

        # Encontra o maior score
        best_cat, max_val = max(scores.items(), key=lambda item: item[1])

        # Se nenhum score atingir o patamar mínimo de expressividade emocional, é genuinamente NEUTRAL
        MIN_TRIGGER_THRESHOLD = 0.70
        if max_val < MIN_TRIGGER_THRESHOLD:
            return FastSentimentResult(
                sentiment="NEUTRAL",
                sentiment_score=0.0,
                confidence=0.5,
                dominant_category="NEUTRAL",
            )

        # Mapeamento do score contínuo (-1.0 a +1.0)
        confidence = min(1.0, round(max_val / 2.0, 2))
        final_score = 0.0

        if best_cat == "URGENT":
            final_score = -0.75 - min(0.20, (max_val - 1.0) * 0.1)
        elif best_cat == "FRUSTRATED":
            final_score = -0.65 - min(0.25, (max_val - 1.0) * 0.1)
        elif best_cat == "ANXIOUS":
            final_score = -0.40 - min(0.20, (max_val - 1.0) * 0.1)
        elif best_cat == "CONFIDENT":
            final_score = 0.75 + min(0.20, (max_val - 1.0) * 0.1)
        elif best_cat == "POSITIVE":
            final_score = 0.65 + min(0.25, (max_val - 1.0) * 0.1)

        final_score = max(-1.0, min(1.0, round(final_score, 2)))

        return FastSentimentResult(
            sentiment=best_cat,
            sentiment_score=final_score,
            confidence=confidence,
            dominant_category=best_cat,
        )


fast_sentiment_analyzer = FastSentimentAnalyzer()
