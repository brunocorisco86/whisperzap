import json
import os
import re
import math
from collections import Counter, defaultdict
from datetime import datetime, date, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func

from src.memory.task_sentiment_analyzer import get_spacy_nlp

from src.analytics.schemas import (
    AnalyticsDashboardResponse,
    KPICard,
    TimeSeriesPoint,
    TopSenderMetric,
    WordFrequencyItem,
    HeatmapCell,
)
from src.contacts.models import ContactRecord
from src.memory.database import SessionLocal
from src.memory.models import MessageRecord, TaskRecord

# Lista curada de stopwords em português para o WordMap
STOPWORDS_PT = {
    "a", "agora", "ainda", "alem", "além", "algo", "alguem", "alguém", "algum", "alguma",
    "algumas", "alguns", "ali", "ampla", "amplas", "amplo", "amplos", "ano", "anos", "ante",
    "antes", "ao", "aos", "apenas", "apoio", "apos", "após", "aqui", "aquilo", "as", "assim",
    "ate", "até", "audio", "áudio", "audios", "áudios", "bem", "boa", "boas", "bom", "bons",
    "breve", "cada", "caso", "certa", "certas", "certo", "certos", "claro", "coisa", "coisas",
    "com", "como", "contra", "contudo", "da", "dado", "dados", "daquele", "daqueles", "das",
    "de", "dela", "delas", "dele", "deles", "demais", "depois", "dessa", "dessas", "desse",
    "desses", "desta", "destas", "deste", "destes", "deve", "devem", "deveria", "deveriam",
    "dia", "dias", "disse", "disso", "diz", "dizem", "do", "dois", "dos", "durante", "e",
    "ela", "elas", "ele", "eles", "em", "enquanto", "entao", "então", "entre", "era", "eram",
    "essa", "essas", "esse", "esses", "esta", "está", "estamos", "estao", "estão", "estas",
    "estava", "estavam", "este", "estes", "esteve", "estivemos", "estiveram", "estou", "eu",
    "fala", "falar", "faz", "fazer", "fazem", "fazemos", "fez", "ficou", "fim", "foi", "fomos",
    "foram", "forma", "grande", "grandes", "ha", "há", "havia", "hoje", "horas", "isso",
    "isto", "ja", "já", "la", "lá", "lhe", "lhes", "mais", "mas", "me", "mesma", "mesmas",
    "mesmo", "mesmos", "meu", "meus", "minha", "minhas", "muito", "muita", "muitos", "muitas",
    "na", "nada", "nao", "não", "nas", "nem", "nenhum", "nenhuma", "nessa", "nessas", "nesse",
    "nesses", "nesta", "nestas", "neste", "nestes", "no", "noite", "nome", "nos", "nós", "nossa",
    "nossas", "nosso", "nossos", "nova", "novas", "novo", "novos", "num", "numa", "nunca",
    "o", "ola", "olá", "onde", "os", "ou", "outra", "outras", "outro", "outros", "para", "parte",
    "passado", "pela", "pelas", "pelo", "pelos", "pequeno", "pequenos", "perto", "pode", "podem",
    "poder", "poderia", "poderiam", "pois", "por", "porque", "porquê", "posso", "pouco", "poucos",
    "pra", "primeiro", "primeiros", "pro", "proprio", "próprio", "qual", "quais", "qualquer",
    "quando", "quanto", "quantos", "quase", "quatro", "que", "quem", "quer", "quereis", "querem",
    "queremos", "queria", "quero", "sabe", "saber", "sao", "são", "se", "seja", "sejam", "sem",
    "sempre", "sendo", "ser", "sera", "será", "serao", "serão", "seria", "seriam", "seu", "seus",
    "si", "sido", "so", "só", "sob", "sobre", "sua", "suas", "tal", "talvez", "tambem", "também",
    "tanta", "tantas", "tanto", "tantos", "tarde", "te", "tem", "têm", "temos", "tendo", "tenha",
    "tenham", "tenho", "ter", "terceiro", "teve", "ti", "tido", "tinha", "tinham", "toda", "todas",
    "todo", "todos", "trabalho", "tres", "três", "tudo", "um", "uma", "umas", "uns", "vai",
    "valer", "vamos", "vao", "vão", "vc", "vcs", "veja", "vem", "vendo", "ver", "verdade",
    "vez", "vezes", "vi", "viu", "você", "voces", "vocês", "vou",
    # Preenchimentos conversacionais e saudações comuns
    "cara", "mano", "gente", "olha", "tipo", "falou", "beleza", "valeu", "ok", "obrigado",
    "obrigada", "tá", "ta", "né", "ne", "ah", "eh", "oh", "uh", "hum", "opa", "abraço",
    "amanhã", "ontem", "bom", "dia", "boa", "tarde", "noite", "áudio", "audio", "mensagem",
    "gravação", "gravacao", "whatsapp", "transcrição", "transcricao",
    # Ruídos técnicos de XML, drawio e diagramas que não pertencem a conversas
    "mxcell", "parent", "mxgeometry", "vertex", "style", "geometry", "target", "source",
    "edge", "value", "points", "array", "root", "model", "diagram", "page", "grid", "xml",
    "html", "http", "https", "drawio", "node", "label", "width", "height", "rel", "true",
    "false", "null", "undefined", "none", "nan", "xmlns", "doctype", "svg", "fill", "stroke",
}

CATEGORY_KEYWORDS = {
    "GARGALOS": {
        "fila", "espera", "fila de espera", "atendimento", "chamado", "chamados", "suporte",
        "dúvida", "duvida", "dúvidas", "duvidas", "problema", "problemas", "urgência", "urgencia",
        "atraso", "atrasos", "reclamação", "reclamacao", "erro", "erros", "falha", "falhas",
        "incidente", "bloqueio", "cobrança", "cobranca", "cancelamento", "pendência", "pendencia",
    },
    "AGRONEGOCIO": {
        "c.vale", "cvale", "cooperativa", "produtor", "produtores", "associado", "associados",
        "cooperado", "cooperados", "safra", "grãos", "graos", "milho", "soja", "campo", "fazenda",
        "lavoura", "agronegócio", "agronegocio", "insumos", "sementes", "adubo", "defensivos",
        "colheita", "balança", "balanca", "secador", "armazém", "armazem", "silo", "silos",
    },
    "ZOOTECNIA": {
        "ração", "racao", "silo", "silos", "aviário", "aviario", "aviários", "aviarios",
        "lote", "lotes", "frango", "frangos", "ave", "aves", "mortalidade", "conversão", "conversao",
        "iep", "peso", "pesagem", "clima", "temperatura", "umidade", "ventilação", "ventilacao",
        "ventilador", "ventiladores", "bebedouro", "bebedouros", "comedouro", "comedouros",
        "nipple", "fal", "fau", "integrado", "integrados", "granja", "granjas", "caseiro",
        "placa", "evaporativa", "sensor", "sensores", "sensorização", "amônia", "amonia",
        "vacina", "vacinação", "pintainho", "pintainhos", "abate", "densidade", "cortina",
        "aquecedor", "gerador", "geradores", "aquecimento",
    },
    "LOGISTICA": {
        "caminhão", "caminhao", "caminhões", "caminhoes", "entrega", "entregas", "motorista",
        "motoristas", "descarga", "fábrica", "fabrica", "rota", "rotas", "pedido", "pedidos",
        "carregamento", "transporte", "prazo", "agendamento", "tms", "frete", "logística",
        "logistica", "expedição", "expedicao", "frota", "carga", "cargas", "transbordo", "viagem",
    },
    "SISTEMAS": {
        "agrocenter", "eprodutor", "e-produtor", "mtech", "portal", "erp", "aplicativo", "app",
        "sistema", "sistemas", "software", "login", "chamado", "chamados", "suporte", "senha",
        "acesso", "integração", "integracao", "api", "webhook", "banco de dados",
    },
    "TECNOLOGIA": {
        "ia", "inteligência", "inteligencia", "modelo", "modelos", "gemini", "whisper", "faster-whisper",
        "servidor", "vps", "hostinger", "docker", "linux", "raspberry", "tailscale", "python",
        "grafo", "pgvector", "embedding", "embeddings", "neural", "rag", "oráculo", "oraculo",
    },
    "GESTAO": {
        "reunião", "reuniao", "reuniões", "reunioes", "relatório", "relatorio", "relatórios",
        "diretoria", "gerência", "gerencia", "gerente", "meta", "metas", "resultado", "resultados",
        "custo", "custos", "planejamento", "estratégia", "estrategia", "apresentação", "apresentacao",
        "indicador", "indicadores", "kpi", "kpis", "orçamento", "orcamento", "aprovação", "aprovacao",
        "decisão", "decisao", "contrato", "contratos", "auditoria", "ata", "equipe", "projeto",
        "projetos", "investimento", "receita", "margem", "despesa", "financeiro",
    },
    "PESSOAL": {
        "família", "familia", "esposa", "marido", "filho", "filha", "filhos", "pai", "mãe",
        "casa", "viagem", "consulta", "médico", "medico", "saúde", "saude", "almoço", "almoco",
        "jantar", "pagamento", "banco", "compromisso", "pessoal", "aniversário", "aniversario",
        "férias", "ferias", "folga",
    },
    "OPERACOES": {
        "tarefa", "tarefas", "atividade", "atividades", "verificação", "verificacao", "manutenção",
        "manutencao", "conferência", "conferencia", "visita", "vistoria", "teste", "testes",
        "ajuste", "ajustes", "conserto", "reparo", "limpeza", "troca", "substituição",
    },
}


class AnalyticsService:
    """Calcula KPIs, séries temporais e estatísticas consolidadas para o Dashboard."""

    def get_dashboard_metrics(
        self,
        period: str = "30d",
        group_by: str = "day",
        db: Session | None = None,
    ) -> AnalyticsDashboardResponse:
        """Processa e consolida todas as métricas analíticas."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            now = datetime.now(timezone.utc)
            start_date, end_date, prev_start, prev_end = self._resolve_date_ranges(period, now)

            from src.ai_gateway.bypass import is_owner_interaction

            # 1. Carrega mensagens do período atual e anterior
            raw_current_messages = (
                db.query(MessageRecord)
                .filter(MessageRecord.created_at >= start_date, MessageRecord.created_at <= end_date)
                .order_by(MessageRecord.created_at.asc())
                .all()
            )

            raw_prev_messages = (
                db.query(MessageRecord)
                .filter(MessageRecord.created_at >= prev_start, MessageRecord.created_at < start_date)
                .all()
            )

            # Filtra interações do próprio usuário/proprietário do dashboard executivo
            current_messages = [m for m in raw_current_messages if not is_owner_interaction(m.speaker, m.meta_info)]
            prev_messages = [m for m in raw_prev_messages if not is_owner_interaction(m.speaker, m.meta_info)]

            # 2. Carrega tarefas associadas
            current_tasks = (
                db.query(TaskRecord)
                .filter(TaskRecord.created_at >= start_date, TaskRecord.created_at <= end_date)
                .all()
            )

            prev_tasks = (
                db.query(TaskRecord)
                .filter(TaskRecord.created_at >= prev_start, TaskRecord.created_at < start_date)
                .all()
            )

            # 3. Carrega contatos para enriquecimento
            contacts_map = {c.name.lower(): c for c in db.query(ContactRecord).all()}

            # 4. Calcula 5 Hero KPIs
            kpi_unique = self._calculate_unique_senders_kpi(current_messages, prev_messages)
            kpi_total_msg = self._calculate_total_messages_kpi(current_messages, prev_messages)
            kpi_audio = self._calculate_audio_duration_kpi(current_messages, prev_messages)
            kpi_action = self._calculate_actionability_kpi(current_messages, current_tasks, prev_messages, prev_tasks)
            kpi_sentiment = self._calculate_sentiment_health_kpi(current_messages, prev_messages)

            # 5. Gera TimeSeries agrupada
            timeseries = self._generate_timeseries(current_messages, current_tasks, start_date, end_date, group_by)

            # 6. Gera Top Interlocutores
            top_senders = self._generate_top_senders(current_messages, current_tasks, contacts_map)

            # 7. Gera WordMap / Nuvem Semântica de Termos
            wordmap = self._generate_wordmap(current_messages)

            # 8. Gera Heatmap de Horários de Pico (24x7)
            heatmap = self._generate_heatmap(current_messages)

            # Resumo executivo de inteligência
            summary = self._generate_executive_summary(
                kpi_unique.value,
                kpi_total_msg.value,
                kpi_action.value,
                top_senders[0].speaker if top_senders else "Nenhum",
            )

            return AnalyticsDashboardResponse(
                period=period,
                group_by=group_by,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
                kpi_unique_senders=kpi_unique,
                kpi_total_messages=kpi_total_msg,
                kpi_audio_duration=kpi_audio,
                kpi_actionability_rate=kpi_action,
                kpi_sentiment_health=kpi_sentiment,
                timeseries=timeseries,
                top_senders=top_senders,
                wordmap=wordmap,
                heatmap=heatmap,
                summary_text=summary,
            )
        finally:
            if should_close:
                db.close()

    def _resolve_date_ranges(self, period: str, now: datetime) -> Tuple[datetime, datetime, datetime, datetime]:
        """Calcula o intervalo de datas atual e o período anterior equivalente."""
        period_clean = (period or "30d").lower()

        if period_clean == "today":
            start_date = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=timezone.utc)
            end_date = now
            delta = timedelta(days=1)
            prev_start = start_date - delta
            prev_end = start_date
        elif period_clean == "7d":
            start_date = now - timedelta(days=7)
            end_date = now
            delta = timedelta(days=7)
            prev_start = start_date - delta
            prev_end = start_date
        elif period_clean == "month":
            start_date = datetime(now.year, now.month, 1, 0, 0, 0, tzinfo=timezone.utc)
            end_date = now
            # Mês anterior
            last_month = (start_date - timedelta(days=1)).replace(day=1)
            prev_start = last_month
            prev_end = start_date
        elif period_clean == "all":
            start_date = now - timedelta(days=365)
            end_date = now
            prev_start = start_date - timedelta(days=365)
            prev_end = start_date
        else:  # default '30d'
            start_date = now - timedelta(days=30)
            end_date = now
            delta = timedelta(days=30)
            prev_start = start_date - delta
            prev_end = start_date

        return start_date, end_date, prev_start, prev_end

    def _calculate_trend(self, current_val: float, prev_val: float) -> Tuple[Optional[float], Optional[str]]:
        """Calcula a variação percentual e direção da tendência."""
        if prev_val == 0:
            if current_val > 0:
                return 100.0, "UP"
            return 0.0, "NEUTRAL"

        diff = ((current_val - prev_val) / prev_val) * 100.0
        direction = "UP" if diff > 0.5 else ("DOWN" if diff < -0.5 else "NEUTRAL")
        return round(diff, 1), direction

    def _calculate_unique_senders_kpi(self, current_msgs: List[MessageRecord], prev_msgs: List[MessageRecord]) -> KPICard:
        curr_unique = len(set(m.speaker for m in current_msgs if m.speaker))
        prev_unique = len(set(m.speaker for m in prev_msgs if m.speaker))
        trend, dir_ = self._calculate_trend(curr_unique, prev_unique)

        return KPICard(
            title="Pessoas em Contato",
            value=curr_unique,
            subtitle=f"{prev_unique} no período anterior",
            trend_pct=trend,
            trend_direction=dir_,
            icon="👥",
        )

    def _calculate_total_messages_kpi(self, current_msgs: List[MessageRecord], prev_msgs: List[MessageRecord]) -> KPICard:
        curr_total = len(current_msgs)
        prev_total = len(prev_msgs)
        audio_count = sum(1 for m in current_msgs if m.audio_duration_s or m.audio_filename)
        trend, dir_ = self._calculate_trend(curr_total, prev_total)

        return KPICard(
            title="Total de Interações",
            value=curr_total,
            subtitle=f"{audio_count} áudios ({round((audio_count / curr_total * 100) if curr_total > 0 else 0)}%)",
            trend_pct=trend,
            trend_direction=dir_,
            icon="💬",
        )

    def _calculate_audio_duration_kpi(self, current_msgs: List[MessageRecord], prev_msgs: List[MessageRecord]) -> KPICard:
        audios = [m.audio_duration_s for m in current_msgs if m.audio_duration_s and m.audio_duration_s > 0]
        prev_audios = [m.audio_duration_s for m in prev_msgs if m.audio_duration_s and m.audio_duration_s > 0]

        total_sec = sum(audios)
        avg_sec = total_sec / len(audios) if audios else 0.0
        prev_avg = sum(prev_audios) / len(prev_audios) if prev_audios else 0.0

        trend, dir_ = self._calculate_trend(avg_sec, prev_avg)
        total_min = round(total_sec / 60.0, 1)

        return KPICard(
            title="Duração Média de Áudio",
            value=f"{round(avg_sec)}s" if avg_sec > 0 else "0s",
            subtitle=f"Total: {total_min} min de áudios",
            trend_pct=trend,
            trend_direction=dir_,
            icon="⏱️",
        )

    def _calculate_actionability_kpi(
        self,
        current_msgs: List[MessageRecord],
        current_tasks: List[TaskRecord],
        prev_msgs: List[MessageRecord],
        prev_tasks: List[TaskRecord],
    ) -> KPICard:
        curr_msgs_count = len(current_msgs)
        curr_tasks_count = len(current_tasks)
        curr_rate = (curr_tasks_count / curr_msgs_count * 100.0) if curr_msgs_count > 0 else 0.0

        prev_msgs_count = len(prev_msgs)
        prev_tasks_count = len(prev_tasks)
        prev_rate = (prev_tasks_count / prev_msgs_count * 100.0) if prev_msgs_count > 0 else 0.0

        trend, dir_ = self._calculate_trend(curr_rate, prev_rate)

        return KPICard(
            title="Taxa de Ação (% Tarefas)",
            value=f"{round(curr_rate, 1)}%",
            subtitle=f"{curr_tasks_count} tarefas geradas",
            trend_pct=trend,
            trend_direction=dir_,
            icon="🎯",
        )

    def _calculate_sentiment_health_kpi(self, current_msgs: List[MessageRecord], prev_msgs: List[MessageRecord]) -> KPICard:
        if not current_msgs:
            return KPICard(title="Saúde do Sentimento", value="Neutro", subtitle="Sem dados no período", icon="😊")

        positive_count = sum(1 for m in current_msgs if (m.sentiment or "").upper() == "POSITIVE" or (m.sentiment_score or 0) > 0.2)
        urgent_count = sum(1 for m in current_msgs if (m.sentiment or "").upper() == "URGENT" or (m.urgency or "").upper() in ("HIGH", "URGENT"))

        pos_pct = round((positive_count / len(current_msgs)) * 100)

        return KPICard(
            title="Saúde do Sentimento",
            value=f"{pos_pct}% Positivo",
            subtitle=f"{urgent_count} interações urgentes",
            trend_pct=None,
            trend_direction="UP" if pos_pct >= 50 else "NEUTRAL",
            icon="😊",
        )

    def _generate_timeseries(
        self,
        messages: List[MessageRecord],
        tasks: List[TaskRecord],
        start_date: datetime,
        end_date: datetime,
        group_by: str,
    ) -> List[TimeSeriesPoint]:
        """Gera pontos agregados no tempo por dia, semana ou mês."""
        group_by_clean = (group_by or "day").lower()
        buckets: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "raw_date": "",
                "label": "",
                "speakers": set(),
                "total": 0,
                "audios": 0,
                "texts": 0,
                "chars_list": [],
                "durations_list": [],
                "tasks": 0,
            }
        )

        for m in messages:
            dt = m.created_at
            if not dt:
                continue

            if group_by_clean == "week":
                year, week_num, _ = dt.isocalendar()
                bucket_key = f"{year}-W{week_num:02d}"
                label = f"Sem {week_num:02d}"
            elif group_by_clean == "month":
                bucket_key = dt.strftime("%Y-%m")
                label = dt.strftime("%b/%y")
            else:  # 'day'
                bucket_key = dt.strftime("%Y-%m-%d")
                label = dt.strftime("%d/%m")

            b = buckets[bucket_key]
            b["raw_date"] = bucket_key
            b["label"] = label
            if m.speaker:
                b["speakers"].add(m.speaker)
            b["total"] += 1

            if m.audio_duration_s and m.audio_duration_s > 0:
                b["audios"] += 1
                b["durations_list"].append(m.audio_duration_s)
            else:
                b["texts"] += 1

            text_len = len(m.revised_text) if m.revised_text else (len(m.raw_text) if m.raw_text else 0)
            if text_len > 0:
                b["chars_list"].append(text_len)

        # Mapeia tarefas aos buckets
        for t in tasks:
            dt = t.created_at
            if not dt:
                continue
            if group_by_clean == "week":
                year, week_num, _ = dt.isocalendar()
                bucket_key = f"{year}-W{week_num:02d}"
            elif group_by_clean == "month":
                bucket_key = dt.strftime("%Y-%m")
            else:
                bucket_key = dt.strftime("%Y-%m-%d")

            if bucket_key in buckets:
                buckets[bucket_key]["tasks"] += 1

        # Ordena cronologicamente
        sorted_keys = sorted(buckets.keys())
        points = []
        for k in sorted_keys:
            b = buckets[k]
            avg_chars = sum(b["chars_list"]) / len(b["chars_list"]) if b["chars_list"] else 0.0
            avg_dur = sum(b["durations_list"]) / len(b["durations_list"]) if b["durations_list"] else 0.0

            points.append(
                TimeSeriesPoint(
                    period_label=b["label"],
                    raw_date=b["raw_date"],
                    unique_senders=len(b["speakers"]),
                    total_messages=b["total"],
                    audio_messages=b["audios"],
                    text_messages=b["texts"],
                    avg_chars=round(avg_chars, 1),
                    avg_audio_duration_s=round(avg_dur, 1),
                    tasks_generated=b["tasks"],
                )
            )

        return points

    def _generate_top_senders(
        self,
        messages: List[MessageRecord],
        tasks: List[TaskRecord],
        contacts_map: Dict[str, ContactRecord],
    ) -> List[TopSenderMetric]:
        """Agrupa métricas por remetente e retorna o ranking ordenado."""
        sender_data: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "total": 0,
                "audios": 0,
                "total_duration": 0.0,
                "tasks": 0,
                "sentiments": [],
                "scores": [],
            }
        )

        for m in messages:
            spk = m.speaker or "Desconhecido"
            sd = sender_data[spk]
            sd["total"] += 1
            if m.audio_duration_s:
                sd["audios"] += 1
                sd["total_duration"] += m.audio_duration_s
            if m.sentiment:
                sd["sentiments"].append(m.sentiment)
            if m.sentiment_score is not None:
                sd["scores"].append(m.sentiment_score)

        # Mapeia tarefas aos remetentes das mensagens
        msg_sender_map = {m.id: (m.speaker or "Desconhecido") for m in messages}
        for t in tasks:
            spk = msg_sender_map.get(t.message_id)
            if spk and spk in sender_data:
                sender_data[spk]["tasks"] += 1

        top_list = []
        for spk, data in sender_data.items():
            contact = contacts_map.get(spk.lower())
            
            # Sentimento dominante
            dom_sentiment = "NEUTRAL"
            if data["sentiments"]:
                dom_sentiment = Counter(data["sentiments"]).most_common(1)[0][0]
            avg_score = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0.0

            top_list.append(
                TopSenderMetric(
                    speaker=spk,
                    role=contact.role if contact else (contact.category if contact else "UNKNOWN"),
                    phone_number=contact.phone_number if contact else None,
                    avatar_url=contact.avatar_url if contact else None,
                    total_messages=data["total"],
                    audio_count=data["audios"],
                    total_duration_s=round(data["total_duration"], 1),
                    tasks_count=data["tasks"],
                    dominant_sentiment=dom_sentiment,
                    avg_sentiment_score=round(avg_score, 2),
                )
            )

        # Ordena por total de mensagens decrescente
        top_list.sort(key=lambda x: x.total_messages, reverse=True)
        return top_list[:15]

    def _generate_wordmap(self, messages: List[MessageRecord]) -> List[WordFrequencyItem]:
        """Gera frequência de termos estratégicos e sintagmas nominais compostos utilizando spaCy NLP."""
        term_counts = Counter()
        term_contexts: Dict[str, str] = {}
        is_compound_map: Dict[str, bool] = {}

        # Carrega termos do Dicionário Léxico para enriquecer as categorias dinamicamente
        dynamic_categories: Dict[str, set] = {k: set(v) for k, v in CATEGORY_KEYWORDS.items()}
        try:
            dict_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "lexical_dictionary.json")
            if os.path.exists(dict_path):
                with open(dict_path, "r", encoding="utf-8") as f:
                    dict_terms = json.load(f)
                    for item in dict_terms:
                        cat = (item.get("category") or "AGRONEGOCIO").upper()
                        if cat not in dynamic_categories:
                            dynamic_categories[cat] = set()
                        term_tokens = re.findall(r"\b[a-zA-ZáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]{3,}\b", item.get("term", "").lower())
                        for tok in term_tokens:
                            dynamic_categories[cat].add(tok)
                        for var in item.get("phonetic_variations", []):
                            var_tokens = re.findall(r"\b[a-zA-ZáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]{3,}\b", var.lower())
                            for tok in var_tokens:
                                dynamic_categories[cat].add(tok)
        except Exception:
            pass

        nlp = get_spacy_nlp()
        xml_noise_regex = re.compile(r"^(mxcell|parent|mxgeometry|vertex|style|geometry|target|source|edge|value|points|array|root|model|diagram|page|grid|xml|html|http|https|drawio|node|label|width|height|rel|true|false|null|undefined|none|nan|xmlns|doctype|svg|fill|stroke)$", re.IGNORECASE)
        noise_articles = {"o", "a", "os", "as", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas", "para", "por", "com", "este", "esta", "esse", "essa", "aquele", "aquela"}

        for m in messages:
            text = ((m.revised_text or "") + " " + (m.summary or "")).strip()
            if not text:
                continue

            # Contexto resumido para o tooltip
            clean_snippet = re.sub(r"\s+", " ", text)[:110]

            if nlp is not None:
                doc = nlp(text)

                # 1. Extração de Sintagmas Nominais Compostos (Noun Chunks)
                if hasattr(doc, "noun_chunks"):
                    for chunk in doc.noun_chunks:
                        chunk_words = [t.text.lower() for t in chunk if not t.is_punct and not xml_noise_regex.match(t.text)]
                        # Remove artigos e preposições do início e fim
                        while chunk_words and chunk_words[0] in noise_articles:
                            chunk_words.pop(0)
                        while chunk_words and chunk_words[-1] in noise_articles:
                            chunk_words.pop()

                        if 2 <= len(chunk_words) <= 4:
                            phrase = " ".join(chunk_words)
                            # Verifica se tem substantivo relevante
                            if not any(xml_noise_regex.match(w) for w in chunk_words) and all(len(w) >= 2 for w in chunk_words):
                                term_counts[phrase] += 2
                                is_compound_map[phrase] = True
                                if phrase not in term_contexts:
                                    term_contexts[phrase] = clean_snippet

                # 2. Extração de Substantivos e Nomes Próprios Estratégicos (Lemmatized)
                for token in doc:
                    if token.pos_ in ("NOUN", "PROPN") and not token.is_punct:
                        lemma = (token.lemma_ or token.text).lower().strip()
                        if (
                            len(lemma) >= 3
                            and lemma not in STOPWORDS_PT
                            and lemma not in noise_articles
                            and not xml_noise_regex.match(lemma)
                        ):
                            term_counts[lemma] += 1
                            if lemma not in term_contexts:
                                term_contexts[lemma] = clean_snippet
            else:
                # Fallback sem spaCy
                tokens = re.findall(r"\b[a-zA-ZáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]{3,}\b", text.lower())
                for t in tokens:
                    if t not in STOPWORDS_PT and not xml_noise_regex.match(t):
                        term_counts[t] += 1
                        if t not in term_contexts:
                            term_contexts[t] = clean_snippet

        if not term_counts:
            return []

        # Seleciona os 50 termos/sintagmas mais expressivos
        most_common = term_counts.most_common(50)
        max_freq = most_common[0][1] if most_common else 1

        items = []
        for word, count in most_common:
            # Classifica categoria analisando a expressão inteira ou subpalavras
            cat = "TEMAS"
            matched = False
            for category_name, kw_set in dynamic_categories.items():
                if word in kw_set:
                    cat = category_name
                    matched = True
                    break

            if not matched:
                # Analisa palavras individuais do termo
                for sub_w in word.split():
                    for category_name, kw_set in dynamic_categories.items():
                        if sub_w in kw_set:
                            cat = category_name
                            matched = True
                            break
                    if matched:
                        break

            weight_pct = round((count / max_freq) * 100, 1)
            items.append(
                WordFrequencyItem(
                    word=word,
                    count=count,
                    category=cat,
                    weight_pct=weight_pct,
                    is_compound=is_compound_map.get(word, False),
                    sample_context=term_contexts.get(word),
                )
            )

        return items

    def _generate_heatmap(self, messages: List[MessageRecord]) -> List[HeatmapCell]:
        """Gera matriz 24h x 7 dias para identificar horários de pico."""
        matrix: Dict[Tuple[int, int], int] = defaultdict(int)

        for m in messages:
            dt = m.created_at
            if not dt:
                continue
            day_of_week = dt.weekday()  # 0 = Segunda, 6 = Domingo
            hour = dt.hour
            matrix[(day_of_week, hour)] += 1

        day_names = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
        cells = []
        for day in range(7):
            for h in range(24):
                count = matrix[(day, h)]
                cells.append(
                    HeatmapCell(
                        day_of_week=day,
                        day_name=day_names[day],
                        hour=h,
                        count=count,
                    )
                )

        return cells

    def _generate_executive_summary(self, unique_senders: Any, total_msgs: Any, action_rate: Any, top_sender: str) -> str:
        """Gera um texto executivo resumindo as principais descobertas analíticas."""
        return (
            f"No período analisado, foram registradas {total_msgs} interações de {unique_senders} pessoas distintas. "
            f"O principal interlocutor foi '{top_sender}'. A taxa de acionabilidade foi de {action_rate}, "
            f"indicando a eficiência da extração de decisões e tarefas."
        )


analytics_service = AnalyticsService()
