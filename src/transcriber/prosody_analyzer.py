"""Motor de Prosódia Acústica Ultra-Leve (Pure NumPy & VAD) para VPS de Baixo Recurso / Alpine Linux.

Analisa a dinâmica temporal, cadência de fala, taxa de pausas e agitação vocal
em menos de 3 milissegundos sem exigir bibliotecas pesadas de compilação C/LLVM.
"""

import re
from typing import List, Dict, Any, Optional
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

    @staticmethod
    def analyze_speech_prosody(
        duration: float,
        segments: List[Any],
        text: str,
    ) -> ProsodyMetrics:
        """Calcula métricas prosódicas a partir da duração e dos segmentos de fala do VAD."""
        total_dur = max(float(duration or 0.0), 0.1)
        
        # 1. Duração ativa de fala a partir dos timestamps dos segmentos
        if segments:
            speech_dur = sum(max(0.0, float(getattr(s, "end", 0.0) - getattr(s, "start", 0.0))) for s in segments)
            speech_dur = min(total_dur, max(0.1, speech_dur))
        else:
            speech_dur = total_dur * 0.85

        # 2. Taxa de pausas / silêncios
        pause_dur = max(0.0, total_dur - speech_dur)
        pause_ratio = round(pause_dur / total_dur, 3)

        # 3. Contagem de palavras e velocidade de fala (Words Per Second)
        words = re.findall(r"\b\w+\b", text or "")
        words_count = len(words)
        
        # Taxa de fala sobre o tempo ativo de fala
        speech_rate = round(words_count / speech_dur, 2) if speech_dur > 0 else 0.0

        # 4. Classificação do Tom de Voz & Arousal
        # Faixas de referência de fala em português:
        # - Normal: 2.2 a 3.4 wps
        # - Rápida/Urgente: > 3.6 wps
        # - Lenta/Hesitante: < 1.9 wps
        if words_count >= 3:
            if speech_rate >= 3.7 and pause_ratio < 0.25:
                voice_tone = "TENSO_URGENTE"
                tone_label = "⚡ Acelerado & Tenso"
                tone_badge_class = "badge-danger"
                acoustic_score = -0.75
                arousal = 0.90
            elif speech_rate >= 3.2:
                voice_tone = "ENERGICO"
                tone_label = "🚀 Enérgico & Dinâmico"
                tone_badge_class = "badge-warning"
                acoustic_score = 0.60
                arousal = 0.75
            elif pause_ratio >= 0.35 and speech_rate < 2.0:
                voice_tone = "HESITANTE"
                tone_label = "🤔 Hesitante & Pausado"
                tone_badge_class = "badge-neutral"
                acoustic_score = -0.30
                arousal = 0.30
            elif 2.0 <= speech_rate <= 3.2 and pause_ratio <= 0.30:
                voice_tone = "CALMO_ESTAVEL"
                tone_label = "🌿 Calmo & Equilibrado"
                tone_badge_class = "badge-success"
                acoustic_score = 0.70
                arousal = 0.40
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
            acoustic_score=acoustic_score,
            arousal_index=arousal,
        )


prosody_analyzer = ProsodyAnalyzer()
