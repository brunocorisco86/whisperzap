import time
from src.transcriber.prosody_analyzer import prosody_analyzer, ProsodyMetrics
from src.transcriber.schemas import TranscriptionSegment


def test_prosody_analyzer_metrics_and_performance():
    """Testa o cálculo de velocidade de fala, pausas e classificação de tom de voz em < 5ms."""
    segments = [
        TranscriptionSegment(id=0, start=0.0, end=2.5, text="precisamos resolver a fila de espera do atendimento"),
        TranscriptionSegment(id=1, start=3.0, end=5.2, text="porque o silo está com problema urgente"),
    ]
    text = "precisamos resolver a fila de espera do atendimento porque o silo está com problema urgente"
    duration = 6.0

    t0 = time.perf_counter()
    metrics = prosody_analyzer.analyze_speech_prosody(duration=duration, segments=segments, text=text)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert isinstance(metrics, ProsodyMetrics)
    assert metrics.words_count == 15
    assert metrics.total_duration_s == 6.0
    assert metrics.speech_duration_s == 4.7
    assert metrics.pause_ratio > 0.1
    assert metrics.speech_rate_wps > 2.5
    assert metrics.voice_tone in ("TENSO_URGENTE", "ENERGICO", "CALMO_ESTAVEL", "HESITANTE", "NEUTRO")
    assert elapsed_ms < 5.0, f"Prosódia demorou {elapsed_ms:.2f}ms (esperado < 5ms)"


def test_prosody_analyzer_empty_and_short_audio():
    """Garante resiliência com áudios muito curtos ou sem fala."""
    metrics = prosody_analyzer.analyze_speech_prosody(duration=0.5, segments=[], text="ok")
    assert metrics.voice_tone == "NEUTRO"
    assert metrics.speech_rate_wps >= 0.0


def test_prosody_analyzer_distinguishes_tones():
    """Testa se o analisador diferencia tons sem colapsar tudo em neutro."""
    # Tenso / Urgente
    m_urgent = prosody_analyzer.analyze_speech_prosody(
        duration=3.0,
        segments=[],
        text="Socorro, o silo travou e está vazando ração urgente!!",
    )
    assert m_urgent.voice_tone == "TENSO_URGENTE"
    assert m_urgent.acoustic_score < 0

    # Enérgico
    m_energic = prosody_analyzer.analyze_speech_prosody(
        duration=2.5,
        segments=[],
        text="Show de bola, ótimo trabalho, conseguimos bater a meta!",
    )
    assert m_energic.voice_tone == "ENERGICO"
    assert m_energic.acoustic_score > 0

    # Hesitante
    m_hesitant = prosody_analyzer.analyze_speech_prosody(
        duration=7.0,
        segments=[],
        text="ééé... então... tipo assim... não sei direito o que fazer",
    )
    assert m_hesitant.voice_tone == "HESITANTE"

    # Calmo / Estável
    m_calm = prosody_analyzer.analyze_speech_prosody(
        duration=5.0,
        segments=[],
        text="Combinado, amanhã cedo passo na unidade para verificar o andamento.",
    )
    assert m_calm.voice_tone == "CALMO_ESTAVEL"

