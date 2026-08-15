"""Testes de Concorrência para o Hermes Voice Memory.
Valida o comportamento sob rajadas de mensagens paralelas e em série.
"""

import asyncio
from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient, ASGITransport
from src.main import app
from src.memory.database import SessionLocal
from src.memory.models import MessageRecord
from src.memory.graph import knowledge_graph
from src.ai_gateway.schemas import SemanticExtractionResponse, ExtractedTask, ExtractedEntity, ExtractedTriple


@pytest.mark.asyncio
async def test_parallel_messages_concurrency():
    """Dispara 10 mensagens simultaneamente em paralelo e valida concorrência atômica no banco e grafo."""
    transport = ASGITransport(app=app)
    
    mock_response = SemanticExtractionResponse(
        intent="TASK",
        summary="Entrega de ração no silo",
        sentiment="NEUTRAL",
        sentiment_score=0.0,
        tasks=[ExtractedTask(title="Verificar silo", assignee="Carlos", priority="HIGH")],
        entities=[ExtractedEntity(name="Silo 04", category="EQUIPMENT")],
        triples=[ExtractedTriple(source="Carlos", relation="MANAGES", target="Silo 04")],
        decisions=[],
        ideas=[],
        topics=["ração", "silo"],
        urgency="HIGH",
        provider="mock",
        model="mock-fast",
        processing_time_ms=5.0,
    )

    with patch("src.memory.repository.semantic_extractor.extract", new_callable=AsyncMock) as mock_extract, \
         patch("src.memory.repository.get_ai_provider") as mock_get_provider:
        
        mock_extract.return_value = mock_response
        mock_provider = AsyncMock()
        mock_provider.generate_embedding.return_value = [0.1] * 768
        mock_get_provider.return_value = mock_provider

        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async def send_msg(idx: int):
                payload = {
                    "speaker": f"Participante_{idx % 3}",
                    "raw_text": f"Mensagem concorrente de teste {idx} sobre entrega de ração no silo",
                    "revised_text": f"Mensagem concorrente de teste {idx} sobre entrega de ração no silo com TMS e Mtech",
                    "meta_info": {"remoteJid": f"55449999900{idx}@s.whatsapp.net", "pushName": f"Pessoa {idx}"}
                }
                return await ac.post("/api/v1/memory/messages", json=payload)

            # Dispara 10 requisições simultâneas em paralelo
            responses = await asyncio.gather(*[send_msg(i) for i in range(10)])

            # Todas as 10 requisições devem retornar HTTP 201 Created
            for r in responses:
                assert r.status_code == 201
                data = r.json()
                assert "message_id" in data
                assert data["intent"] == "TASK"

    # Verifica integridade na base de dados
    db = SessionLocal()
    try:
        total_parallel = db.query(MessageRecord).filter(
            MessageRecord.revised_text.like("%Mensagem concorrente de teste%")
        ).count()
        assert total_parallel == 10
    finally:
        db.close()

    # Verifica que o grafo continua íntegro e sem corrupção de arquivo
    stats = knowledge_graph.stats()
    assert stats["nodes"] > 0
