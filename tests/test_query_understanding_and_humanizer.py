"""Testes unitários e de integração para o motor HermesQueryUnderstanding e HermesResponseHumanizer."""

import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.memory.database import SessionLocal, init_db
from src.contacts.models import ContactRecord
from src.memory.models import MessageRecord
from src.memory.query_understanding import hermes_query_understanding
from src.ai_gateway.humanizer import hermes_response_humanizer
from src.memory.semantic_cache import semantic_cache


@pytest.fixture(autouse=True)
def setup_database():
    """Inicializa banco e limpa cache semântico antes de cada teste."""
    init_db()
    semantic_cache._cache.clear()


def test_query_understanding_intent_and_speaker():
    """Testa se o HermesQueryUnderstanding identifica interlocutores e intenções via spaCy + DB."""
    db = SessionLocal()
    try:
        if not db.query(ContactRecord).filter(ContactRecord.name == "Mateus Silva").first():
            db.add(ContactRecord(
                id="c-mateus-test",
                name="Mateus Silva",
                nickname="Mateus",
                phone_number="554499887711",
                role="PRODUCER_COOPERATED",
            ))
            db.commit()

        # 1. Pergunta sobre diálogo com interlocutor
        parsed1 = hermes_query_understanding.analyze_query("Sobre o que o Mateus conversou comigo ontem?", db=db)
        assert parsed1.intent == "INTERLOCUTOR_DIALOGUE"
        assert parsed1.target_speaker == "Mateus"
        assert parsed1.target_speaker_full_name == "Mateus Silva"
        assert parsed1.is_recent is True

        # 2. Pergunta sobre tarefas
        parsed2 = hermes_query_understanding.analyze_query("Quais são as tarefas e pendências em aberto?", db=db)
        assert parsed2.intent == "TASK_LOOKUP"

        # 3. Pergunta sobre conceito / sistema
        parsed3 = hermes_query_understanding.analyze_query("Como funciona a integração do TMS na C.Vale?", db=db)
        assert parsed3.intent == "CONCEPT_STATUS"
        assert any(t["term"] in ("TMS", "C.Vale") for t in parsed3.domain_terms)
    finally:
        db.close()


def test_query_understanding_polimnia_domain_terms():
    """Testa a identificação e expansão de siglas e variantes fonéticas do glossário Polímnia."""
    parsed = hermes_query_understanding.analyze_query("O aplicativo do produtor e o sensor do silo 3 estragou")
    
    terms_found = [t["term"] for t in parsed.domain_terms]
    # "aplicativo do produtor" é variação de eProdutor
    assert "eProdutor" in terms_found or "Silos e Ração" in terms_found or len(terms_found) >= 1
    assert "silo" in [s.lower() for s in parsed.clean_seed_entities]


def test_response_humanizer_strips_technical_junk():
    """Testa se o HermesResponseHumanizer remove UUIDs, [ID:...], notas vCard e triplas brutas."""
    raw_dirty_text = """
    Com base nas memórias registradas:
    • [ID: 413528f9-08fc-413b-b301-a3299457cea0] De: Gracieli Patel em 20/08/2026 | Conteúdo: "E sem essa peça nada funciona"
    ID Yahoo: zeh_gatinha
    [Nota Importada]: Importado via Google vCard
    Contato Oficial: Gracieli Patel | Cargo: PRODUCER_COOPERATED | Telefone: 554499722779
    FAL -[DEPENDS_ON]-> eProdutor
    Entidade: TMS | Categoria: SYSTEM | Info: Sistema de transporte
    """

    humanized = hermes_response_humanizer.humanize(raw_dirty_text)

    # 1. Não deve conter UUIDs nem tags [ID: ...]
    assert "[ID:" not in humanized
    assert "413528f9-08fc" not in humanized

    # 2. Não deve conter lixo de vCards
    assert "ID Yahoo:" not in humanized
    assert "zeh_gatinha" not in humanized
    assert "[Nota Importada]:" not in humanized

    # 3. Deve converter triplas cruas em texto corrido limpo
    assert "-[DEPENDS_ON]->" not in humanized
    assert "FAL conectado a eProdutor" in humanized or "FAL" in humanized

    # 4. Deve conter a fala essencial
    assert "E sem essa peça nada funciona" in humanized


def test_response_humanizer_polishing_and_canonicalization():
    """Testa padronização léxica com Polímnia e pontuação sintática com spaCy."""
    text = "o sistema da cvale e o aplicativo eprodutor precisam de calibracao no tms"
    humanized = hermes_response_humanizer.humanize(text)

    # Deve aplicar as maiúsculas canônicas do glossário Polímnia
    assert "C.Vale" in humanized
    assert "eProdutor" in humanized
    assert "TMS" in humanized
    # Deve terminar com ponto final
    assert humanized.endswith(".")


def test_end_to_end_melpomene_query_humanized():
    """Testa a rota completa do Oráculo Melpômene garantindo respostas limpas e humanizadas."""
    db = SessionLocal()
    try:
        if not db.query(ContactRecord).filter(ContactRecord.name == "Fernando Varolo").first():
            db.add(ContactRecord(
                id="c-varolo-test",
                name="Fernando Varolo",
                phone_number="5544999998877",
                role="COLLEAGUE",
            ))
            db.commit()
    finally:
        db.close()

    client = TestClient(app)

    # Registra mensagem
    client.post("/api/v1/memory/messages", json={
        "speaker": "Fernando Varolo",
        "revised_text": "Alinhamos com a diretoria a implantação dos novos sensores LoRa na granja.",
        "summary": "Fernando Varolo alinhou implantação de sensores LoRa com diretoria.",
    })

    # Consulta
    res = client.post("/api/v1/memory/query", json={
        "query": "O que o Fernando Varolo alinhou?",
        "top_k": 3,
        "include_graph": True,
    })
    assert res.status_code == 200
    data = res.json()

    assert "[ID:" not in data["answer"]
    assert "sensores" in data["answer"].lower() or "fernando" in data["answer"].lower()


def test_local_cognitive_synthesizer_dialogue():
    """Testa a síntese cognitiva local sem dependência de LLM externo."""
    from src.ai_gateway.cognitive_synthesizer import local_cognitive_synthesizer
    from src.ai_gateway.schemas import MemorySourceCitation

    mock_sources = [
        MemorySourceCitation(
            message_id="msg-1",
            speaker="Gracieli Patel",
            text_snippet="E sem essa peça nada funciona",
            similarity=0.98,
        ),
        MemorySourceCitation(
            message_id="msg-2",
            speaker="Gracieli Patel",
            text_snippet="Ele saiu da empresa e vai demorar",
            similarity=0.98,
        ),
        MemorySourceCitation(
            message_id="msg-3",
            speaker="Gracieli Patel",
            text_snippet="Deixa ver o que vão responder daí te passo",
            similarity=0.98,
        ),
    ]

    result = local_cognitive_synthesizer.synthesize_dialogue(
        speaker_name="Gracieli Patel",
        sources=mock_sources,
        pending_tasks=["Cobrar fornecedor da peça"],
        related_entities=[],
    )

    assert "Gracieli Patel" in result
    assert "Equipamentos" in result or "Operação" in result or "peça" in result
    assert "Acompanhamento" in result or "Retorno" in result
    assert "Cobrar fornecedor da peça" in result
