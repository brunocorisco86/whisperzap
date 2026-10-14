"""Testes automatizados para o Motor de Visão Local 100% Zero-Token (YOLO11n ONNX + Detector de Documento)."""

import pytest
import pymupdf
from src.ai_gateway.vision_local import vision_local_engine, VisionResult


def _create_synthetic_test_image(width: int = 200, height: int = 200, color=(1, 0, 0)) -> bytes:
    """Gera uma imagem sintética PNG em memória via PyMuPDF puro."""
    doc = pymupdf.open()
    page = doc.new_page(width=width, height=height)
    page.draw_rect([10, 10, width - 10, height - 10], color=color, fill=color)
    png_bytes = page.get_pixmap().tobytes("png")
    doc.close()
    return png_bytes


def _create_synthetic_document_image() -> bytes:
    """Gera uma imagem sintética com aspecto de folha A4 / cupom (aspect ratio 1.41) com fundo claro."""
    doc = pymupdf.open()
    # Aspect ratio A4 (595 x 842)
    page = doc.new_page(width=300, height=424)
    # Fundo branco
    page.draw_rect([0, 0, 300, 424], color=(1, 1, 1), fill=(1, 1, 1))
    page.insert_text((30, 50), "DANFE - NOTA FISCAL ELETRONICA", color=(0, 0, 0))
    page.insert_text((30, 80), "CHAVE DE ACESSO: 4124 0982 1200 1200", color=(0, 0, 0))
    page.insert_text((30, 110), "VALOR TOTAL: R$ 1.540,00", color=(0, 0, 0))
    png_bytes = page.get_pixmap().tobytes("png")
    doc.close()
    return png_bytes


def test_vision_engine_empty_input():
    """Valida resiliência contra imagens nulas ou corrompidas."""
    res = vision_local_engine.classify_image(b"")
    assert isinstance(res, VisionResult)
    assert res.is_document is False
    assert res.tokens_consumed == 0


def test_vision_engine_document_detection():
    """Valida identificação de documento/nota fiscal localmente com zero tokens."""
    doc_bytes = _create_synthetic_document_image()
    res = vision_local_engine.classify_image(doc_bytes, caption="Segue a nota fiscal da entrega")

    assert isinstance(res, VisionResult)
    assert res.is_document is True
    assert "Nota Fiscal" in res.summary or "Documento" in res.summary
    assert "Segue a nota fiscal" in res.summary
    assert res.tokens_consumed == 0
    assert res.inference_time_ms > 0.0


def test_vision_engine_yolo_inference_resilience():
    """Valida inferência YOLO11n ONNX sobre imagem arbitrária sem exceções."""
    img_bytes = _create_synthetic_test_image(width=640, height=640, color=(0.2, 0.4, 0.8))
    res = vision_local_engine.classify_image(img_bytes, caption="Verificação de rotina")

    assert isinstance(res, VisionResult)
    assert res.tokens_consumed == 0
    assert res.inference_time_ms < 300.0  # CPU inference deve ser < 300ms


def test_whatsapp_service_extract_image_info():
    """Valida se o whatsapp_service reconhece eventos de imageMessage corretamente."""
    from src.whatsapp.service import whatsapp_service

    payload_image = {
        "event": "messages.upsert",
        "data": {
            "key": {
                "id": "IMG_TEST_12345",
                "remoteJid": "554497604925@s.whatsapp.net",
                "fromMe": False,
            },
            "pushName": "Valdecir",
            "messageType": "imageMessage",
            "message": {
                "imageMessage": {
                    "caption": "Foto do caminhão de ração no silo",
                    "mimetype": "image/jpeg",
                }
            },
            "messageTimestamp": 1728860000,
        },
    }

    info = whatsapp_service.extract_message_info(payload_image)
    assert info is not None
    assert info["has_image"] is True
    assert info["has_audio"] is False
    assert info["has_pdf"] is False
    assert info["caption"] == "Foto do caminhão de ração no silo"
    assert info["key_id"] == "IMG_TEST_12345"
