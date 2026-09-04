"""Testes para deduplicação semântica de tarefas (spaCy NLP) e fidelidade temporal de timestamps."""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.memory.models import MessageCreate, TaskRecord
from src.memory.task_sentiment_analyzer import task_sentiment_analyzer
from src.whatsapp.service import whatsapp_service


class TestSpacyTaskDeduplicationAndTimestamps(unittest.TestCase):
    def test_spacy_find_similar_existing_task(self):
        """Valida que tarefas equivalentes semanticamente são detectadas pelo spaCy."""
        t1 = MagicMock(spec=TaskRecord)
        t1.id = "task-1"
        t1.title = "Falar com o Rafael amanhã sobre o alinhamento"
        t1.notes = "Instruções de tags de firmware"

        t2 = MagicMock(spec=TaskRecord)
        t2.id = "task-2"
        t2.title = "Comprar café no mercado"
        t2.notes = ""

        existing_tasks = [t1, t2]

        # Candidata muito semelhante a t1
        candidate_title = "Alinhar com o Rafael amanhã sobre as tags"
        candidate_context = "Preciso conversar com o Rafael logo cedo"

        match = task_sentiment_analyzer.find_similar_existing_task(
            candidate_title=candidate_title,
            candidate_context=candidate_context,
            existing_tasks=existing_tasks,
            similarity_threshold=0.50,
        )

        self.assertIsNotNone(match)
        matched_task, score = match
        self.assertEqual(matched_task.id, "task-1")
        self.assertGreaterEqual(score, 0.50)

        # Candidata completamente diferente
        unrelated_title = "Trocar o óleo do carro"
        unrelated_match = task_sentiment_analyzer.find_similar_existing_task(
            candidate_title=unrelated_title,
            candidate_context="Revisão mecânica",
            existing_tasks=existing_tasks,
            similarity_threshold=0.60,
        )
        self.assertIsNone(unrelated_match)

    def test_extract_message_info_self_memo_with_lid_and_timestamp(self):
        """Valida que mensagens enviadas pelo próprio usuário com @lid são tratadas como self_memo e preservam timestamp."""
        payload = {
            "event": "messages.upsert",
            "data": {
                "key": {
                    "remoteJid": "237490367660176@lid",
                    "fromMe": True,
                    "id": "MSG_TEST_SELF_LID_01",
                },
                "pushName": "Você",
                "messageTimestamp": 1788459651,  # 2026-09-03 15:20:51 UTC
                "message": {
                    "conversation": "? O que conversei com a Débora hoje?",
                },
            },
        }

        info = whatsapp_service.extract_message_info(payload)
        self.assertIsNotNone(info)
        self.assertTrue(info["is_self_memo"])
        self.assertTrue(info["from_me"])
        self.assertEqual(info["key_id"], "MSG_TEST_SELF_LID_01")
        self.assertIsNotNone(info["created_at"])
        self.assertEqual(info["created_at"].year, 2026)
        self.assertEqual(info["created_at"].month, 9)
        self.assertEqual(info["created_at"].day, 3)
        self.assertEqual(info["text"], "? O que conversei com a Débora hoje?")

    def test_message_create_preserves_custom_created_at(self):
        """Valida que MessageCreate aceita e preserva created_at explícito."""
        custom_dt = datetime(2026, 9, 3, 15, 20, 51, tzinfo=timezone.utc)
        msg = MessageCreate(
            speaker="Debora Patel",
            revised_text="Já tô no posto",
            created_at=custom_dt,
        )
        self.assertEqual(msg.created_at, custom_dt)


if __name__ == "__main__":
    unittest.main()
