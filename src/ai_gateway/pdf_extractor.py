"""Módulo de Extração e Conversão de Documentos PDF para Markdown (GFM).

Whisperzap - Arquitetura de Alta Disponibilidade com Cascata de Fallback:
- Tier 1 (Prioritário): Gemini Moderno (gemini-3.5-flash-lite / gemini-3.0-flash)
- Tier 2 (Fallback): Gemini Moderno Secundário (gemini-2.5-flash / gemini-3.0-flash)
- Tier 3 (Contingência Local de Emergência): pymupdf4llm (sem uso de API, leve para VPS 4GB)

Restrições de Recursos e Segurança (VPS KVM 1):
- Trava de segurança estrita: Rejeição imediata de PDFs > 15 MB para evitar estouro de memória (OOM).
- Zero dependências de deep learning local (sem PyTorch, Transformers ou EasyOCR).
- Conversão 100% GFM (GitHub Flavored Markdown) com tabelas pipes e títulos hierárquicos.
"""

import base64
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional, Union

import pymupdf
import pymupdf4llm

from src.ai_gateway.model_registry import ModelRegistry
from src.ai_gateway.prompts import PDF_EXTRACT_SYSTEM_PROMPT, PDF_EXTRACT_USER_PROMPT
from src.ai_gateway.providers.gemini import GeminiProvider
from src.config import settings

logger = logging.getLogger(__name__)

# Trava estrita de segurança para VPS com margem livre de memória ~800MB - 1.1GB
MAX_PDF_SIZE_BYTES: int = 15 * 1024 * 1024  # 15 MB
DEFAULT_TIER1_MODEL: str = "gemini-3.5-flash-lite"
DEFAULT_TIER2_MODEL: str = "gemini-2.5-flash"
DEFAULT_TIER3_NAME: str = "pymupdf4llm"


class PDFExtractionError(Exception):
    """Exceção base para falhas no processamento de PDF."""
    pass


class PDFTooLargeError(PDFExtractionError):
    """Exceção levantada quando o arquivo PDF ultrapassa o limite seguro de 15 MB."""
    pass


@dataclass
class PDFExtractionResult:
    """Resultado estruturado da extração de documento PDF."""
    markdown: str
    tier_used: str  # "tier1_gemini", "tier2_gemini", "tier3_pymupdf"
    model_name: str
    filename: str
    size_bytes: int
    page_count: int
    success: bool = True
    error_message: Optional[str] = None


class PDFExtractor:
    """Extrator de documentos PDF com suporte a cascata de alta disponibilidade e fallback local."""

    def __init__(self, model_registry: Optional[ModelRegistry] = None):
        self.registry = model_registry or ModelRegistry()

    def _clean_markdown_output(self, text: str) -> str:
        """Remove cercas de bloco Markdown redundantes caso a LLM retorne envolto em ```markdown."""
        cleaned = text.strip()
        # Remove blocos ```markdown ... ``` envolventes totais
        match = re.match(r"^```(?:markdown)?\s*\n([\s\S]*?)\n```$", cleaned, flags=re.IGNORECASE)
        if match:
            cleaned = match.group(1).strip()
        return cleaned

    def _normalize_input_to_bytes(self, pdf_input: Union[bytes, str]) -> bytes:
        """Normaliza entrada recebida (bytes, string base64 ou caminho de arquivo) para bytes binários."""
        if isinstance(pdf_input, bytes):
            return pdf_input

        if isinstance(pdf_input, str):
            # Se for caminho de arquivo no disco
            if os.path.isfile(pdf_input):
                with open(pdf_input, "rb") as f:
                    return f.read()

            # Se for string base64 (removendo data URI scheme se presente)
            data_str = pdf_input.strip()
            if "," in data_str and "base64" in data_str[:50]:
                data_str = data_str.split(",", 1)[1]

            try:
                return base64.b64decode(data_str)
            except Exception as e:
                raise PDFExtractionError(f"Falha ao decodificar string base64 do PDF: {e}") from e

        raise PDFExtractionError(f"Tipo de entrada não suportado para PDF: {type(pdf_input)}")

    def _extract_local_contingency(self, pdf_bytes: bytes, filename: str) -> tuple[str, int]:
        """Tier 3: Extração local de emergência usando PyMuPDF4LLM em memória."""
        try:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
            page_count = len(doc)
            # Converte as páginas para Markdown estruturado
            markdown_content = pymupdf4llm.to_markdown(doc)
            doc.close()
            return markdown_content.strip(), page_count
        except Exception as exc:
            logger.error(f"[PDFExtractor] Falha catastrófica no Tier 3 local ({filename}): {exc}")
            raise PDFExtractionError(f"Erro ao extrair PDF localmente via pymupdf4llm: {exc}") from exc

    async def _try_gemini_extract(
        self,
        pdf_base64: str,
        model_name: str,
        timeout: float = 60.0,
    ) -> str:
        """Chama a API do Gemini enviando o PDF como inlineData multimodal."""
        key = settings.GEMINI_API_KEY
        if not key or key.startswith("sua_chave"):
            raise ValueError("GEMINI_API_KEY não configurada ou inválida.")

        provider = GeminiProvider(api_key=key, model_name=model_name)
        raw_md = await provider.generate_from_inline_data(
            data_base64=pdf_base64,
            mime_type="application/pdf",
            prompt=PDF_EXTRACT_USER_PROMPT,
            system_instruction=PDF_EXTRACT_SYSTEM_PROMPT,
            temperature=0.0,
            model_name=model_name,
            timeout=timeout,
        )
        return self._clean_markdown_output(raw_md)

    async def extract(
        self,
        pdf_input: Union[bytes, str],
        filename: str = "documento.pdf",
        custom_tier1_model: Optional[str] = None,
        custom_tier2_model: Optional[str] = None,
        allow_fallback: bool = True,
    ) -> PDFExtractionResult:
        """Executa a extração do PDF através do roteador com cascata de alta disponibilidade:
        1. Validação de tamanho (máximo 15 MB);
        2. Tier 1: Gemini 3.5 Flash Lite / 3.0 Flash;
        3. Tier 2: Gemini 2.5 Flash (Fallback para 429/503/timeout);
        4. Tier 3: PyMuPDF4LLM local (Contingência de emergência).
        """
        # 1. Normalização e Validação de Tamanho
        pdf_bytes = self._normalize_input_to_bytes(pdf_input)
        size_bytes = len(pdf_bytes)

        if size_bytes > MAX_PDF_SIZE_BYTES:
            size_mb = size_bytes / (1024 * 1024)
            logger.warning(f"🚨 [PDFExtractor] PDF rejeitado: {filename} tem {size_mb:.2f} MB (limite: 15 MB).")
            raise PDFTooLargeError(
                f"O arquivo {filename} possui {size_mb:.2f} MB e excede o limite máximo permitido de 15 MB."
            )

        if size_bytes == 0:
            raise PDFExtractionError(f"O documento {filename} está vazio (0 bytes).")

        # Inspeciona documento para contagem de páginas
        page_count = 1
        try:
            doc_probe = pymupdf.open(stream=pdf_bytes, filetype="pdf")
            page_count = len(doc_probe)
            doc_probe.close()
        except Exception as e:
            logger.warning(f"[PDFExtractor] Não foi possível inspecionar metadados do PDF {filename}: {e}")

        # Prepara base64 para envio aos Tiers Gemini
        pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")

        tier1_model = custom_tier1_model or self.registry.get_active_model("pdf_extract", DEFAULT_TIER1_MODEL)
        tier2_model = custom_tier2_model or self.registry.get_active_model("pdf_fallback", DEFAULT_TIER2_MODEL)

        # ==================== TIER 1 (PRIORITÁRIO) ====================
        try:
            logger.info(f"⚡ [PDFExtractor] Tentando Tier 1 com modelo '{tier1_model}' para '{filename}' ({size_bytes} bytes, {page_count} págs)...")
            md_tier1 = await self._try_gemini_extract(pdf_base64=pdf_base64, model_name=tier1_model)
            if md_tier1:
                logger.info(f"✅ [PDFExtractor] Sucesso no Tier 1 ({tier1_model}) para '{filename}'.")
                return PDFExtractionResult(
                    markdown=md_tier1,
                    tier_used="tier1_gemini",
                    model_name=tier1_model,
                    filename=filename,
                    size_bytes=size_bytes,
                    page_count=page_count,
                    success=True,
                )
        except Exception as err_t1:
            logger.warning(f"⚠️ [PDFExtractor] Falha no Tier 1 ({tier1_model}) para '{filename}': {err_t1}")
            if not allow_fallback:
                raise

        # ==================== TIER 2 (FALLBACK GEMINI) ====================
        try:
            logger.info(f"🔄 [PDFExtractor] Acionando Tier 2 de Fallback com modelo '{tier2_model}' para '{filename}'...")
            md_tier2 = await self._try_gemini_extract(pdf_base64=pdf_base64, model_name=tier2_model)
            if md_tier2:
                logger.info(f"✅ [PDFExtractor] Sucesso no Tier 2 ({tier2_model}) para '{filename}'.")
                return PDFExtractionResult(
                    markdown=md_tier2,
                    tier_used="tier2_gemini",
                    model_name=tier2_model,
                    filename=filename,
                    size_bytes=size_bytes,
                    page_count=page_count,
                    success=True,
                )
        except Exception as err_t2:
            logger.warning(f"⚠️ [PDFExtractor] Falha no Tier 2 ({tier2_model}) para '{filename}': {err_t2}")
            if not allow_fallback:
                raise

        # ==================== TIER 3 (CONTINGÊNCIA LOCAL PYMUPDF) ====================
        logger.warning(
            f"📦 [PDFExtractor] APIs Gemini indisponíveis ou esgotadas. Acionando Tier 3 (Contingência Local: {DEFAULT_TIER3_NAME}) para '{filename}'..."
        )
        local_md, detected_pages = self._extract_local_contingency(pdf_bytes=pdf_bytes, filename=filename)
        return PDFExtractionResult(
            markdown=local_md,
            tier_used="tier3_pymupdf",
            model_name=DEFAULT_TIER3_NAME,
            filename=filename,
            size_bytes=size_bytes,
            page_count=detected_pages or page_count,
            success=True,
        )


# Instância singleton padrão do extrator
pdf_extractor = PDFExtractor()
