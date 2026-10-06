"""Testes unitários e benchmarks para o Modelo Local de Embeddings Orquestrado pelo JEV."""

import time
import math
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.ai_gateway.providers.local_embedding import LocalEmbeddingProvider
from src.ai_gateway.jev import jev_service, JEVAction
from src.memory.models import Base, MessageCreate, EmbeddingRecord
from src.contacts.models import ContactRecord
from src.memory.repository import MemoryRepository, cosine_similarity


@pytest.fixture
def memory_db():
    """Cria banco SQLite em memória isolado para os testes de embedding."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.mark.asyncio
async def test_local_embedding_dimension_and_l2_norm():
    """Valida se o provedor local gera vetores de 768 dimensões com norma L2 estritamente unitária."""
    provider = LocalEmbeddingProvider(dimension=768)
    text = "Monitoramento ultrassônico do nível de ração nos silos cooperados da C.Vale."
    vec = await provider.generate_embedding(text)

    assert len(vec) == 768, f"Esperado 768 dimensões, obtido {len(vec)}"
    norm = math.sqrt(sum(x * x for x in vec))
    assert norm == pytest.approx(1.0, rel=1e-3), f"Vetor não normalizado em L2: norma = {norm}"


@pytest.mark.asyncio
async def test_local_embedding_empty_text():
    """Valida comportamento para textos vazios (retorna vetor nulo de 768 dimensões)."""
    provider = LocalEmbeddingProvider(dimension=768)
    vec = await provider.generate_embedding("")
    assert len(vec) == 768
    assert all(x == 0.0 for x in vec)


@pytest.mark.asyncio
async def test_local_embedding_semantic_similarity_separation():
    """Valida se textos do mesmo domínio (silos/ração) têm similaridade superior a textos de outros domínios."""
    provider = LocalEmbeddingProvider(dimension=768)

    t1 = "Calibrar os sensores de nível de ração no Silo 3 da C.Vale."
    t2 = "Verificar leituras do sensor do Silo 3 e nível de abastecimento de ração."
    t3 = "Aprovação de despesas administrativas e contrato de aluguel do escritório."

    v1 = await provider.generate_embedding(t1)
    v2 = await provider.generate_embedding(t2)
    v3 = await provider.generate_embedding(t3)

    sim_related = cosine_similarity(v1, v2)
    sim_unrelated = cosine_similarity(v1, v3)

    assert sim_related > 0.40, f"Similaridade semântica entre textos relacionados muito baixa: {sim_related}"
    assert sim_unrelated < 0.25, f"Similaridade entre textos não relacionados muito alta: {sim_unrelated}"
    assert sim_related > sim_unrelated * 2.0, "Separação semântica insuficiente entre domínios"


def test_jev_orchestrator_should_vectorize_flag():
    """Valida se o JEV sinaliza should_vectorize=False apenas para ruídos sociais e BYPASS."""
    verdict_noise = jev_service.judge("Bom dia a todos!", speaker="Carlos")
    assert verdict_noise.action == JEVAction.BYPASS
    assert verdict_noise.should_vectorize is False

    verdict_task = jev_service.judge("Anotar ideia urgente para os silos", speaker="Bruno", is_self_memo=True)
    assert verdict_task.action == JEVAction.DIRECT_RESOLVE
    assert verdict_task.should_vectorize is True

    verdict_query = jev_service.judge("Qual o status dos sensores dos silos?", speaker="Bruno")
    assert verdict_query.action == JEVAction.GRAPH_QUERY
    assert verdict_query.should_vectorize is True


@pytest.mark.asyncio
async def test_repository_save_message_respects_jev_bypass(memory_db):
    """Valida se save_message pula a gravação na tabela embeddings quando JEV determina BYPASS."""
    repo = MemoryRepository()
    repo.embedding_provider = LocalEmbeddingProvider(dimension=768)

    # 1. Mensagem de SAC/robô (salva no banco para histórico de auditoria, mas JEV desativa vetorização)
    msg_noise = MessageCreate(
        speaker="Bruno",
        raw_text="Olá! Sou o assistente virtual da transportadora. Digite 1 para rastreio ou 2 para falar com atendente.",
        revised_text="Olá! Sou o assistente virtual da transportadora. Digite 1 para rastreio ou 2 para falar com atendente.",
        meta_info={"message_type": "audio"},
    )
    saved_noise = await repo.save_message(msg_noise, db=memory_db)
    assert saved_noise is not None

    # Verifica se NÃO criou registro de embedding para a saudação
    embs_noise = memory_db.query(EmbeddingRecord).filter(EmbeddingRecord.message_id == saved_noise.id).all()
    assert len(embs_noise) == 0, "Embedding foi gerado indevidamente para mensagem de ruído!"

    # 2. Mensagem operacional (JEV deve autorizar vetorização)
    msg_action = MessageCreate(
        speaker="Bruno",
        raw_text="verificar sensor ultrassonico do silo 2 amanha",
        revised_text="Verificar sensor ultrassônico do Silo 2 amanhã.",
    )
    saved_action = await repo.save_message(msg_action, db=memory_db)
    assert saved_action is not None

    embs_action = memory_db.query(EmbeddingRecord).filter(EmbeddingRecord.message_id == saved_action.id).all()
    assert len(embs_action) == 1, "Embedding deveria ter sido gerado para mensagem operacional!"
    assert len(embs_action[0].embedding_json) == 768


@pytest.mark.asyncio
async def test_local_embedding_performance_and_latency():
    """Valida se a latência média do provedor local é sub-milissegundo."""
    provider = LocalEmbeddingProvider(dimension=768)
    sample_text = "Integração do TMS com sensores de telemetria nos silos da fazenda 4."

    # Warmup
    await provider.generate_embedding(sample_text)

    n_iterations = 50
    t0 = time.perf_counter()
    for _ in range(n_iterations):
        await provider.generate_embedding(sample_text)
    total_time = time.perf_counter() - t0
    avg_ms = (total_time / n_iterations) * 1000.0

    print(f"\n⚡ Latência média de embedding local: {avg_ms:.3f} ms por texto")
    assert avg_ms < 2.0, f"Latência muito alta para modelo local: {avg_ms:.3f} ms (alvo < 2.0 ms)"
