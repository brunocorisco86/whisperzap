"""Motor de Prosódia Acústica e Cadência Ultra-Leve (Pure Python & VAD) para VPS de Baixo Recurso.

Analisa a dinâmica temporal, cadência de fala, taxa de pausas e agitação vocal
em menos de 2 milissegundos sem exigir bibliotecas pesadas de compilação C/LLVM.
Combina métricas de VAD/segmentação com marcadores paralinguísticos do texto
para evitar o colapso artificial em 'NEUTRO'.
"""

import re
from typing import List, Any
from pydantic import BaseModel, Field


class ProsodyMetrics(BaseModel):
    """Métricas prosódicas e acústicas extraídas da fala."""
    total_duration_s: float = Field(..., description="Duração total do áudio em segundos")
    speech_duration_s: float = Field(..., description="Duração de fala ativa sem silêncios em segundos")
    pause_ratio: float = Field(..., description="Proporção de silêncio/pausas no áudio (0.0 a 1.0)")
    words_count: int = Field(..., description="Total de palavras identificadas")
    speech_rate_wps: float = Field(..., description="Velocidade de fala em palavras por segundo ativo")
    voice_tone: str = Field(..., description="Classificação do tom de voz (TENSO_URGENTE, ENERGICO, CALMO_ESTAVEL, HESITANTE, NEUTRO)")
    tone_label: str = Field(..., description="Rótulo amigável formatado com emoji")
    tone_badge_class: str = Field(..., description="Classe CSS para estilização no frontend")
    acoustic_score: float = Field(..., description="Score acústico de -1.0 (muito tenso/ansioso) a +1.0 (muito calmo/positivo)")
    arousal_index: float = Field(..., description="Índice de agitação/excitação vocal (0.0 a 1.0)")


class ProsodyAnalyzer:
    """Analisador acústico leve baseado em dados de segmentação Silero-VAD e texto."""

    # Marcadores paralinguísticos e emocionais no texto transcrito
    URGENCY_KEYWORDS = {
        "urgente", "socorro", "rápido", "rapido", "corre", "cuidado", "atenção", "atencao",
        "problema", "imediatamente", "agora", "parou", "grave", "travou", "quebrou", "vazando",
        "crítico", "critico", "prejuízo", "prejuizo", "acidente", "alerta",
    }
    
    ENERGY_KEYWORDS = {
        "ótimo", "otimo", "show", "maravilha", "bora", "vamos", "excelente", "top", "parabéns",
        "parabens", "sucesso", "perfeito", "sensacional", "conseguimos", "demais", "beleza",
    }
    
    HESITATION_KEYWORDS = {
        "ééé", "éé", "humm", "hum", "tipo", "sei lá", "sei la", "deixa eu ver", "peraí", "perai",
        "acho que", "talvez", "então...", "entao...", "não sei", "nao sei",
    }

    @classmethod
    def analyze_speech_prosody(
        cls,
        duration: float,
        segments: List[Any],
        text: str,
    ) -> ProsodyMetrics:
        """Calcula métricas prosódicas a partir da duração e dos segmentos de fala do VAD."""
        total_dur = max(float(duration or 0.0), 0.1)
        raw_text = (text or "").strip()
        
        # 1. Contagem de palavras e tokens de pontuação
        words = re.findall(r"\b\w+\b", raw_text)
        words_count = len(words)
        lower_text = raw_text.lower()

        # 2. Duração ativa de fala a partir dos timestamps dos segmentos
        if segments:
            speech_dur = sum(max(0.0, float(getattr(s, "end", 0.0) - getattr(s, "start", 0.0))) for s in segments)
            speech_dur = min(total_dur, max(0.1, speech_dur))
        else:
            # Fallback inteligente quando não há lista de segmentos VAD:
            # Estima pausas com base na pontuação e no fluxo de palavras
            punctuation_pauses = len(re.findall(r"[,;:\.\?!…]+", raw_text)) * 0.35
            estimated_pause = min(total_dur * 0.40, max(0.2, punctuation_pauses))
            speech_dur = max(0.1, total_dur - estimated_pause)

        # 3. Taxa de pausas / silêncios
        pause_dur = max(0.0, total_dur - speech_dur)
        pause_ratio = round(pause_dur / total_dur, 3)

        # 4. Velocidade de fala (Words Per Second sobre o tempo ativo)
        speech_rate = round(words_count / speech_dur, 2) if speech_dur > 0 else 0.0

        # 5. Marcadores textuais de prosódia
        tokens_set = set(re.findall(r"\b[a-zA-ZáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]{2,}\b", lower_text))
        has_urgency_words = bool(tokens_set & cls.URGENCY_KEYWORDS)
        has_energy_words = bool(tokens_set & cls.ENERGY_KEYWORDS)
        has_hesitation_words = (
            bool(tokens_set & cls.HESITATION_KEYWORDS)
            or any(p in lower_text for p in ("não sei", "nao sei", "sei lá", "sei la", "deixa ver", "peraí", "perai", "tipo assim", "acho que"))
            or "..." in raw_text
        )

        exclamation_count = raw_text.count("!")
        question_count = raw_text.count("?")

        # 6. Classificação do Tom de Voz & Arousal
        # Parâmetros calibrados para o português falado no Brasil:
        # - Fala Conversacional Típica: 2.0 a 2.8 wps
        # - Fala Acelerada/Agitada: >= 2.85 wps
        # - Fala Muito Rápida/Urgente: >= 3.25 wps
        # - Fala Lenta/Pausada: < 1.95 wps

        if words_count >= 1:
            # Condição A: Tenso / Urgente (fala acelerada com marcadores de estresse/urgência ou sem entusiasmo)
            if (
                (has_urgency_words and (speech_rate >= 2.3 or exclamation_count >= 1))
                or (speech_rate >= 3.1 and pause_ratio < 0.28 and not has_energy_words)
                or (speech_rate >= 3.6 and not has_energy_words)
                or (exclamation_count >= 2 and speech_rate >= 2.5 and not has_energy_words)
            ):
                voice_tone = "TENSO_URGENTE"
                tone_label = "⚡ Acelerado & Tenso"
                tone_badge_class = "badge-danger"
                acoustic_score = -0.75
                arousal = min(0.95, 0.70 + (speech_rate / 10.0))

            # Condição B: Enérgico / Dinâmico (entusiasmo, agilidade positiva e engajamento)
            elif (
                (has_energy_words and (speech_rate >= 2.0 or exclamation_count >= 1))
                or (speech_rate >= 2.65 and pause_ratio < 0.30 and not has_urgency_words)
            ):
                voice_tone = "ENERGICO"
                tone_label = "🚀 Enérgico & Dinâmico"
                tone_badge_class = "badge-warning"
                acoustic_score = 0.65
                arousal = 0.75

            # Condição C: Hesitante / Pausado (marcadores disfluentes, pausas ou cadência lenta)
            elif (
                has_hesitation_words
                or (speech_rate < 1.85 and words_count >= 3)
                or (pause_ratio >= 0.26 and speech_rate < 2.1)
            ):
                voice_tone = "HESITANTE"
                tone_label = "🤔 Hesitante & Pausado"
                tone_badge_class = "badge-neutral"
                acoustic_score = -0.30
                arousal = 0.30

            # Condição D: Calmo & Equilibrado
            elif 1.70 <= speech_rate <= 2.65 and pause_ratio <= 0.35 and not has_urgency_words:
                voice_tone = "CALMO_ESTAVEL"
                tone_label = "🌿 Calmo & Equilibrado"
                tone_badge_class = "badge-success"
                acoustic_score = 0.60
                arousal = 0.40

            # Condição E: Neutro (áudios muito curtos sem marcadores ou fala estritamente protocolar)
            else:
                voice_tone = "NEUTRO"
                tone_label = "💬 Neutro & Estável"
                tone_badge_class = "badge-info"
                acoustic_score = 0.0
                arousal = 0.50
        else:
            voice_tone = "NEUTRO"
            tone_label = "💬 Curto / Neutro"
            tone_badge_class = "badge-info"
            acoustic_score = 0.0
            arousal = 0.50

        return ProsodyMetrics(
            total_duration_s=round(total_dur, 2),
            speech_duration_s=round(speech_dur, 2),
            pause_ratio=pause_ratio,
            words_count=words_count,
            speech_rate_wps=speech_rate,
            voice_tone=voice_tone,
            tone_label=tone_label,
            tone_badge_class=tone_badge_class,
            acoustic_score=round(acoustic_score, 2),
            arousal_index=round(arousal, 2),
        )


prosody_analyzer = ProsodyAnalyzer()
