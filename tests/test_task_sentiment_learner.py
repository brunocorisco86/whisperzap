import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from src.main import app
from src.memory.database import SessionLocal
from src.memory.models import TaskRecord, MessageRecord, MessageCreate
from src.memory.task_sentiment_analyzer import task_sentiment_analyzer
from src.ai_gateway.task_learner import task_learner_engine
from src.memory.repository import memory_repository

client = TestClient(app)


def test_spacy_task_sentiment_analyzer_noise_classification():
    """Valida a classificação linguística e de ruído pelo spaCy."""
    # 1. Observação de campo isolada
    res_obs = task_sentiment_analyzer.analyze_task_text("Investigar causa de aves", "Frango sentado")
    assert res_obs["noise_category"] == "FIELD_OBSERVATION_FRAGMENT"
    assert res_obs["is_likely_noise"] is True
    assert task_sentiment_analyzer.is_actionable_task("Investigar aves", "Frango sentado") is False

    # 2. Atualização de status passiva
    res_stat = task_sentiment_analyzer.analyze_task_text("Verificar status", "ainda nao me deram resposta, to no abatedouro hoje")
    assert res_stat["noise_category"] == "STATUS_UPDATE"
    assert res_stat["is_likely_noise"] is True
    assert task_sentiment_analyzer.is_actionable_task("Verificar status", "ainda nao me deram resposta, to no abatedouro hoje") is False

    # 3. Conversa sobre roadmap
    res_road = task_sentiment_analyzer.analyze_task_text("Implementar análise", "ta no roadmap pra mostrar quem mais ta gerando task")
    assert res_road["noise_category"] == "ROADMAP_CHAT"
    assert res_road["is_likely_noise"] is True

    # 4. Conselho condicional / hipotético
    res_hypo = task_sentiment_analyzer.analyze_task_text("Enviar link", "a menos que eles exijam o arquivo, manda o link")
    assert res_hypo["noise_category"] == "HYPOTHETICAL_ADVICE"
    assert res_hypo["is_likely_noise"] is True

    # 5. Tarefa acionável legítima com verbo de ação e prazo
    res_real = task_sentiment_analyzer.analyze_task_text(
        "Calibrar sensor de temperatura",
        "Lembrar de calibrar o sensor da granja 4 amanhã cedo com o João",
    )
    assert res_real["noise_category"] is None
    assert res_real["has_action_verb"] is True
    assert res_real["actionability_score"] >= 0.8
    assert res_real["is_likely_noise"] is False
    assert task_sentiment_analyzer.is_actionable_task("Calibrar sensor", "Lembrar de calibrar o sensor da granja 4 amanhã cedo") is True


def test_task_learner_prompt_injection():
    """Valida se o hint de regras negativas é gerado adequadamente."""
    hint = task_learner_engine.get_pruning_rules_prompt_hint()
    assert "DIRETRIZES ESTRITAS DE FILTRAGEM ANTI-FALSO-POSITIVO" in hint
    assert "NUNCA" in hint


def test_learner_rules_api_endpoints():
    """Testa os endpoints GET /learner-rules e POST /optimize-learner."""
    # 1. GET rules
    res_get = client.get("/api/v1/memory/tasks/learner-rules")
    assert res_get.status_code == 200
    data_get = res_get.json()
    assert "negative_guidelines" in data_get
    assert len(data_get["negative_guidelines"]) > 0

    # 2. POST trigger optimizer
    db = SessionLocal()
    try:
        # Cria uma tarefa cancelada para garantir análise
        task_test = TaskRecord(
            id="task_test_cancelled_1",
            title="Investigar aves sentadas no aviário",
            status="CANCELLED",
            priority="LOW",
            created_at=datetime.now(timezone.utc),
        )
        db.merge(task_test)
        db.commit()

        res_opt = client.post("/api/v1/memory/tasks/optimize-learner")
        assert res_opt.status_code == 200
        data_opt = res_opt.json()
        assert "version" in data_opt
        assert data_opt["total_cancelled_analyzed"] >= 1
    finally:
        db.close()


@pytest.mark.asyncio
async def test_repository_noise_pre_save_filtering():
    """Garante que mensagens com ruídos observacionais não geram tarefas no banco de dados."""
    db = SessionLocal()
    try:
        msg = MessageCreate(
            speaker="Bruno Conter",
            revised_text="Aviso rápido de campo do lote: Frango sentado.",
            meta_info={"phone": "554497604925", "fromMe": True},
        )
        saved_msg = await memory_repository.save_message(msg, db=db)
        assert saved_msg is not None

        # Confere se tarefas foram salvas (deve ser 0 graças ao filtro spaCy anti-ruído)
        tasks = db.query(TaskRecord).filter(TaskRecord.message_id == saved_msg.id).all()
        assert len(tasks) == 0
    finally:
        db.close()
