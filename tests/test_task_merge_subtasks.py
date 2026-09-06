"""Testes unitários para o Guardião Temático de Não-Colisão, Subtarefas, Checklists e status MERGED."""

import pytest
from unittest.mock import MagicMock
from src.memory.task_sentiment_analyzer import task_sentiment_analyzer
from src.memory.subtask_service import subtask_service
from src.memory.models import TaskRecord


def test_anti_collision_topic_gate():
    """Garante que tarefas com temas/objetos diferentes NUNCA sejam unificadas, mesmo citando mesmo fornecedor."""
    # Ambas poderiam ser da 'e-Aware', mas tratam de temas totalmente distintos
    t_veiculos = "Investigar falha de carregamento na interface de rastreamento de veículos com a e-Aware"
    t_racao = "Conversar com o pessoal da e-Aware para alinhar envio de push notification de pedido de ração no app eProdutor"
    t_tags = "Realizar cadastros das tags com a e-Aware"

    sim_veiculos_racao = task_sentiment_analyzer.compute_task_similarity(
        t_veiculos, "", t_racao, ""
    )
    assert sim_veiculos_racao == 0.0, f"Deveria ser 0.0 pelo Anti-Collision Gate, obtido: {sim_veiculos_racao}"

    sim_veiculos_tags = task_sentiment_analyzer.compute_task_similarity(
        t_veiculos, "", t_tags, ""
    )
    assert sim_veiculos_tags == 0.0, f"Deveria ser 0.0 pelo Anti-Collision Gate, obtido: {sim_veiculos_tags}"

    # Tarefas do mesmo tópico devem passar normalmente
    t_tags_b = "Realizar os cadastros das tags após receber instruções do Rafa"
    sim_tags_match = task_sentiment_analyzer.compute_task_similarity(
        t_tags, "", t_tags_b, ""
    )
    assert sim_tags_match >= 0.50, f"Deveria ser >= 0.50 para mesmo tópico, obtido: {sim_tags_match}"


def test_subtask_service_add_and_merge():
    """Testa a geração e formatação de subtarefas em markdown com cabeçalho percentual."""
    primary_title = "Alinhar diretrizes com a Sandra da Agrisolus"
    dup_title = "Enviar documento com diretrizes para Sandra (Agrisolus)"

    initial_notes = "Anotação prévia do gestor."
    merged_notes = subtask_service.add_or_merge_subtask(
        existing_notes=initial_notes,
        primary_title=primary_title,
        primary_audio_ref="msg_111",
        duplicate_title=dup_title,
        duplicate_audio_ref="msg_222",
    )

    parsed = subtask_service.parse_subtasks(merged_notes)
    assert parsed["has_subtasks"] is True
    assert parsed["total"] == 2
    assert parsed["completed"] == 0
    assert parsed["percentage"] == 0
    assert "0/2 concluídas - 0%" in merged_notes
    assert "msg_111" in merged_notes
    assert "msg_222" in merged_notes


def test_subtask_service_toggle_and_recalculate():
    """Testa a alternância de subtarefa (- [ ] para - [x]) e recálculo do percentual de conclusão."""
    notes = (
        "### 📋 Subtarefas (0/2 concluídas - 0%):\n"
        "- [ ] Item 1 (🎙️ Ref: msg_111)\n"
        "- [ ] Item 2 (🎙️ Ref: msg_222)\n"
    )

    # Marca o item 0 como concluído
    updated_1 = subtask_service.toggle_subtask(notes, subtask_index=0, target_state=True)
    parsed_1 = subtask_service.parse_subtasks(updated_1)
    assert parsed_1["completed"] == 1
    assert parsed_1["total"] == 2
    assert parsed_1["percentage"] == 50
    assert "1/2 concluídas - 50%" in updated_1

    # Marca o item 1 também como concluído
    updated_2 = subtask_service.toggle_subtask(updated_1, subtask_index=1, target_state=True)
    parsed_2 = subtask_service.parse_subtasks(updated_2)
    assert parsed_2["completed"] == 2
    assert parsed_2["total"] == 2
    assert parsed_2["percentage"] == 100
    assert "2/2 concluídas - 100%" in updated_2


def test_task_rationalization_merged_status():
    """Testa se a tarefa duplicada é marcada como MERGED (e não CANCELLED) no banco."""
    mock_db = MagicMock()

    task1 = TaskRecord(
        id="t-primary",
        title="Realizar cadastros das tags",
        priority="HIGH",
        status="PENDING",
        message_id="msg_001",
        notes="",
    )
    task2 = TaskRecord(
        id="t-duplicate",
        title="Realizar os cadastros das tags após receber instruções do Rafa",
        priority="LOW",
        status="PENDING",
        message_id="msg_002",
        notes="Orientações passadas via áudio",
    )

    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        task1, task2
    ]

    res = task_sentiment_analyzer.rationalize_pending_tasks(mock_db, similarity_threshold=0.50)

    assert res["status"] == "SUCCESS"
    assert res["merged_count"] == 1

    # task2 deve ser MERGED
    assert task2.status == "MERGED"
    assert "Consolidado por Terpsícore & Polímnia" in task2.reassessment_notes
    assert "como subtarefa na tarefa #t-primary" in task2.reassessment_notes

    # task1 deve ter subtarefas estruturadas
    parsed = subtask_service.parse_subtasks(task1.notes)
    assert parsed["has_subtasks"] is True
    assert parsed["total"] == 2
    mock_db.commit.assert_called_once()


def test_subtask_service_remove_subtask():
    """Testa remoção de subtarefa ao desfazer a unificação."""
    initial_notes = (
        "### 📋 Subtarefas (0/2 concluídas - 0%):\n"
        "- [ ] Tarefa Principal (🎙️ Ref: msg-01)\n"
        "- [ ] Subtarefa Adicional (🎙️ Ref: msg-02)\n\n"
        "Notas normais do usuário"
    )

    # Remove por audio_ref
    updated = subtask_service.remove_subtask(initial_notes, audio_ref="msg-02")
    parsed = subtask_service.parse_subtasks(updated)
    assert parsed["total"] == 1
    assert parsed["items"][0]["title"] == "Tarefa Principal"
    assert "Notas normais do usuário" in updated
    assert "msg-02" not in updated

    # Remove a única subtarefa restante
    updated_final = subtask_service.remove_subtask(updated, audio_ref="msg-01")
    parsed_final = subtask_service.parse_subtasks(updated_final)
    assert parsed_final["has_subtasks"] is False
    assert updated_final.strip() == "Notas normais do usuário"

