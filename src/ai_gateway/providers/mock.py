"""Provedor Mock para testes e desenvolvimento offline."""

from src.ai_gateway.providers.base import BaseLLMProvider


class MockProvider(BaseLLMProvider):
    """Provedor simulado para testes sem consumo de APIs externas."""

    def __init__(self, model_name: str = "mock-model"):
        super().__init__(model_name=model_name)

    @property
    def provider_name(self) -> str:
        return "mock"

    async def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        """Retorna uma resposta simulada formatada."""
        # Se for um prompt de revisão contendo "Transcrição Bruta:", simula texto limpo
        if "Transcrição Bruta:" in prompt:
            lines = prompt.splitlines()
            raw_lines = []
            capture = False
            for line in lines:
                if line.startswith("Transcrição Bruta:"):
                    capture = True
                    continue
                if line.startswith("Contexto:") or line.startswith("Texto revisado:"):
                    break
                if capture and line.strip():
                    raw_lines.append(line.strip())

            raw_text = " ".join(raw_lines) if raw_lines else "Texto de teste simulado."
            # Capitaliza primeira letra e garante ponto final
            cleaned = raw_text.strip()
            if cleaned and not cleaned.endswith((".", "!", "?")):
                cleaned = cleaned + "."
            return cleaned.capitalize()

        # Se for um prompt de extração semântica
        if "extração semântica" in (system_instruction or "").lower() or "JSON de extração" in prompt:
            import json
            # Analisa o texto para simular tarefas e entidades se encontradas
            lower_prompt = prompt.lower()
            intent = "TASK" if any(w in lower_prompt for w in ["preciso", "falar", "comprar", "enviar", "fazer", "amanhã", "reunião"]) else "NOTE"
            if "ideia" in lower_prompt or "sugiro" in lower_prompt:
                intent = "IDEA"
            elif "problema" in lower_prompt or "estragou" in lower_prompt or "falha" in lower_prompt:
                intent = "PROBLEM"

            tasks = []
            if intent == "TASK" or "amanhã" in lower_prompt or "preciso" in lower_prompt:
                tasks.append({
                    "title": "Verificar pendências operacionais mencionadas",
                    "assignee": "João" if "joão" in lower_prompt or "joao" in lower_prompt else None,
                    "due_date": "amanhã" if "amanhã" in lower_prompt or "amanha" in lower_prompt else None,
                    "priority": "HIGH" if "urgente" in lower_prompt or "sensor" in lower_prompt else "MEDIUM",
                })

            entities = []
            if "joão" in lower_prompt or "joao" in lower_prompt:
                entities.append({"name": "João", "category": "PERSON", "details": "Contato de trabalho"})
            if "silo" in lower_prompt:
                entities.append({"name": "Silo 3", "category": "EQUIPMENT", "details": "Armazenamento de ração"})
            if "cvale" in lower_prompt or "c.vale" in lower_prompt:
                entities.append({"name": "C.Vale", "category": "LOCATION", "details": "Cooperativa"})
            if "fal" in lower_prompt or "fau" in lower_prompt:
                entities.append({"name": "FAL", "category": "SYSTEM", "details": "Ficha de Acompanhamento de Lote"})

            mock_json = {
                "intent": intent,
                "summary": "Mensagem com diretrizes de acompanhamento operacional e tarefas.",
                "tasks": tasks,
                "entities": entities,
                "decisions": [],
                "ideas": ["Otimizar sensores e fluxo de comunicação"] if intent == "IDEA" else [],
                "topics": ["operações", "silos", "automação"],
                "urgency": "HIGH" if "urgente" in lower_prompt else "MEDIUM",
            }
            return json.dumps(mock_json, ensure_ascii=False)

        return "Resposta simulada pelo MockProvider."

