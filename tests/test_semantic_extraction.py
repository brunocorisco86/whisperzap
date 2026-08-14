"""Testes unitários para o Extrator Semântico e schemas de IA."""

import pytest
from src.ai_gateway.extractor import SemanticExtractor
from src.ai_gateway.providers.mock import MockProvider
from src.ai_gateway.schemas import SemanticExtractionRequest


@pytest.fixture
def mock_extractor():
    """Cria uma instância do extrator configurada com MockProvider."""
    extractor = SemanticExtractor()
    extractor.provider = MockProvider(model_name="mock-extractor")
    return extractor


@pytest.mark.asyncio
async def test_semantic_extraction_task_intent(mock_extractor):
    """Testa extração de mensagem contendo tarefa operacional."""
    req = SemanticExtractionRequest(
        text="Amanhã preciso falar com o João sobre o sensor do silo 3 na C.Vale.",
        speaker="Bruno",
        include_dictionary=True,
    )
    result = await mock_extractor.extract(req)

    assert result.intent == "TASK"
    assert len(result.tasks) >= 1
    assert result.tasks[0].assignee == "João"
    assert result.tasks[0].due_date == "amanhã"
    assert any(e.name == "Silo 3" for e in result.entities)
    assert result.provider == "mock"
    assert result.processing_time_ms > 0


@pytest.mark.asyncio
async def test_semantic_extraction_idea_intent(mock_extractor):
    """Testa extração de ideia ou insight."""
    req = SemanticExtractionRequest(
        text="Tive uma ideia de colocar sensores de nível ultrassônicos em todos os silos.",
        speaker="Bruno",
    )
    result = await mock_extractor.extract(req)

    assert result.intent == "IDEA"
    assert len(result.ideas) >= 1


def test_extract_json_from_markdown_fences(mock_extractor):
    """Verifica se o extrator lida corretamente com blocos de código Markdown retornados por LLMs."""
    raw_markdown = """```json
    {
      "intent": "NOTE",
      "summary": "Resumo teste",
      "tasks": [],
      "entities": [],
      "decisions": [],
      "ideas": [],
      "topics": ["teste"],
      "urgency": "LOW"
    }
    ```"""
    parsed = mock_extractor._extract_json_from_text(raw_markdown)
    assert parsed["intent"] == "NOTE"
    assert parsed["summary"] == "Resumo teste"
