"""Testes unitários e de integração para o serviço nativo WhatsApp / Evolution API."""

import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from src.main import app
from src.config import settings
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
            "key": {"id": "m_query_1", "remoteJid": "554497604925@s.whatsapp.net", "fromMe": True},
            "pushName": "Bruno Conter",
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
        # Garante que a transcrição foi enviada para o proprietário com o cabeçalho do remetente
        mock_send.assert_called_once()
        sent_number = mock_send.call_args[1]["number"]
        sent_text = mock_send.call_args[1]["text"]
        assert sent_number == settings.USER_PHONE_NUMBER
        assert "*Áudio Recebido de:* Debora Patel" in sent_text


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


def test_format_terpsicore_task_verbose_complete():
    """Testa a renderização rica de tarefa Terpsícore com todos os atributos estratégicos."""
    from src.whatsapp.service import format_terpsicore_task_verbose
    from src.memory.models import TaskRecord

    task = TaskRecord(
        id="t-123",
        title="Construir novo silo de secagem",
        priority="URGENT",
        due_date="2026-10-15",
        assignee="Rafael Gerente",
        is_favorite=True,
        is_epic=True,
        is_idea=True,
        in_vault=True,
        vault_reason="Aguardando liberação de crédito",
        procrastination_factor="FINANCIAL",
    )

    formatted = format_terpsicore_task_verbose(task)
    assert "🔴 *[URGENTE]*" in formatted
    assert "Construir novo silo de secagem" in formatted
    assert "⭐ *Favorito*" in formatted
    assert "🏛️ *Objetivo Épico*" in formatted
    assert "💡 *Ideia/Semente*" in formatted
    assert "🗝️ *No Baú (Vault)* (Aguardando liberação de crédito)" in formatted
    assert "📅 Prazo: 2026-10-15" in formatted
    assert "👤 Resp: Rafael Gerente" in formatted
    assert "⏱️ Radar: FINANCIAL" in formatted


@pytest.mark.asyncio
async def test_process_webhook_self_memo_voice_with_verbose_signaled_tasks():
    """Testa que notas pessoais de voz com tarefas sinalizadas enviam texto rico no WhatsApp."""
    dummy_base64 = "T2dnUwACAAAAAAAAAAA="

    self_memo_payload = {
        "data": {
            "key": {"id": "self_memo_signaled_02", "remoteJid": "554497604925@s.whatsapp.net", "fromMe": True},
            "pushName": "Bruno Conter",
            "messageType": "audioMessage",
            "message": {"audioMessage": {"seconds": 12}},
        }
    }

    from src.ai_gateway.schemas import SemanticExtractionResponse, ExtractedTask
    mock_extracted = SemanticExtractionResponse(
        intent="TASK",
        summary="Anotar ideia urgente para projeto de sensores",
        sentiment="NEUTRAL",
        sentiment_score=0.0,
        tasks=[
            ExtractedTask(
                title="Implementar projeto anual dos sensores dos silos",
                priority="URGENT",
                due_date="2026-10-15",
                assignee="Bruno",
            )
        ],
        entities=[],
        triples=[],
        decisions=[],
        ideas=["Ideia de sensores nos silos"],
        topics=["Projetos"],
        urgency="URGENT",
        provider="mock",
        model="mock",
        processing_time_ms=10.0,
    )

    with patch.object(whatsapp_service, "get_media_base64", new_callable=AsyncMock) as mock_media, \
         patch.object(whatsapp_service, "send_text_message", new_callable=AsyncMock) as mock_send, \
         patch("src.transcriber.service.whisper_service.transcribe_audio", new_callable=AsyncMock) as mock_transcribe, \
         patch("src.ai_gateway.extractor.semantic_extractor.extract", new_callable=AsyncMock) as mock_extract:

        mock_media.return_value = dummy_base64
        mock_extract.return_value = mock_extracted
        from src.transcriber.prosody_analyzer import ProsodyAnalyzer
        mock_transcribe.return_value = (
            "anotar ideia urgente para o projeto anual dos sensores dos silos",
            "pt",
            0.99,
            12.0,
            [],
            ProsodyAnalyzer.analyze_speech_prosody(12.0, [], "anotar ideia urgente para o projeto anual dos sensores dos silos"),
        )
        mock_send.return_value = True

        res = await whatsapp_service.process_webhook_event(self_memo_payload)

        assert res["status"] == "success"
        assert res["type"] == "audio"
        assert res["is_self_memo"] is True
        mock_send.assert_called_once()
        sent_text = mock_send.call_args[1]["text"]
        assert "Nota Pessoal Gravada" in sent_text
        assert "📋 *Tarefas Sinalizadas (Terpsícore):*" in sent_text
        assert "🔴 *[URGENTE]* *Implementar projeto anual dos sensores dos silos*" in sent_text
        assert "🏛️ *Objetivo Épico*" in sent_text or "💡 *Ideia/Semente*" in sent_text


@pytest.mark.asyncio
async def test_process_webhook_modelos_diagnostic_command():
    """Testa que comando ? modelos dispara a conferência e responde com relatório visual."""
    payload = {
        "data": {
            "key": {"id": "cmd_models_01", "remoteJid": "554497604925@s.whatsapp.net", "fromMe": True},
            "pushName": "Bruno Conter",
            "messageType": "conversation",
            "message": {"conversation": "? modelos"},
        }
    }

    mock_check_result = {
        "status": "success",
        "summary": "4/5 modelos viáveis",
        "active_models": {"revise": "gemini-3.5-flash-lite", "hermes": "gemini-3.7-flash"},
        "model_checks": [
            {"model": "gemini-3.5-flash-lite", "tier": "LITE", "viable": True, "status": "HEALTHY", "latency_ms": 310},
            {"model": "gemini-3.7-flash", "tier": "FLASH", "viable": False, "status": "OVERLOADED", "latency_ms": 820, "error": "HTTP 503"},
        ],
        "auto_remediated": True,
        "remediation_details": {"hermes": "gemini-3.7-flash (OVERLOADED) ➔ gemini-3.5-flash-lite"},
    }

    with patch("src.ai_gateway.model_registry.model_registry.check_viable_models", new_callable=AsyncMock) as mock_check, \
         patch.object(whatsapp_service, "send_text_message", new_callable=AsyncMock) as mock_send:

        mock_check.return_value = mock_check_result
        mock_send.return_value = True

        res = await whatsapp_service.process_webhook_event(payload)

        assert res["status"] == "success"
        assert res["type"] == "hermes_models_check"
        mock_send.assert_called_once()
        sent_text = mock_send.call_args[1]["text"]
        assert "Diagnóstico de Modelos de IA (Hermes)" in sent_text
        assert "gemini-3.5-flash-lite" in sent_text
        assert "Auto-Recuperação Acionada" in sent_text



