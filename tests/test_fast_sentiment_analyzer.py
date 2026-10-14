import time
import pytest
from src.ai_gateway.sentiment_analyzer import fast_sentiment_analyzer, FastSentimentResult


def test_fast_sentiment_analyzer_emotions():
    """Valida a identificação correta de todas as emoções não-neutras."""
    # Positivo
    r_pos = fast_sentiment_analyzer.analyze("Muito obrigado pela ajuda! Ficou perfeito e excelente.")
    assert r_pos.sentiment == "POSITIVE"
    assert r_pos.sentiment_score > 0.5

    # Confiante
    r_conf = fast_sentiment_analyzer.analyze("Pode deixar comigo, já providenciei tudo e está resolvido sem falta.")
    assert r_conf.sentiment == "CONFIDENT"
    assert r_conf.sentiment_score > 0.5

    # Urgente
    r_urg = fast_sentiment_analyzer.analyze("URGENTE!! O gerador travou e a ração parou de descer, socorro!")
    assert r_urg.sentiment == "URGENT"
    assert r_urg.sentiment_score < -0.5

    # Frustrado
    r_fru = fast_sentiment_analyzer.analyze("De novo esse erro absurdo, é uma palhaçada esse atraso recorrente.")
    assert r_fru.sentiment == "FRUSTRATED"
    assert r_fru.sentiment_score < -0.5

    # Ansioso
    r_anx = fast_sentiment_analyzer.analyze("Alguma novidade sobre o pedido? Estou preocupado pois não responderam ainda.")
    assert r_anx.sentiment == "ANXIOUS"
    assert r_anx.sentiment_score < -0.2

    # Genuinamente Neutro
    r_neu = fast_sentiment_analyzer.analyze("Segue anexo a ata da reunião técnica realizada na terça-feira.")
    assert r_neu.sentiment == "NEUTRAL"
    assert r_neu.sentiment_score == 0.0


def test_fast_sentiment_analyzer_negation_handling():
    """Garante que frases como 'não tem problema' ou 'sem estresse' não sejam tratadas como negativas."""
    r = fast_sentiment_analyzer.analyze("Fica tranquilo, não tem problema nenhum, tudo certo.")
    assert r.sentiment in ("POSITIVE", "NEUTRAL", "CONFIDENT")
    assert r.sentiment != "FRUSTRATED"


def test_fast_sentiment_analyzer_performance():
    """Garante que o analisador execute em tempo imperceptível (< 1ms)."""
    t0 = time.perf_counter()
    for _ in range(100):
        fast_sentiment_analyzer.analyze(
            text="Preciso com urgência que você verifique o sensor 4 antes que dê problema crítico!!",
            urgency="HIGH",
            prosody_tone="TENSO_URGENTE",
            acoustic_score=-0.75,
        )
    elapsed_total_ms = (time.perf_counter() - t0) * 1000
    avg_ms = elapsed_total_ms / 100.0

    assert avg_ms < 1.0, f"Tempo médio {avg_ms:.3f}ms excedeu limite de 1.0ms"
