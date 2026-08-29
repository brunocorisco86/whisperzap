"""Testes unitários para Bypass de IA, Filtro de Grupos e Exclusão do Proprietário do Dashboard."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from src.ai_gateway.bypass import (
    is_group_message,
    is_owner_interaction,
    normalize_text,
    should_bypass_ai,
)
from src.analytics.service import analytics_service
from src.config import settings
from src.memory.database import SessionLocal, init_db
from src.memory.models import MessageCreate, MessageRecord
from src.memory.repository import memory_repository
from src.memory.sentiment_timeline import sentiment_timeline_service


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def test_normalize_text():
    assert normalize_text("Bom dia!!") == "bom dia"
    assert normalize_text("  Olá,   tudo bem?  ") == "ola tudo bem"
    assert normalize_text("123-ABC") == "123 abc"
    assert normalize_text("") == ""


def test_is_group_message():
    assert is_group_message({"remoteJid": "12036302482910@g.us"}) is True
    assert is_group_message({"remoteJid": "status@broadcast"}) is True
    assert is_group_message({"isGroup": True}) is True
    assert is_group_message({"participant": "5544999990001@s.whatsapp.net"}) is True

    # Mensagem privada legítima
    assert is_group_message({"remoteJid": "5544999990001@s.whatsapp.net"}) is False
    assert is_group_message({}) is False
    assert is_group_message(None) is False


def test_is_owner_interaction():
    # Identificação por telefone
    assert is_owner_interaction(speaker="554497604925") is True
    assert is_owner_interaction(meta_info={"remoteJid": "554497604925@s.whatsapp.net"}) is True
    assert is_owner_interaction(meta_info={"fromMe": True}) is True

    # Identificação por nome / alias
    assert is_owner_interaction(speaker="Bruno") is True
    assert is_owner_interaction(speaker="user") is True
    assert is_owner_interaction(meta_info={"pushName": "Bruno"}) is True

    # Interlocutor externo
    assert is_owner_interaction(speaker="Carlos Gestor") is False
    assert is_owner_interaction(speaker="5544999990001") is False
    assert is_owner_interaction(meta_info={"remoteJid": "5544999990001@s.whatsapp.net", "fromMe": False}) is False


def test_should_bypass_ai():
    # Mensagens curtas (<= 15 caracteres)
    bypass, reason = should_bypass_ai("oi")
    assert bypass is True

    bypass, reason = should_bypass_ai("bom dia")
    assert bypass is True

    bypass, reason = should_bypass_ai("meu nome")
    assert bypass is True

    bypass, reason = should_bypass_ai("ok beleza")
    assert bypass is True

    # Mensagens sem texto / emojis
    bypass, reason = should_bypass_ai("👍 🙏")
    assert bypass is True

    bypass, reason = should_bypass_ai("", message_type="stickerMessage")
    assert bypass is True

    bypass, reason = should_bypass_ai("", message_type="reactionMessage")
    assert bypass is True

    # Grupo com flag de ignorar ativo
    bypass, reason = should_bypass_ai("Texto longo para teste com mais de quinze caracteres", meta_info={"remoteJid": "12036302482910@g.us"})
    assert bypass is True
    assert reason == "group_message"

    # Bypass explícito no payload
    bypass, reason = should_bypass_ai("Texto longo com mais de 20 caracteres sem grupo", meta_info={"bypass_ai": True})
    assert bypass is True
    assert reason == "explicit_bypass"

    # Mensagem informativa longa real (NÃO deve fazer bypass)
    bypass, reason = should_bypass_ai("Precisamos revisar o lote 45 e a calibração dos sensores de silo da C.Vale com urgência.")
    assert bypass is False
    assert reason == "process_ai"


from src.ai_gateway.bypass import (
    is_emoji_only_or_symbols,
    is_group_message,
    is_owner_interaction,
    normalize_text,
    should_bypass_ai,
    should_drop_message,
)


def test_is_emoji_only_or_symbols():
    assert is_emoji_only_or_symbols("🥰🥰🥰") is True
    assert is_emoji_only_or_symbols("👍") is True
    assert is_emoji_only_or_symbols("🤝") is True
    assert is_emoji_only_or_symbols("🐔🇧🇷") is True
    assert is_emoji_only_or_symbols("??? !!! ...") is True
    assert is_emoji_only_or_symbols("") is True
    assert is_emoji_only_or_symbols("   ") is True

    # Mensagens com texto real
    assert is_emoji_only_or_symbols("Olá tudo bem? 🥰") is False
    assert is_emoji_only_or_symbols("Relatório pronto 👍") is False
    assert is_emoji_only_or_symbols("Calibração do sensor do silo 3") is False


def test_should_drop_message():
    # 1. Textos vazios / nulos
    assert should_drop_message("")[0] is True
    assert should_drop_message(None)[0] is True
    assert should_drop_message("   ")[0] is True

    # 2. Apenas emojis / símbolos
    assert should_drop_message("🥰🥰🥰🥰")[0] is True
    assert should_drop_message("🤝")[0] is True
    assert should_drop_message("👍 🙏")[0] is True

    # 3. Mídias não textuais
    assert should_drop_message("", message_type="stickerMessage")[0] is True
    assert should_drop_message("", message_type="reactionMessage")[0] is True
    assert should_drop_message("", message_type="imageMessage")[0] is True

    # 4. Mensagens de grupo
    assert should_drop_message("Texto longo de grupo com mais de 20 caracteres", meta_info={"remoteJid": "12036302482910@g.us"})[0] is True

    # 5. Saudações triviais / ruídos curtos
    assert should_drop_message("oi")[0] is True
    assert should_drop_message("bom dia")[0] is True
    assert should_drop_message("boa tarde")[0] is True
    assert should_drop_message("tudo bem")[0] is True
    assert should_drop_message("ok")[0] is True

    # 6. Mensagem de negócio legítima (GANHA PRIVILÉGIO DE IA)
    drop, reason = should_drop_message("Precisamos revisar o lote 45 e a calibração dos sensores de silo da C.Vale com urgência.")
    assert drop is False
    assert reason == "privileged_valid_message"

    # Pergunta com comando ou pergunta de negócio ganha privilégio
    drop, reason = should_drop_message("? Como estão os níveis dos silos da granja?")
    assert drop is False
    assert reason == "privileged_valid_message"

    # Frases sociais adicionais descartadas
    assert should_drop_message("partiu")[0] is True
    assert should_drop_message("fechou entao")[0] is True
    assert should_drop_message("que bacana")[0] is True


@pytest.mark.asyncio
async def test_save_message_drops_empty_and_emojis():
    db = SessionLocal()
    try:
        # Envia apenas emojis -> deve retornar None e não salvar
        msg_emoji = MessageCreate(
            speaker="Tuca",
            raw_text="🥰🥰🥰🥰🥰🥰🥰",
            revised_text="🥰🥰🥰🥰🥰🥰🥰",
            meta_info={"source": "whatsapp", "message_type": "text"},
        )
        saved_emoji = await memory_repository.save_message(msg_emoji, db=db)
        assert saved_emoji is None

        # Envia texto vazio de áudio inaudível -> deve retornar None
        msg_empty = MessageCreate(
            speaker="Bruno",
            raw_text="",
            revised_text="",
            audio_duration_s=5,
            meta_info={"source": "whatsapp", "message_type": "audio"},
        )
        saved_empty = await memory_repository.save_message(msg_empty, db=db)
        assert saved_empty is None

        # Envia mensagem de contato SEM CARTÃO -> deve retornar None (rejeitado por não ter cartão)
        msg_no_card = MessageCreate(
            speaker="Desconhecido Sem Cartao",
            raw_text="Mensagem sem cartão cadastrado não gera memória.",
            revised_text="Mensagem sem cartão cadastrado não gera memória.",
            meta_info={"source": "whatsapp", "message_type": "text", "phone": "5544999999999"},
        )
        saved_no_card = await memory_repository.save_message(msg_no_card, db=db)
        assert saved_no_card is None

        # Cadastra o cartão do João Silva
        from src.contacts.models import ContactRecord
        c_joao = ContactRecord(id="c-joao-test", name="João Silva", phone_number="5544999991234", role="EXECUTIVE")
        db.merge(c_joao)
        db.commit()

        # Envia mensagem válida de contato COM CARTÃO -> deve salvar normalmente
        msg_valid = MessageCreate(
            speaker="João Silva",
            raw_text="Lembre-me amanhã de fazer a planilha do bem-estar animal para a auditoria.",
            revised_text="Lembre-me amanhã de fazer a planilha do bem-estar animal para a auditoria.",
            meta_info={"source": "whatsapp", "message_type": "text", "phone": "5544999991234"},
        )
        saved_valid = await memory_repository.save_message(msg_valid, db=db)
        assert saved_valid is not None
        assert saved_valid.id is not None
        assert "planilha" in saved_valid.revised_text
    finally:
        db.close()


def test_analytics_excludes_owner_interactions():
    db = SessionLocal()
    try:
        # Cria mensagens do dono (Bruno) e de interlocutor externo (Carlos)
        msg_owner = MessageRecord(
            id=str(uuid4()),
            created_at=datetime.now(timezone.utc),
            speaker="Bruno",
            raw_text="Mensagem enviada pelo dono do sistema com mais de 15 caracteres.",
            revised_text="Mensagem enviada pelo dono do sistema com mais de 15 caracteres.",
            intent="NOTE",
            sentiment="POSITIVE",
            sentiment_score=0.5,
            meta_info={"fromMe": True, "remoteJid": "554497604925@s.whatsapp.net"},
        )
        msg_external = MessageRecord(
            id=str(uuid4()),
            created_at=datetime.now(timezone.utc),
            speaker="Carlos Diretor",
            raw_text="Relatório de entrega de ração e níveis de silo pronto para envio.",
            revised_text="Relatório de entrega de ração e níveis de silo pronto para envio.",
            intent="DECISION",
            sentiment="POSITIVE",
            sentiment_score=0.8,
            meta_info={"fromMe": False, "remoteJid": "5544988880000@s.whatsapp.net"},
        )
        db.add(msg_owner)
        db.add(msg_external)
        db.commit()

        metrics = analytics_service.get_dashboard_metrics(period="today", db=db)

        # O dashboard não deve contabilizar a mensagem do Bruno nas pessoas em contato ou total
        # Bruno não deve constar na lista de Top Interlocutores
        top_speakers = [s.speaker for s in metrics.top_senders]
        assert "Bruno" not in top_speakers
        assert "user" not in top_speakers
        assert "Carlos Diretor" in top_speakers
    finally:
        db.close()


def test_sentiment_timeline_excludes_owner_and_unregistered_contacts():
    db = SessionLocal()
    try:
        from src.contacts.models import ContactRecord
        # Cadastra apenas Lucas Gerente
        c_lucas = ContactRecord(id="c-lucas-sent", name="Lucas Gerente", phone_number="554499887766", role="EXECUTIVE")
        db.merge(c_lucas)
        db.commit()

        from src.memory.timezone_utils import get_now_brt
        today_str = get_now_brt().strftime("%Y-%m-%d")

        msg_owner = MessageRecord(
            id=str(uuid4()),
            created_at=datetime.now(timezone.utc),
            speaker="Bruno",
            raw_text="Minha própria mensagem",
            revised_text="Minha própria mensagem",
            intent="NOTE",
            sentiment="POSITIVE",
            sentiment_score=0.5,
            meta_info={"fromMe": True},
        )
        msg_contact = MessageRecord(
            id=str(uuid4()),
            created_at=datetime.now(timezone.utc),
            speaker="Lucas Gerente",
            raw_text="Relatório operacional recebido com sucesso.",
            revised_text="Relatório operacional recebido com sucesso.",
            intent="NOTE",
            sentiment="POSITIVE",
            sentiment_score=0.7,
            meta_info={"fromMe": False},
        )
        msg_no_card = MessageRecord(
            id=str(uuid4()),
            created_at=datetime.now(timezone.utc),
            speaker="Desconhecido Sem Card",
            raw_text="Mensagem sem cartão cadastrado.",
            revised_text="Mensagem sem cartão cadastrado.",
            intent="NOTE",
            sentiment="POSITIVE",
            sentiment_score=0.9,
            meta_info={"fromMe": False},
        )
        db.add(msg_owner)
        db.add(msg_contact)
        db.add(msg_no_card)
        db.commit()

        collection = sentiment_timeline_service.collect_daily_sentiments(target_date=today_str, db=db)
        snapshot_speakers = [s.speaker for s in collection.snapshots]

        # Bruno (Dono) e user NÃO devem constar
        assert "Bruno" not in snapshot_speakers
        assert "user" not in snapshot_speakers
        # Interlocutores ativos com falas registradas devem constar
        assert "Lucas Gerente" in snapshot_speakers
        assert "Desconhecido Sem Card" in snapshot_speakers
    finally:
        db.close()


def test_should_analyze_sentiment_by_weight_threshold():
    """Valida que apenas contatos com peso >= 0.70 (ou favoritos) gastam tokens de análise de sentimento."""
    from src.ai_gateway.bypass import should_analyze_sentiment
    from src.contacts.models import ContactRecord
    db = SessionLocal()
    try:
        # 1. Executivo (peso 1.0) -> Deve analisar
        c_exec = ContactRecord(id="c-th-exec", name="Marcos Diretor", phone_number="554499110011", role="EXECUTIVE")
        # 2. Fornecedor sem favorito (peso 0.50) -> Não deve analisar (abaixo de 0.70)
        c_vendor = ContactRecord(id="c-th-vendor", name="Fornecedor Suprimentos", phone_number="554499220022", role="SERVICE_VENDOR", is_favorite=False)
        # 3. Fornecedor Favorito (peso 0.50 * 1.10 = 0.55 -> ainda abaixo de 0.70)
        c_vendor_fav = ContactRecord(id="c-th-vendor-fav", name="Fornecedor Estratégico", phone_number="554499330033", role="SERVICE_VENDOR", is_favorite=True)
        # 4. Colega Favorito (peso 0.70 * 1.10 = 0.77 -> qualificado >= 0.70)
        c_colleague_fav = ContactRecord(id="c-th-colleague", name="Parceiro Inovação", phone_number="554499440044", role="COLLEAGUE", is_favorite=True)

        db.merge(c_exec)
        db.merge(c_vendor)
        db.merge(c_vendor_fav)
        db.merge(c_colleague_fav)
        db.commit()

        # Checagens
        should_exec, reason_exec, w_exec = should_analyze_sentiment("Marcos Diretor", db=db)
        assert should_exec is True
        assert w_exec == 1.00

        should_vendor, reason_vendor, w_vendor = should_analyze_sentiment("Fornecedor Suprimentos", db=db)
        assert should_vendor is False
        assert "below" in reason_vendor
        assert w_vendor == 0.50

        should_colleague, reason_colleague, w_colleague = should_analyze_sentiment("Parceiro Inovação", db=db)
        assert should_colleague is True
        assert w_colleague == 0.77
    finally:
        db.close()
