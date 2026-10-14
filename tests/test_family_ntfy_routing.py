"""Testes unitários para roteamento de notificações ntfy familiares e segregação de tópicos."""

import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.config import Settings
from src.contacts.models import ContactRecord
from src.contacts.service import contact_service
from src.notifications.service import NtfyNotificationService
from src.whatsapp.service import whatsapp_service


def test_ntfy_topic_properties():
    """Valida se as properties do Settings limpam URLs completas para slugs limpos."""
    s1 = Settings(NTFY_TOPIC="bruno-casa-dallas", NTFY_FAMILY_TOPIC="EEpT9fCTfBkjC4bg")
    assert s1.ntfy_general_topic == "bruno-casa-dallas"
    assert s1.ntfy_family_topic == "EEpT9fCTfBkjC4bg"

    # Se configurado com URL completa https://ntfy.sh/...
    s2 = Settings(
        NTFY_TOPIC="https://ntfy.sh/bruno-casa-dallas/",
        NTFY_FAMILY_TOPIC="https://ntfy.sh/EEpT9fCTfBkjC4bg",
    )
    assert s2.ntfy_general_topic == "bruno-casa-dallas"
    assert s2.ntfy_family_topic == "EEpT9fCTfBkjC4bg"


def test_resolve_family_status_wife():
    """Testa detecção da esposa pelo Papel Hierárquico FAMILY_CORE e atributos."""
    contact_wife = ContactRecord(
        id="wa_5544999214934",
        phone_number="5544999214934",
        name="Débora Patel Conter",
        nickname="Amor",
        role="FAMILY_CORE",
        notes="Minha esposa amada",
    )
    is_family, is_wife, rel = contact_service.resolve_family_status(contact=contact_wife)
    assert is_family is True
    assert is_wife is True
    assert rel == "Esposa"


def test_resolve_family_status_mother():
    """Testa detecção da mãe pelo Papel Hierárquico FAMILY_CORE."""
    contact_mother = ContactRecord(
        id="wa_5543999909260",
        phone_number="5543999909260",
        name="Jussara Conter",
        nickname="Mãe",
        role="FAMILY_CORE",
        notes="Mãe",
    )
    is_family, is_wife, rel = contact_service.resolve_family_status(contact=contact_mother)
    assert is_family is True
    assert is_wife is False
    assert rel == "Mãe"


def test_resolve_family_status_mother_in_law():
    """Testa detecção da sogra pelo Papel Hierárquico FAMILY_EXTENDED."""
    contact_sogra = ContactRecord(
        id="wa_554499440454",
        phone_number="554499440454",
        name="Joceli Patel",
        nickname="Joceli (Sogra)",
        role="FAMILY_EXTENDED",
        notes="Sogra",
    )
    is_family, is_wife, rel = contact_service.resolve_family_status(contact=contact_sogra)
    assert is_family is True
    assert is_wife is False
    assert rel == "Sogra"


def test_resolve_family_status_colleague_not_family():
    """Testa que colega de trabalho não é classificado como família."""
    contact_colleague = ContactRecord(
        id="wa_5544988887777",
        phone_number="5544988887777",
        name="Carlos Silva",
        nickname="Carlos",
        role="COLLEAGUE",
    )
    is_family, is_wife, rel = contact_service.resolve_family_status(contact=contact_colleague)
    assert is_family is False
    assert is_wife is False
    assert rel == ""


def test_resolve_family_status_owner_ignored():
    """Testa que o proprietário supremo nunca é tratado como contato de família de si mesmo."""
    is_family, is_wife, rel = contact_service.resolve_family_status(
        speaker="Bruno Conter", phone="554497604925"
    )
    assert is_family is False
    assert is_wife is False
    assert rel == "Proprietário"


@pytest.mark.asyncio
async def test_notify_family_message_routes_to_family_topic():
    """Testa se notify_family_message despacha corretamente para o tópico da família configurado."""
    service = NtfyNotificationService()
    service.send_notification = AsyncMock(return_value=True)

    await service.notify_family_message(
        speaker="Débora",
        text="Amor, me avisa quando sair!",
        message_type="text",
        is_wife=True,
        relationship="Esposa",
        contact_phone="5544999214934",
    )

    service.send_notification.assert_called_once()
    _, kwargs = service.send_notification.call_args
    assert kwargs["topic"] == service.family_topic
    assert "Débora (Esposa)" in kwargs["title"]
    assert "heart" in kwargs["tags"]
    assert kwargs["priority"] == 4


@pytest.mark.asyncio
async def test_whatsapp_webhook_routes_wife_text_to_family_topic():
    """Testa que mensagem de texto da esposa dispara notificação para o tópico familiar ntfy."""
    payload = {
        "event": "messages.upsert",
        "data": {
            "key": {
                "remoteJid": "5544999214934@s.whatsapp.net",
                "fromMe": False,
                "id": "WIFE_MSG_123",
            },
            "pushName": "Débora Patel",
            "message": {
                "conversation": "Amor, tudo bem?",
            },
            "messageTimestamp": int(time.time()),
        },
    }

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    mock_db.query.return_value.filter.return_value.all.return_value = []

    with patch("src.whatsapp.service.memory_repository.save_message", new_callable=AsyncMock) as mock_save, \
         patch("src.whatsapp.service.ntfy_service.notify_family_message", new_callable=AsyncMock) as mock_ntfy_family, \
         patch("src.whatsapp.service.contact_service.resolve_family_status", return_value=(True, True, "Esposa")):

        mock_saved_msg = MagicMock()
        mock_saved_msg.id = "saved_123"
        mock_saved_msg.sentiment = "POSITIVE"
        mock_saved_msg.sentiment_score = 0.8
        mock_save.return_value = mock_saved_msg

        res = await whatsapp_service.process_webhook_event(payload=payload, db=mock_db)
        assert res["status"] == "success"
        assert res["type"] == "text"

        mock_ntfy_family.assert_called_once()
        _, kwargs = mock_ntfy_family.call_args
        assert kwargs["is_wife"] is True
        assert kwargs["relationship"] == "Esposa"
        assert "Amor, tudo bem?" in kwargs["text"]
