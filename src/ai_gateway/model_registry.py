"""Registro e Gerenciador Dinâmico de Modelos de IA (Model Registry).

Permite descobrir, ranquear por custo-benefício de tokens e atualizar
dinamicamente os modelos de IA utilizados pelo WhisperZap sem necessidade de hardcoding.
"""

import json
import logging
import os
import re
import time
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from pydantic import BaseModel, Field

from src.config import settings

logger = logging.getLogger(__name__)


class DiscoveredModel(BaseModel):
    name: str
    display_name: str = ""
    description: str = ""
    tier: str = "FLASH"  # LITE, FLASH, PRO, EMBEDDING, OTHER
    generation: float = 3.0
    input_token_limit: int = 1048576
    output_token_limit: int = 8192
    supported_methods: List[str] = Field(default_factory=list)
    cost_efficiency_score: float = 8.0
    is_recommended: bool = False
    recommended_for: List[str] = Field(default_factory=list)


class ModelRegistryData(BaseModel):
    active_models: Dict[str, str] = Field(default_factory=lambda: {
        "default": "gemini-3.5-flash-lite",
        "revise": "gemini-3.5-flash-lite",
        "extract": "gemini-3.5-flash-lite",
        "summarize": "gemini-3.5-flash-lite",
        "weekly": "gemini-3.5-flash-lite",
        "hermes": "gemini-3.5-flash-lite",
        "embedding": "gemini-embedding-001",
    })
    auto_adopt_best_lite: bool = True
    last_discovery_at: Optional[str] = None
    discovered_models: List[DiscoveredModel] = Field(default_factory=list)
    history: List[Dict[str, Any]] = Field(default_factory=list)


class CircuitState:
    CLOSED = "CLOSED"        # Operação normal
    OPEN = "OPEN"            # Modelo sobrecarregado/indisponível, requisições desviadas
    HALF_OPEN = "HALF_OPEN"  # Testando recuperação após expiração do cooldown


class ModelCircuitBreaker:
    """Circuit Breaker reativo thread-safe para modelos de IA."""

    def __init__(self, failure_threshold: int = 2, cooldown_seconds: float = 90.0):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.failure_counts: Dict[str, int] = {}
        self.circuit_state: Dict[str, str] = {}
        self.last_failure_time: Dict[str, float] = {}
        self._lock = threading.RLock()

    def report_failure(self, model: str, status_code: int = 503) -> bool:
        """Registra falha de execução. Se atingir o threshold, abre o circuito."""
        with self._lock:
            now = time.time()
            self.failure_counts[model] = self.failure_counts.get(model, 0) + 1
            self.last_failure_time[model] = now

            if self.failure_counts[model] >= self.failure_threshold:
                was_open = self.circuit_state.get(model) == CircuitState.OPEN
                self.circuit_state[model] = CircuitState.OPEN
                if not was_open:
                    logger.warning(
                        f"🚨 [CircuitBreaker] Modelo '{model}' entrou em OPEN após {self.failure_counts[model]} falhas (HTTP {status_code})."
                    )
                return True
            return False

    def report_success(self, model: str) -> None:
        """Registra sucesso na chamada ao modelo, restabelecendo o circuito."""
        with self._lock:
            self.failure_counts[model] = 0
            if self.circuit_state.get(model) != CircuitState.CLOSED:
                logger.info(f"✅ [CircuitBreaker] Modelo '{model}' recuperado (circuito CLOSED).")
            self.circuit_state[model] = CircuitState.CLOSED

    def is_available(self, model: str) -> bool:
        """Verifica se o modelo está liberado para tráfego."""
        with self._lock:
            state = self.circuit_state.get(model, CircuitState.CLOSED)
            if state == CircuitState.CLOSED:
                return True
            if state == CircuitState.OPEN:
                if time.time() - self.last_failure_time.get(model, 0) > self.cooldown_seconds:
                    self.circuit_state[model] = CircuitState.HALF_OPEN
                    logger.info(f"🔄 [CircuitBreaker] Cooldown expirado para '{model}'. Transicionado para HALF_OPEN.")
                    return True
                return False
            return True

    def get_status(self) -> Dict[str, Any]:
        """Retorna telemetria consolidada de todos os modelos monitorados."""
        with self._lock:
            now = time.time()
            res = {}
            for m, state in self.circuit_state.items():
                last_fail = self.last_failure_time.get(m, 0)
                elapsed = now - last_fail if last_fail else 0
                res[m] = {
                    "state": state,
                    "failure_count": self.failure_counts.get(m, 0),
                    "seconds_since_last_failure": round(elapsed, 1),
                    "cooldown_remaining": max(0.0, round(self.cooldown_seconds - elapsed, 1)) if state == CircuitState.OPEN else 0.0,
                }
            return res


class ModelRegistry:
    """Gerenciador dinâmico thread-safe de modelos de IA."""

    def __init__(self, persistence_path: Optional[str] = None):
        self.persistence_path = persistence_path or os.path.join(settings.DATA_DIR or "data", "ai_model_registry.json")
        self._lock = threading.RLock()
        self.circuit_breaker = ModelCircuitBreaker()
        self.data = self._load()

    def _load(self) -> ModelRegistryData:
        """Carrega os dados persistidos ou inicializa com padrões resilientes."""
        if os.path.exists(self.persistence_path):
            try:
                with open(self.persistence_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    return ModelRegistryData(**raw)
            except Exception as e:
                logger.warning(f"Erro ao carregar {self.persistence_path}: {e}. Inicializando com padrões.")

        default_data = ModelRegistryData()
        # Sincroniza com configurações do settings se existirem
        if settings.MODEL_REVISE:
            default_data.active_models["revise"] = settings.MODEL_REVISE
        if settings.MODEL_EXTRACT:
            default_data.active_models["extract"] = settings.MODEL_EXTRACT
        if settings.MODEL_SUMMARIZE:
            default_data.active_models["summarize"] = settings.MODEL_SUMMARIZE
        if settings.MODEL_WEEKLY:
            default_data.active_models["weekly"] = settings.MODEL_WEEKLY
        if settings.EMBEDDING_MODEL:
            default_data.active_models["embedding"] = settings.EMBEDDING_MODEL
        if settings.AI_DEFAULT_MODEL:
            default_data.active_models["default"] = settings.AI_DEFAULT_MODEL
            default_data.active_models["hermes"] = settings.AI_DEFAULT_MODEL
        return default_data

    def _save(self) -> None:
        """Salva atomicamente o registro de modelos no disco."""
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.persistence_path) or ".", exist_ok=True)
                tmp = f"{self.persistence_path}.tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self.data.model_dump(), f, ensure_ascii=False, indent=2)
                os.replace(tmp, self.persistence_path)
            except Exception as e:
                logger.error(f"Erro ao salvar registro de modelos em {self.persistence_path}: {e}")

    def get_active_model(self, task: str = "default", fallback: Optional[str] = None) -> str:
        """Retorna dinamicamente o modelo configurado para uma determinada tarefa."""
        with self._lock:
            active = self.data.active_models.get(task) or self.data.active_models.get("default")
            if active:
                return active
            return fallback or settings.AI_DEFAULT_MODEL or "gemini-3.1-flash-lite"

    def get_all_active_models(self) -> Dict[str, str]:
        """Retorna todos os modelos ativos para todas as tarefas."""
        with self._lock:
            return dict(self.data.active_models)

    def list_models(self) -> List[Dict[str, Any]]:
        """Retorna a lista de modelos descobertos."""
        with self._lock:
            return [m.model_dump() for m in self.data.discovered_models]

    def set_active_model(self, task: str, model_name: str) -> None:
        """Define o modelo ativo para uma tarefa específica."""
        with self._lock:
            self.data.active_models[task] = model_name.strip()
            self._save()
            logger.info(f"✨ [ModelRegistry] Modelo para '{task}' atualizado dinamicamente para: '{model_name}'")

    def update_active_models(self, updates: Dict[str, str], auto_adopt: Optional[bool] = None) -> Dict[str, str]:
        """Atualiza múltiplos modelos ativos em lote."""
        with self._lock:
            for task, model in updates.items():
                if model and isinstance(model, str):
                    self.data.active_models[task] = model.strip()
            if auto_adopt is not None:
                self.data.auto_adopt_best_lite = bool(auto_adopt)
            self._save()
            logger.info(f"✨ [ModelRegistry] Modelos ativos atualizados: {self.data.active_models}")
            return dict(self.data.active_models)

    def get_viable_fallback_chain(self, current_model: str, task: str = "revise") -> List[str]:
        """Retorna dinamicamente candidatos saudáveis do pool descoberto, excluindo modelos com circuito aberto."""
        with self._lock:
            # Pega candidatos descobertos ordenados por custo-benefício
            discovered = [
                m.name for m in self.data.discovered_models
                if "generateContent" in m.supported_methods and m.tier in ("LITE", "FLASH") and m.cost_efficiency_score > 0
            ]
            viable = [
                m for m in discovered
                if m != current_model and self.circuit_breaker.is_available(m)
            ]
            if not viable:
                # Se pool descoberto estiver vazio ou exaurido, usa candidatos de segurança padrão
                safety = ["gemini-3.5-flash-lite", "gemini-3.7-flash", "gemini-flash-latest"]
                viable = [m for m in safety if m != current_model and self.circuit_breaker.is_available(m)]
            return viable

    async def handle_runtime_failure(self, failed_model: str, task: str = "revise", status_code: int = 503) -> str:
        """Acionado reativamente pelo provedor quando um modelo falha em produção (503/429/404/timeout)."""
        self.circuit_breaker.report_failure(failed_model, status_code)

        with self._lock:
            fallbacks = self.get_viable_fallback_chain(failed_model, task=task)
            if not fallbacks:
                logger.warning("⚠️ Pool de modelos esgotado. Disparando descoberta dinâmica de emergência na API do Google...")
                await self.discover_gemini_models(auto_adopt=False)
                fallbacks = self.get_viable_fallback_chain(failed_model, task=task)

            if fallbacks:
                new_model = fallbacks[0]
                old_model = self.data.active_models.get(task, failed_model)
                self.data.active_models[task] = new_model
                self._save()
                logger.warning(
                    f"⚡ [Auto-Remediação Instantânea] Tarefa '{task}' migrada de '{old_model}' para '{new_model}' "
                    f"devido a falha (HTTP {status_code})."
                )
                return new_model
            return failed_model

    def _extract_generation(self, model_name: str) -> float:
        """Extrai a geração numérica do modelo (ex: 'gemini-3.7-flash' -> 3.7)."""
        m = re.search(r"(\d+(?:\.\d+)?)", model_name)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
        return 1.0

    async def discover_gemini_models(
        self,
        api_key: Optional[str] = None,
        auto_adopt: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Consulta a API pública do Google Gemini, mapeia modelos disponíveis e elege os mais custo-eficientes."""
        key = api_key or settings.GEMINI_API_KEY
        if not key or key.startswith("sua_chave"):
            logger.warning("[ModelRegistry] GEMINI_API_KEY não configurada para descoberta de modelos.")
            return {
                "status": "error",
                "message": "GEMINI_API_KEY não configurada.",
                "active_models": self.get_all_active_models(),
                "discovered_count": len(self.data.discovered_models),
            }

        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    logger.error(f"[ModelRegistry] Erro ao listar modelos no Gemini ({resp.status_code}): {resp.text}")
                    return {
                        "status": "error",
                        "message": f"Erro {resp.status_code} na API do Gemini: {resp.text[:200]}",
                        "active_models": self.get_all_active_models(),
                    }

                raw_data = resp.json()
        except Exception as e:
            logger.error(f"[ModelRegistry] Exceção ao consultar API do Gemini: {e}")
            return {
                "status": "error",
                "message": f"Exceção de rede: {e}",
                "active_models": self.get_all_active_models(),
            }

        models_list = raw_data.get("models", [])
        discovered: List[DiscoveredModel] = []

        best_lite_model: Optional[DiscoveredModel] = None
        best_flash_model: Optional[DiscoveredModel] = None
        best_embedding_model: Optional[DiscoveredModel] = None

        for item in models_list:
            full_name = item.get("name", "")
            # Limpa prefixo "models/"
            short_name = full_name.replace("models/", "").strip()
            display_name = item.get("displayName", short_name)
            desc = item.get("description", "")
            methods = item.get("supportedGenerationMethods", [])

            # Ignora modelos que não geram conteúdo nem embeddings
            has_gen = "generateContent" in methods
            has_embed = "embedContent" in methods
            if not has_gen and not has_embed:
                continue

            # Classifica o Tier e Geração
            lower_name = short_name.lower()
            gen = self._extract_generation(short_name)

            if has_embed:
                tier = "EMBEDDING"
                score = 9.0 + (gen * 0.1)
                rec_for = ["embeddings", "vector_search"]
            elif "flash-lite" in lower_name or "lite" in lower_name:
                tier = "LITE"
                # Custo-benefício máximo para tarefas repetitivas
                score = 9.5 + (gen * 0.1)
                rec_for = ["revise", "extract", "fast_transcriptions"]
            elif "flash" in lower_name:
                tier = "FLASH"
                score = 8.5 + (gen * 0.1)
                rec_for = ["summarize", "weekly", "hermes_rag"]
            elif "pro" in lower_name:
                tier = "PRO"
                score = 6.0 + (gen * 0.1)
                rec_for = ["deep_reasoning"]
            else:
                tier = "OTHER"
                score = 5.0
                rec_for = []

            # Verifica modelos depreciados ou descontinuados
            if any(deprecated_str in lower_name for deprecated_str in ["1.5", "2.5-flash", "text-embedding-004"]):
                score = 0.0

            dm = DiscoveredModel(
                name=short_name,
                display_name=display_name,
                description=desc,
                tier=tier,
                generation=gen,
                input_token_limit=item.get("inputTokenLimit", 1048576),
                output_token_limit=item.get("outputTokenLimit", 8192),
                supported_methods=methods,
                cost_efficiency_score=round(score, 2),
                recommended_for=rec_for,
            )

            # Identifica os melhores candidatos para adoção
            if tier == "LITE" and has_gen and score > 0:
                if not best_lite_model or (dm.generation > best_lite_model.generation):
                    best_lite_model = dm

            if tier == "FLASH" and has_gen and score > 0:
                if not best_flash_model or (dm.generation > best_flash_model.generation):
                    best_flash_model = dm

            if tier == "EMBEDDING" and has_embed and score > 0:
                if not best_embedding_model or (dm.generation > best_embedding_model.generation):
                    best_embedding_model = dm

            discovered.append(dm)

        # Ordena por escore de custo-benefício descrescente
        discovered.sort(key=lambda m: (m.cost_efficiency_score, m.generation), reverse=True)

        if best_lite_model:
            best_lite_model.is_recommended = True
        if best_flash_model:
            best_flash_model.is_recommended = True
        if best_embedding_model:
            best_embedding_model.is_recommended = True

        now_iso = datetime.now(timezone.utc).isoformat()
        should_adopt = self.data.auto_adopt_best_lite if auto_adopt is None else auto_adopt

        adopted_changes = {}
        with self._lock:
            self.data.discovered_models = discovered
            self.data.last_discovery_at = now_iso

            if should_adopt:
                # 1. Adota o melhor modelo LITE para tarefas frequentes
                if best_lite_model:
                    for task_name in ["default", "revise", "extract"]:
                        old = self.data.active_models.get(task_name)
                        if old != best_lite_model.name:
                            self.data.active_models[task_name] = best_lite_model.name
                            adopted_changes[task_name] = f"{old} -> {best_lite_model.name}"

                # 2. Adota o melhor modelo FLASH para tarefas de síntese e RAG
                if best_flash_model:
                    for task_name in ["summarize", "weekly", "hermes"]:
                        old = self.data.active_models.get(task_name)
                        # Se já for um modelo lite e usuário prefere lite, mantém lite, caso contrário adota
                        target = best_lite_model.name if (best_lite_model and "lite" in (old or "")) else best_flash_model.name
                        if old != target:
                            self.data.active_models[task_name] = target
                            adopted_changes[task_name] = f"{old} -> {target}"

                # 3. Adota o melhor embedding
                if best_embedding_model:
                    old_emb = self.data.active_models.get("embedding")
                    if old_emb != best_embedding_model.name:
                        self.data.active_models["embedding"] = best_embedding_model.name
                        adopted_changes["embedding"] = f"{old_emb} -> {best_embedding_model.name}"

            # Registra no histórico
            history_entry = {
                "timestamp": now_iso,
                "discovered_count": len(discovered),
                "best_lite": best_lite_model.name if best_lite_model else None,
                "best_flash": best_flash_model.name if best_flash_model else None,
                "best_embedding": best_embedding_model.name if best_embedding_model else None,
                "adopted_changes": adopted_changes,
            }
            self.data.history.insert(0, history_entry)
            self.data.history = self.data.history[:20]  # Mantém os últimos 20 registros

            self._save()

        logger.info(
            f"🔍 [ModelRegistry] Descoberta concluída: {len(discovered)} modelos mapeados. "
            f"Melhor Lite: {best_lite_model.name if best_lite_model else 'Nenhum'}. "
            f"Adoção automática aplicada: {adopted_changes if adopted_changes else 'Nenhuma alteração necessária'}"
        )

        return {
            "status": "success",
            "last_discovery_at": now_iso,
            "discovered_count": len(discovered),
            "best_lite_model": best_lite_model.model_dump() if best_lite_model else None,
            "best_flash_model": best_flash_model.model_dump() if best_flash_model else None,
            "best_embedding_model": best_embedding_model.model_dump() if best_embedding_model else None,
            "adopted_changes": adopted_changes,
            "active_models": self.get_all_active_models(),
            "models": [m.model_dump() for m in discovered[:15]],
        }

    async def check_viable_models(
        self,
        probe_each: bool = True,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Testa em tempo real a viabilidade, latência e status de sobrecarga (503/429) dos modelos.
        Se o modelo ativo principal estiver indisponível ou sobrecarregado, substitui-o automaticamente
        pelo modelo mais rápido e saudável disponível.
        """
        import asyncio
        import time

        key = api_key or settings.GEMINI_API_KEY
        if not key or key.startswith("sua_chave"):
            return {
                "status": "error",
                "message": "GEMINI_API_KEY não configurada.",
                "active_models": self.get_all_active_models(),
                "model_checks": [],
                "auto_remediated": False,
                "remediation_details": {},
            }

        # Monta a lista dinâmica a partir dos modelos descobertos
        discovered_gen = [
            {"name": m.name, "type": "generate", "tier": m.tier}
            for m in self.data.discovered_models
            if "generateContent" in m.supported_methods and m.cost_efficiency_score > 0
        ]
        discovered_emb = [
            {"name": m.name, "type": "embed", "tier": m.tier}
            for m in self.data.discovered_models
            if "embedContent" in m.supported_methods and m.cost_efficiency_score > 0
        ]

        if not discovered_gen and key and not key.startswith("fake-test-key"):
            try:
                await self.discover_gemini_models(api_key=key, auto_adopt=False)
                discovered_gen = [
                    {"name": m.name, "type": "generate", "tier": m.tier}
                    for m in self.data.discovered_models
                    if "generateContent" in m.supported_methods and m.cost_efficiency_score > 0
                ]
                discovered_emb = [
                    {"name": m.name, "type": "embed", "tier": m.tier}
                    for m in self.data.discovered_models
                    if "embedContent" in m.supported_methods and m.cost_efficiency_score > 0
                ]
            except Exception as disc_exc:
                logger.debug(f"Aviso na descoberta dinâmica antes do probe: {disc_exc}")

        # Garante a presença dos modelos base resilientes mais ativos
        candidates_map: Dict[str, Dict[str, str]] = {
            "gemini-3.5-flash-lite": {"name": "gemini-3.5-flash-lite", "type": "generate", "tier": "LITE"},
            "gemini-3.7-flash": {"name": "gemini-3.7-flash", "type": "generate", "tier": "FLASH"},
            "gemini-embedding-001": {"name": "gemini-embedding-001", "type": "embed", "tier": "EMBEDDING"},
        }

        # Incorpora modelos descobertos da API
        for item in (discovered_gen[:6] + discovered_emb[:2]):
            candidates_map[item["name"]] = item

        # Assegura que os modelos atualmente ativos façam parte da lista de auditoria
        for t, m_name in self.data.active_models.items():
            if m_name and m_name not in candidates_map:
                req_type = "embed" if t == "embedding" else "generate"
                tier = "EMBEDDING" if t == "embedding" else ("LITE" if "lite" in m_name.lower() else "FLASH")
                candidates_map[m_name] = {"name": m_name, "type": req_type, "tier": tier}

        candidates = list(candidates_map.values())

        async def probe_candidate(item: Dict[str, str], client: httpx.AsyncClient) -> Dict[str, Any]:
            model_name = item["name"]
            req_type = item["type"]
            tier = item["tier"]

            if not probe_each:
                return {
                    "model": model_name,
                    "tier": tier,
                    "viable": True,
                    "status": "UNCHECKED",
                    "latency_ms": 0,
                }

            start_t = time.perf_counter()
            try:
                if req_type == "generate":
                    probe_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
                    probe_payload = {
                        "contents": [{"parts": [{"text": "ping"}]}],
                        "generationConfig": {"maxOutputTokens": 2, "temperature": 0.0},
                    }
                    resp = await client.post(probe_url, json=probe_payload, timeout=5.0)
                else:
                    probe_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:embedContent?key={key}"
                    probe_payload = {
                        "model": f"models/{model_name}",
                        "content": {"parts": [{"text": "ping"}]},
                        "outputDimensionality": 768,
                    }
                    resp = await client.post(probe_url, json=probe_payload, timeout=5.0)

                latency_ms = round((time.perf_counter() - start_t) * 1000, 1)

                if resp.status_code == 200:
                    return {
                        "model": model_name,
                        "tier": tier,
                        "generation": self._extract_generation(model_name),
                        "viable": True,
                        "status": "HEALTHY",
                        "http_code": 200,
                        "latency_ms": latency_ms,
                    }
                elif resp.status_code in (429, 503):
                    return {
                        "model": model_name,
                        "tier": tier,
                        "viable": False,
                        "status": "OVERLOADED",
                        "http_code": resp.status_code,
                        "latency_ms": latency_ms,
                        "error": f"HTTP {resp.status_code} (Alta demanda / sobrecarga)",
                    }
                elif resp.status_code == 404:
                    return {
                        "model": model_name,
                        "tier": tier,
                        "viable": False,
                        "status": "NOT_FOUND",
                        "http_code": 404,
                        "latency_ms": latency_ms,
                        "error": "HTTP 404 (Modelo inexistente)",
                    }
                else:
                    return {
                        "model": model_name,
                        "tier": tier,
                        "viable": False,
                        "status": "ERROR",
                        "http_code": resp.status_code,
                        "latency_ms": latency_ms,
                        "error": f"HTTP {resp.status_code}",
                    }
            except httpx.TimeoutException:
                return {
                    "model": model_name,
                    "tier": tier,
                    "viable": False,
                    "status": "TIMEOUT",
                    "http_code": 408,
                    "latency_ms": 5000,
                    "error": "Timeout (>5s)",
                }
            except Exception as exc:
                return {
                    "model": model_name,
                    "tier": tier,
                    "viable": False,
                    "status": "ERROR",
                    "http_code": 500,
                    "latency_ms": 0,
                    "error": str(exc),
                }

        async with httpx.AsyncClient() as client:
            tasks = [probe_candidate(item, client) for item in candidates]
            results = await asyncio.gather(*tasks)

        viable_generative = [r for r in results if r.get("viable") and r.get("tier") in ("LITE", "FLASH", "PRO")]
        viable_generative.sort(key=lambda x: (-x.get("generation", 1.0), x.get("latency_ms", 9999)))

        auto_remediated = False
        remediation_details = {}

        best_lite = next((r["model"] for r in viable_generative if r.get("tier") == "LITE"), None)
        best_overall = viable_generative[0]["model"] if viable_generative else None

        with self._lock:
            for task_name, current_model in list(self.data.active_models.items()):
                if task_name == "embedding":
                    continue
                # Se o modelo ativo atual falhou no probe (sobrecarregado 503, 429 ou 404)
                failed_check = next((r for r in results if r["model"] == current_model and not r.get("viable")), None)
                if failed_check and (best_lite or best_overall):
                    replacement = best_lite or best_overall
                    if current_model != replacement:
                        self.data.active_models[task_name] = replacement
                        remediation_details[task_name] = f"{current_model} ({failed_check['status']}) ➔ {replacement}"
                        auto_remediated = True

            if auto_remediated:
                self._save()
                logger.warning(f"🚨 [ModelRegistry] Auto-remediação executada: {remediation_details}")

        now_iso = datetime.now(timezone.utc).isoformat()
        healthy_count = sum(1 for r in results if r.get("viable"))

        return {
            "status": "success",
            "timestamp": now_iso,
            "summary": f"{healthy_count}/{len(results)} modelos viáveis",
            "active_models": self.get_all_active_models(),
            "model_checks": results,
            "auto_remediated": auto_remediated,
            "remediation_details": remediation_details,
        }


# Instância Singleton
model_registry = ModelRegistry()
