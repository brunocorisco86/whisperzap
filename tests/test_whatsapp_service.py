"""Testes unitários e de integração para o serviço nativo WhatsApp / Evolution API."""

import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from src.main import app
from src.whatsapp.service import (
    whatsapp_service,
    sanitize_phone_number,
    TRIVIAL_GREETINGS,
)
from src.memory.database import init_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    init_db()


def test_sanitize_phone_number():
    """Valida a limpeza e extração de dígitos do identificador WhatsApp."""
    assert sanitize_phone_number("554499887766@s.whatsapp.net") == "554499887766"
    assert sanitize_phone_number("554499887766:12@s.whatsapp.net") == "554499887766"
    assert sanitize_phone_number("+55 (44) 9988-7766") == "554499887766"
    assert sanitize_phone_number("") == ""
    assert sanitize_phone_number(None) == ""


def test_extract_message_info_variations():
    """Testa a extração de metadados para diferentes formatos de eventos da Evolution API."""
    # 1. Mensagem de texto privada
    text_payload = {
        "event": "messages.upsert",
        "data": {
            "key": {
                "id": "msg_text_01",
                "remoteJid": "554499112233@s.whatsapp.net",
                "fromMe": False,
            },
            "pushName": "Carlos Cooperado",
            "messageType": "conversation",
            "message": {
                "conversation": "Olá, preciso checar o silo 3 da granja.",
            },
        },
    }
    info_text = whatsapp_service.extract_message_info(text_payload)
    assert info_text["key_id"] == "msg_text_01"
    assert info_text["phone_number"] == "554499112233"
    assert info_text["push_name"] == "Carlos Cooperado"
    assert info_text["is_group"] is False
    assert info_text["has_audio"] is False
    assert info_text["text"] == "Olá, preciso checar o silo 3 da granja."

    # 2. Mensagem de grupo (deve marcar is_group = True)
    group_payload = {
        "event": "messages.upsert",
        "data": {
            "key": {
                "id": "msg_group_01",
                "remoteJid": "120363028123456789@g.us",
                "participant": "554499112233@s.whatsapp.net",
            },
            "isGroup": True,
            "message": {"conversation": "Aviso geral no grupo"},
        },
    }
    info_group = whatsapp_service.extract_message_info(group_payload)
    assert info_group["is_group"] is True

    # 3. Mensagem de áudio
    audio_payload = {
        "event": "messages.upsert",
        "data": {
            "key": {
                "id": "msg_audio_01",
                "remoteJid": "554499112233@s.whatsapp.net",
                "fromMe": False,
            },
            "pushName": "Carlos Cooperado",
            "messageType": "audioMessage",
            "message": {
                "audioMessage": {
                    "mimetype": "audio/ogg; codecs=opus",
                    "seconds": 12,
                }
            },
        },
    }
    info_audio = whatsapp_service.extract_message_info(audio_payload)
    assert info_audio["has_audio"] is True
    assert info_audio["is_group"] is False


@pytest.mark.asyncio
async def test_process_webhook_ignores_group_and_stickers():
    """Garante que grupos e figurinhas são descartados sem processamento desnecessário."""
    # Grupo
    group_payload = {
        "data": {
            "key": {"id": "g1", "remoteJid": "12345@g.us"},
            "message": {"conversation": "Conversa de grupo"},
        }
    }
    res_g = await whatsapp_service.process_webhook_event(group_payload)
    assert res_g["status"] == "ignored"
    assert res_g["reason"] == "group_or_broadcast"

    # Sticker
    sticker_payload = {
        "data": {
            "key": {"id": "s1", "remoteJid": "554499998877@s.whatsapp.net"},
            "messageType": "stickerMessage",
            "message": {"stickerMessage": {}},
        }
    }
    res_s = await whatsapp_service.process_webhook_event(sticker_payload)
    assert res_s["status"] == "ignored"
    assert res_s["reason"] == "ignorable_media_type"


@pytest.mark.asyncio
async def test_process_webhook_text_message_and_bypass():
    """Testa o processamento de texto com bypass de saudação e salvamento no banco."""
    # Saudação curta -> bypass_ai = True
    greeting_payload = {
        "data": {
            "key": {"id": "m_greet_1", "remoteJid": "554499998877@s.whatsapp.net"},
            "pushName": "João Produtor",
            "message": {"conversation": "Bom dia!"},
        }
    }
    res = await whatsapp_service.process_webhook_event(greeting_payload)
    assert res["status"] == "success"
    assert res["type"] == "text"
    assert res["bypass_ai"] is True


@pytest.mark.asyncio
async def test_process_webhook_hermes_query():
    """Testa comando '?' direcionado ao Hermes Agent com resposta automática."""
    query_payload = {
        "data": {
            "key": {"id": "m_query_1", "remoteJid": "554499998877@s.whatsapp.net", "fromMe": False},
            "pushName": "Bruno",
            "message": {"conversation": "? Qual o status do silo de ração da C.Vale?"},
        }
    }

    from src.ai_gateway.schemas import HermesQueryResponse, MemorySourceCitation
    mock_rag_response = HermesQueryResponse(
        query="Qual o status do silo de ração da C.Vale?",
        answer="O nível do Silo 3 está em 68% com ração de crescimento C.Vale.",
        sources=[MemorySourceCitation(message_id="m1", speaker="Bruno", text_snippet="Silo 3", similarity=0.95)],
        related_entities=["Silo 3 (EQUIPMENT)"],
        pending_tasks_mentioned=[],
        processing_time_ms=12.5,
        provider="gemini",
        model="gemini-3.1-flash-lite",
    )

    with patch.object(whatsapp_service, "send_text_message", new_callable=AsyncMock) as mock_send, \
         patch("src.memory.repository.memory_repository.query_hermes_rag", new_callable=AsyncMock) as mock_rag:
        mock_send.return_value = True
        mock_rag.return_value = mock_rag_response
        res = await whatsapp_service.process_webhook_event(query_payload)

        assert res["status"] == "success"
        assert res["type"] == "hermes_query"
        assert "silo" in res["query"].lower()
        assert len(res["answer"]) > 0
        mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_process_webhook_audio_flow_mocked():
    """Testa o pipeline completo de áudio (download base64 -> Whisper -> IA Revise -> Envio -> Persistência)."""
    # 100 bytes dummy base64
    dummy_base64 = "T2dnUwACAAAAAAAAAAA="

    audio_payload = {
        "data": {
            "key": {"id": "audio_test_123", "remoteJid": "554499881122@s.whatsapp.net", "fromMe": False},
            "pushName": "Debora Patel",
            "messageType": "audioMessage",
            "message": {"audioMessage": {"seconds": 5}},
        }
    }

    with patch.object(whatsapp_service, "get_media_base64", new_callable=AsyncMock) as mock_media, \
         patch.object(whatsapp_service, "send_text_message", new_callable=AsyncMock) as mock_send, \
         patch("src.transcriber.service.whisper_service.transcribe_audio", new_callable=AsyncMock) as mock_transcribe:

        mock_media.return_value = dummy_base64
        from src.transcriber.prosody_analyzer import ProsodyAnalyzer
        mock_transcribe.return_value = (
            "solicito a entrega de ração no silo dois amanha",
            "pt",
            0.99,
            5.0,
            [],
            ProsodyAnalyzer.analyze_speech_prosody(5.0, [], "solicito a entrega de ração no silo dois amanha"),
        )
        mock_send.return_value = True

        res = await whatsapp_service.process_webhook_event(audio_payload)

        assert res["status"] == "success"
        assert res["type"] == "audio"
        assert res["speaker"] == "Debora Patel"
        assert "ração" in res["text"].lower()
        # Garante que NENHUMA mensagem foi enviada para o terceiro (proteção de privacidade e anti-looping)
        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_process_webhook_self_memo_voice_with_tasks():
    """Testa a funcionalidade de Nota Pessoal (Self-Memo) gravada para si mesmo com extração de tarefas."""
    dummy_base64 = "T2dnUwACAAAAAAAAAAA="

    self_memo_payload = {
        "data": {
            "key": {"id": "self_memo_01", "remoteJid": "554497604925@s.whatsapp.net", "fromMe": True},
            "pushName": "Bruno Conter",
            "messageType": "audioMessage",
            "message": {"audioMessage": {"seconds": 8}},
        }
    }

    with patch.object(whatsapp_service, "get_media_base64", new_callable=AsyncMock) as mock_media, \
         patch.object(whatsapp_service, "send_text_message", new_callable=AsyncMock) as mock_send, \
         patch("src.transcriber.service.whisper_service.transcribe_audio", new_callable=AsyncMock) as mock_transcribe:

        mock_media.return_value = dummy_base64
        from src.transcriber.prosody_analyzer import ProsodyAnalyzer
        mock_transcribe.return_value = (
            "lembrar de ligar para o fornecedor de racao amanha cedo",
            "pt",
            0.99,
            8.0,
            [],
            ProsodyAnalyzer.analyze_speech_prosody(8.0, [], "lembrar de ligar para o fornecedor de racao amanha cedo"),
        )
        mock_send.return_value = True

        res = await whatsapp_service.process_webhook_event(self_memo_payload)

        assert res["status"] == "success"
        assert res["type"] == "audio"
        assert res["is_self_memo"] is True
        assert "Nota Pessoal" in res["speaker"]
        mock_send.assert_called_once()
        sent_text = mock_send.call_args[1]["text"]
        assert "Nota Pessoal Gravada" in sent_text


def test_whatsapp_router_endpoints():
    """Testa os endpoints HTTP do router FastAPI /api/v1/whatsapp com enfileiramento e deduplicação."""
    # 1. Envio de texto
    with patch.object(whatsapp_service, "send_text_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        res_send = client.post("/api/v1/whatsapp/send-text", json={"number": "554499887766", "text": "Teste Monólito"})
        assert res_send.status_code == 200
        assert res_send.json()["success"] is True

    # 2. Webhook HTTP POST com enfileiramento assíncrono (200 OK imediato)
    sample_payload = {
        "event": "messages.upsert",
        "data": {
            "key": {"id": "unique_msg_100", "remoteJid": "554499112233@s.whatsapp.net", "fromMe": False},
            "pushName": "Carlos Teste",
            "message": {"conversation": "Mensagem teste de fila"},
        },
    }
    with patch.object(whatsapp_service, "process_webhook_event_task", new_callable=AsyncMock):
        res_hook = client.post("/api/v1/whatsapp/webhook", json=sample_payload)
        assert res_hook.status_code == 200
        assert res_hook.json()["status"] == "queued"
        assert res_hook.json()["key_id"] == "unique_msg_100"

        # 3. Segunda tentativa do mesmo key_id deve ser ignorada como duplicata
        res_duplicate = client.post("/api/v1/whatsapp/webhook", json=sample_payload)
        assert res_duplicate.status_code == 200
        assert res_duplicate.json()["status"] == "ignored"
        assert res_duplicate.json()["reason"] == "duplicate_key_id"


def test_whatsapp_service_deduplication():
    """Testa o mecanismo de deduplicação atômica de key_id."""
    key = f"test_dedup_{uuid.uuid4().hex}"
    # Primeira verificação: não é duplicado e registra
    assert whatsapp_service.is_key_duplicate_or_processing(key) is False
    # Segunda verificação imediata: deve retornar True (duplicado)
    assert whatsapp_service.is_key_duplicate_or_processing(key) is True

