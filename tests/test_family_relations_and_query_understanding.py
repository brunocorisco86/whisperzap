"""Testes automatizados para resolução de relações familiares e tags de contatos no Hermes Query Understanding."""

import pytest
from unittest.mock import AsyncMock, patch
from src.memory.query_understanding import hermes_query_understanding
from src.whatsapp.service import whatsapp_service


def test_resolve_family_relation_wife():
    """Valida que consultas sobre esposa, mulher e patroa resolvem diretamente para Débora Patel."""
    for q in [
        "O que conversei com a minha esposa hoje?",
        "?O que conversei com a minha mulher hoje?",
        "O que a patroa me pediu?",
        "O que conversei com minha esposa?",
    ]:
        parsed = hermes_query_understanding.analyze_query(q)
        assert parsed.target_speaker == "Debora", f"Falhou para query: {q}"
        assert "Debora" in (parsed.target_speaker_full_name or "")
        assert parsed.intent == "INTERLOCUTOR_DIALOGUE"


def test_resolve_family_relation_mother():
    """Valida que consultas sobre mãe resolvem para Jussara Conter."""
    for q in [
        "O que conversei com a minha mãe hoje?",
        "O que a minha mae me mandou ontem?",
        "O que falei com mamãe?",
    ]:
        parsed = hermes_query_understanding.analyze_query(q)
        assert parsed.target_speaker == "Jussara", f"Falhou para query: {q}"
        assert "Jussara" in (parsed.target_speaker_full_name or "")


def test_resolve_family_relation_mother_in_law():
    """Valida que consultas sobre sogra resolvem para Joceli Patel."""
    for q in [
        "O que a minha sogra falou?",
        "? O que conversei com a sogra hoje?",
    ]:
        parsed = hermes_query_understanding.analyze_query(q)
        assert parsed.target_speaker == "Joceli", f"Falhou para query: {q}"
        assert "Joceli" in (parsed.target_speaker_full_name or "")


def test_family_words_do_not_hijack_unrelated_vcard_contacts():
    """Garante que contatos vCard contendo 'ESPOSA' no nome não sequestram a busca."""
    parsed = hermes_query_understanding.analyze_query("O que conversei com a minha esposa hoje?")
    assert parsed.target_speaker != "Andrei"
    assert "Andrei" not in (parsed.target_speaker_full_name or "")


@pytest.mark.asyncio
async def test_whatsapp_service_send_presence():
    """Valida envio de status de presença visual ('composing') para feedback anti-vácuo."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200

        ok = await whatsapp_service.send_presence(number="554497604925", presence="composing")
        assert ok is True
        mock_post.assert_called_once()
        assert "chat/sendPresence" in mock_post.call_args[0][0]
