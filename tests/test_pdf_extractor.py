"""Testes unitários e de integração para o extrator de PDF e fluxo WhatsApp."""

import base64
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import pymupdf
from src.main import app
from src.ai_gateway.pdf_extractor import (
    PDFExtractor,
    PDFTooLargeError,
    PDFExtractionError,
    MAX_PDF_SIZE_BYTES,
    pdf_extractor,
)
from src.whatsapp.service import whatsapp_service
from src.memory.database import init_db
from src.config import settings


@pytest.fixture(autouse=True)
def setup_database():
    init_db()


def _create_sample_pdf_bytes(text: str = "Relatorio de Producao\nSilo 1: 90%") -> bytes:
    """Gera bytes de um PDF válido em memória usando pymupdf."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.mark.asyncio
async def test_pdf_extractor_rejects_oversized_pdf():
    """Trava de Segurança VPS: Rejeita PDFs com tamanho superior a 15 MB."""
    extractor = PDFExtractor()
    oversized_bytes = b"0" * (MAX_PDF_SIZE_BYTES + 1024)

    with pytest.raises(PDFTooLargeError) as exc_info:
        await extractor.extract(oversized_bytes, filename="arquivo_pesado.pdf")

    assert "excede o limite máximo permitido de 15 MB" in str(exc_info.value)


@pytest.mark.asyncio
async def test_pdf_extractor_tier1_gemini_success():
    """Testa sucesso imediato no Tier 1 (Gemini 3.5 Flash Lite) sem necessidade de fallback."""
    extractor = PDFExtractor()
    pdf_bytes = _create_sample_pdf_bytes("Tabela de Conversão Alimentar")
    mock_md = "# Tabela de Conversão Alimentar\n| Lote | CA |\n| 101 | 1.55 |"

    with patch.object(extractor, "_try_gemini_extract", new_callable=AsyncMock) as mock_extract:
        mock_extract.return_value = mock_md

        result = await extractor.extract(pdf_bytes, filename="lotes.pdf")

        assert result.success is True
        assert result.tier_used == "tier1_gemini"
        assert result.model_name == "gemini-3.5-flash-lite"
        assert result.markdown == mock_md
        assert result.page_count >= 1
        mock_extract.assert_called_once()


@pytest.mark.asyncio
async def test_pdf_extractor_tier2_fallback_on_tier1_error():
    """Testa acionamento do Tier 2 (Gemini 2.5 Flash) quando Tier 1 falha com 429 ou 503."""
    extractor = PDFExtractor()
    pdf_bytes = _create_sample_pdf_bytes("Documento Estratégico")
    mock_md_tier2 = "## Documento Estratégico\n- Ponto 1\n- Ponto 2"

    async def side_effect(pdf_base64: str, model_name: str, timeout: float = 60.0):
        if "3.5-flash-lite" in model_name:
            raise RuntimeError("HTTP 429: Resource has been exhausted (rate limit)")
        return mock_md_tier2

    with patch.object(extractor, "_try_gemini_extract", side_effect=side_effect):
        result = await extractor.extract(pdf_bytes, filename="estrategico.pdf")

        assert result.success is True
        assert result.tier_used == "tier2_gemini"
        assert result.model_name == "gemini-2.5-flash"
        assert result.markdown == mock_md_tier2


@pytest.mark.asyncio
async def test_pdf_extractor_tier3_emergency_local_fallback():
    """Testa contingência local de emergência (Tier 3: PyMuPDF4LLM) quando ambos os tiers de API falham."""
    extractor = PDFExtractor()
    original_text = "Conteúdo de emergência local para validação de contingência."
    pdf_bytes = _create_sample_pdf_bytes(original_text)

    # Força falha em todas as chamadas Gemini
    with patch.object(extractor, "_try_gemini_extract", side_effect=Exception("API Unreachable")):
        result = await extractor.extract(pdf_bytes, filename="contingencia.pdf")

        assert result.success is True
        assert result.tier_used == "tier3_pymupdf"
        assert result.model_name == "pymupdf4llm"
        assert "Conteúdo de emergência local" in result.markdown
        assert result.page_count >= 1


def test_whatsapp_service_extract_message_info_with_pdf():
    """Valida a identificação de documento PDF no parser de webhooks da Evolution API."""
    pdf_payload = {
        "event": "messages.upsert",
        "data": {
            "key": {
                "id": "msg_pdf_01",
                "remoteJid": f"{settings.USER_PHONE_NUMBER}@s.whatsapp.net",
                "fromMe": True,
            },
            "pushName": "Bruno Conter",
            "messageType": "documentMessage",
            "message": {
                "documentMessage": {
                    "mimetype": "application/pdf",
                    "fileName": "balancete_mensal.pdf",
                    "caption": "Segue o balancete de agosto",
                    "fileLength": 1048576,
                }
            },
        },
    }

    info = whatsapp_service.extract_message_info(pdf_payload)
    assert info is not None
    assert info["has_pdf"] is True
    assert info["has_audio"] is False
    assert info["pdf_filename"] == "balancete_mensal.pdf"
    assert info["caption"] == "Segue o balancete de agosto"
    assert info["is_self_memo"] is True


@pytest.mark.asyncio
async def test_whatsapp_service_process_webhook_pdf_success():
    """Testa o processamento de ponta a ponta de um PDF recebido no WhatsApp."""
    pdf_bytes = _create_sample_pdf_bytes("Relatório Semanal de Avicultura\nIEP Médio: 395")
    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    pdf_payload = {
        "event": "messages.upsert",
        "data": {
            "key": {
                "id": "msg_pdf_full_01",
                "remoteJid": f"{settings.USER_PHONE_NUMBER}@s.whatsapp.net",
                "fromMe": True,
            },
            "pushName": "Bruno Conter",
            "messageType": "documentMessage",
            "message": {
                "documentMessage": {
                    "mimetype": "application/pdf",
                    "fileName": "relatorio_iep.pdf",
                    "base64": pdf_b64,
                }
            },
        },
    }

    with patch.object(whatsapp_service, "send_text_message", new_callable=AsyncMock) as mock_send, \
         patch.object(pdf_extractor, "extract", new_callable=AsyncMock) as mock_extract:

        from src.ai_gateway.pdf_extractor import PDFExtractionResult
        mock_extract.return_value = PDFExtractionResult(
            markdown="### Relatório Semanal de Avicultura\nIEP Médio: 395",
            tier_used="tier1_gemini",
            model_name="gemini-3.5-flash-lite",
            filename="relatorio_iep.pdf",
            size_bytes=len(pdf_bytes),
            page_count=1,
            success=True,
        )

        res = await whatsapp_service.process_webhook_event(pdf_payload)

        assert res["status"] == "success"
        assert res["type"] == "pdf"
        assert res["filename"] == "relatorio_iep.pdf"
        assert res["tier_used"] == "tier1_gemini"
        assert mock_send.called
        # Garante que enviou mensagem de feedback para o proprietário
        sent_text = mock_send.call_args[1]["text"]
        assert "Documento" in sent_text
        assert "relatorio_iep.pdf" in sent_text


@pytest.mark.asyncio
async def test_whatsapp_service_process_webhook_pdf_too_large():
    """Testa a rejeição no webhook para PDFs maiores que 15 MB com alerta de segurança."""
    oversized_bytes = b"%" + b"0" * (MAX_PDF_SIZE_BYTES + 500)
    pdf_b64 = base64.b64encode(oversized_bytes).decode("utf-8")

    pdf_payload = {
        "event": "messages.upsert",
        "data": {
            "key": {
                "id": "msg_pdf_large_01",
                "remoteJid": f"{settings.USER_PHONE_NUMBER}@s.whatsapp.net",
                "fromMe": True,
            },
            "pushName": "Bruno Conter",
            "messageType": "documentMessage",
            "message": {
                "documentMessage": {
                    "mimetype": "application/pdf",
                    "fileName": "manual_gigante.pdf",
                    "base64": pdf_b64,
                }
            },
        },
    }

    with patch.object(whatsapp_service, "send_text_message", new_callable=AsyncMock) as mock_send:
        res = await whatsapp_service.process_webhook_event(pdf_payload)

        assert res["status"] == "error"
        assert res["reason"] == "pdf_too_large"
        assert mock_send.called
        sent_text = mock_send.call_args[1]["text"]
        assert "15 MB" in sent_text
