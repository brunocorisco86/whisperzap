"""Testes automatizados para a conversão e consistência de Timezone (Horário de Brasília / America/Sao_Paulo)."""

from datetime import datetime, timezone
from src.memory.timezone_utils import to_local_tz, format_brt, get_now_brt, BRASILIA_TZ
from src.ai_gateway.prompts import HERMES_QUERY_USER_TEMPLATE


def test_utc_to_brasilia_conversion():
    """Valida a conversão correta de um timestamp UTC tarde da noite para o dia correto no Brasil."""
    # 18 de agosto às 01:20 UTC é 17 de agosto às 22:20 no horário de Brasília (UTC-3)
    dt_utc = datetime(2026, 8, 18, 1, 20, 0, tzinfo=timezone.utc)
    dt_brt = to_local_tz(dt_utc)

    assert dt_brt.day == 17
    assert dt_brt.month == 8
    assert dt_brt.year == 2026
    assert dt_brt.hour == 22
    assert dt_brt.minute == 20

    formatted = format_brt(dt_utc)
    assert formatted == "17/08/2026 22:20"


def test_naive_datetime_handling():
    """Valida que datetimes naive do banco são tratados como UTC e convertidos corretamente."""
    dt_naive = datetime(2026, 8, 18, 2, 45, 0)
    formatted = format_brt(dt_naive)
    assert formatted == "17/08/2026 23:45"


def test_hermes_prompt_contains_brasilia_datetime_header():
    """Valida que o template de prompt do Hermes exige e formata o horário de Brasília."""
    rendered_prompt = HERMES_QUERY_USER_TEMPLATE.format(
        current_datetime="17/08/2026 22:45:00 (Segunda-feira)",
        query="sobre o que conversei hoje?",
        retrieved_context="Memória de teste",
        graph_context="Grafo de teste",
        tasks_context="Tarefas de teste",
    )

    assert "Horário Oficial de Brasília / UTC-3" in rendered_prompt
    assert "17/08/2026 22:45:00" in rendered_prompt
