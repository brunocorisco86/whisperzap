"""Testes da visibilidade de tarefas novas, envelhecimento automático do backlog e filtros anti-ruído (0 tokens)."""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from src.ai_gateway.model_registry import DiscoveredModel, ModelRegistry
from src.memory.database import SessionLocal
from src.memory.models import TaskRecord
from src.memory.repository import memory_repository
from src.memory.task_sentiment_analyzer import task_sentiment_analyzer

PREFIX = "ZZTERPS"


def _naive_utc(delta: timedelta = timedelta(0)) -> datetime:
    return (datetime.now(timezone.utc) - delta).replace(tzinfo=None)


def _task(title: str, age: timedelta, **kwargs) -> TaskRecord:
    return TaskRecord(
        id=str(uuid.uuid4()),
        title=f"{PREFIX} {title}",
        created_at=_naive_utc(age),
        priority=kwargs.pop("priority", "HIGH"),
        status="PENDING",
        **kwargs,
    )


def _cleanup(db):
    db.query(TaskRecord).filter(TaskRecord.title.like(f"{PREFIX}%")).delete(synchronize_session=False)
    db.commit()


def test_recent_task_is_not_buried_by_old_high_priority_backlog():
    db = SessionLocal()
    try:
        _cleanup(db)
        for i in range(30):
            db.add(_task(f"antiga-{i}", timedelta(days=5), priority="URGENT"))
        new_task = _task("nova-media", timedelta(hours=2), priority="MEDIUM")
        db.add(new_task)
        db.commit()

        ordered = [t for t in memory_repository.list_tasks(view_mode="active", status="PENDING", db=db) if t.title.startswith(PREFIX)]
        titles = [t.title for t in ordered]
        assert titles[0] == f"{PREFIX} nova-media"
        assert len(titles) == 31
    finally:
        _cleanup(db)
        db.close()


def test_favorites_still_rank_above_recent_tasks():
    db = SessionLocal()
    try:
        _cleanup(db)
        db.add(_task("favorita-antiga", timedelta(days=3), priority="LOW", is_favorite=True))
        db.add(_task("nova", timedelta(hours=1), priority="HIGH"))
        db.commit()

        ordered = [t.title for t in memory_repository.list_tasks(view_mode="active", status="PENDING", db=db) if t.title.startswith(PREFIX)]
        assert ordered == [f"{PREFIX} favorita-antiga", f"{PREFIX} nova"]
    finally:
        _cleanup(db)
        db.close()


def test_auto_aging_moves_only_eligible_old_tasks_and_restore_sticks():
    db = SessionLocal()
    try:
        _cleanup(db)
        old = timedelta(days=40)
        eligible = _task("elegivel", old)
        with_due = _task("com-prazo", old, due_date="2026-12-01")
        favorite = _task("favorita", old, is_favorite=True)
        epic = _task("epica", old, is_epic=True)
        reassessed = _task("reavaliada", old, reassessment_notes="mantida")
        recent = _task("recente", timedelta(days=2))
        for t in (eligible, with_due, favorite, epic, reassessed, recent):
            db.add(t)
        db.commit()

        memory_repository.auto_age_pending_tasks(db=db, days=21)
        for t in (eligible, with_due, favorite, epic, reassessed, recent):
            db.refresh(t)

        assert eligible.in_vault is True
        assert eligible.vault_reason == memory_repository.AUTO_AGE_VAULT_REASON
        assert not any(t.in_vault for t in (with_due, favorite, epic, reassessed, recent))

        # Restaurar do Baú registra reavaliação e a rotina não devolve a tarefa ao Baú
        memory_repository.restore_task_from_vault(eligible.id, db=db)
        memory_repository.auto_age_pending_tasks(db=db, days=21)
        db.refresh(eligible)
        assert eligible.in_vault is False
        assert "Restaurada" in (eligible.reassessment_notes or "")
    finally:
        _cleanup(db)
        db.close()


def test_filter_accepts_real_tasks_previously_discarded():
    titles = [
        "Integrar o produtor Clayton Salvador no eProdutor",
        "Enviar lista atualizada dos aviários",
        "Utilizar cor de destaque na próxima entrega ou documento",
        "Ajustar o aplicativo para exibir a guia de recolha dos produtores do consultor",
        "Evitar erros na produção ou fornecimento de ração",
    ]
    for title in titles:
        assert task_sentiment_analyzer.is_actionable_task(title=title, source_text=""), title


def test_filter_still_rejects_noise():
    assert not task_sentiment_analyzer.is_actionable_task(
        title="Aguardar retorno do fornecedor", source_text="Estou esperando eles responderem ainda não me deram retorno"
    )
    assert not task_sentiment_analyzer.is_actionable_task(title="Celular do Paulo", source_text="Celular do Paulo")


def test_text_fallback_excludes_tts_and_image_models(tmp_path):
    assert ModelRegistry.is_text_generation_model("gemini-3.7-flash")
    assert ModelRegistry.is_text_generation_model("gemini-3.1-flash-lite-preview")
    assert not ModelRegistry.is_text_generation_model("gemini-3.8-flash-lite-tts")
    assert not ModelRegistry.is_text_generation_model("gemini-3.1-flash-lite-image")

    reg = ModelRegistry(persistence_path=str(tmp_path / "reg.json"))
    reg.data.discovered_models = [
        DiscoveredModel(name="gemini-3.8-flash-lite-tts", display_name="tts", description="", tier="LITE", generation=3.8,
                        supported_methods=["generateContent"], cost_efficiency_score=9.9),
        DiscoveredModel(name="gemini-3.1-flash-lite-image", display_name="img", description="", tier="LITE", generation=3.1,
                        supported_methods=["generateContent"], cost_efficiency_score=9.8),
        DiscoveredModel(name="gemini-3.7-flash", display_name="txt", description="", tier="FLASH", generation=3.7,
                        supported_methods=["generateContent"], cost_efficiency_score=8.9),
    ]
    chain = reg.get_viable_fallback_chain(current_model="gemini-x")
    assert "gemini-3.7-flash" in chain
    assert not any("tts" in m or "image" in m for m in chain)


def test_httpx_logger_does_not_log_info_urls():
    import src.main  # noqa: F401  (aplica a configuração de logging)

    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
