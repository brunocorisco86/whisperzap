"""Testes unitários para o ContactService e ponderação de prioridade."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.contacts.schemas import ContactCreate, ContactRole
from src.contacts.service import ContactService, calculate_effective_weight
from src.memory.models import Base


@pytest.fixture
def contact_db():
    """Cria banco SQLite em memória isolado para os testes de contatos."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()


def test_effective_weight_calculation():
    c_exec = ContactCreate(phone_number="1", name="Gestor", role=ContactRole.EXECUTIVE)
    assert calculate_effective_weight(c_exec) == 1.00

    c_family = ContactCreate(phone_number="2", name="Esposa", role=ContactRole.FAMILY_CORE)
    assert calculate_effective_weight(c_family) == 0.95

    c_custom = ContactCreate(
        phone_number="3", name="Especial", role=ContactRole.COLLEAGUE, custom_weight=0.88
    )
    assert calculate_effective_weight(c_custom) == 0.88


def test_create_and_list_contacts(contact_db):
    service = ContactService()

    # Cria contato
    c1 = service.create_or_update_contact(
        ContactCreate(
            phone_number="44999991234",
            name="João Silva",
            role=ContactRole.EXECUTIVE,
            company="C.Vale",
            projects=["Silos", "TMS"],
        ),
        db=contact_db,
    )
    assert c1.id is not None
    assert c1.effective_weight == 1.00

    # Lista
    all_contacts = service.list_contacts(db=contact_db)
    assert len(all_contacts) == 1
    assert all_contacts[0].name == "João Silva"

    # Atualiza mesmo telefone
    c1_updated = service.create_or_update_contact(
        ContactCreate(
            phone_number="44999991234",
            name="João Silva Gestor",
            role=ContactRole.EXECUTIVE,
            company="C.Vale Matriz",
            projects=["Silos", "TMS", "Agrocenter"],
        ),
        db=contact_db,
    )
    assert c1_updated.name == "João Silva Gestor"
    assert "Agrocenter" in c1_updated.projects
    assert len(service.list_contacts(db=contact_db)) == 1


def test_batch_import_from_markdown(contact_db):
    service = ContactService()
    md_content = """
    | Telefone | Nome | Papel | Empresa | Projetos |
    | :--- | :--- | :--- | :--- | :--- |
    | 44999991234 | João Silva | GESTOR | C.Vale | Silos, TMS |
    | 44988885678 | Dra. Camila | STAKEHOLDER | Consultoria | Sanidade |
    """
    res = service.import_batch_from_text(md_content, db=contact_db)
    assert res.imported_count == 2
    assert len(res.contacts) == 2

    # Exporta de volta para Markdown
    exported_md = service.export_markdown_table(db=contact_db)
    assert "44999991234" in exported_md
    assert "Dra. Camila" in exported_md


def test_calculate_priority_for_message(contact_db):
    service = ContactService()
    # Cadastra um gestor e um fornecedor
    service.create_or_update_contact(
        ContactCreate(phone_number="44999991234", name="João Gestor", role=ContactRole.EXECUTIVE),
        db=contact_db,
    )
    service.create_or_update_contact(
        ContactCreate(phone_number="44911112222", name="Fornecedor X", role=ContactRole.SERVICE_VENDOR),
        db=contact_db,
    )

    # Mensagem com urgência MEDIUM vinda do Gestor -> Elevada para HIGH devido ao peso 1.0!
    p1 = service.calculate_priority_for_message("44999991234", raw_urgency="MEDIUM", db=contact_db)
    assert p1 == "HIGH"

    # Mensagem com urgência HIGH vinda do Gestor -> Elevada para URGENT!
    p2 = service.calculate_priority_for_message("João Gestor", raw_urgency="HIGH", db=contact_db)
    assert p2 == "URGENT"

    # Mensagem com urgência MEDIUM vinda do Fornecedor -> Mantém MEDIUM / LOW
    p3 = service.calculate_priority_for_message("44911112222", raw_urgency="MEDIUM", db=contact_db)
    assert p3 in ("MEDIUM", "LOW")
