"""Testes unitários para o Parser Polimórfico de Contatos (Markdown Table e JSON)."""

from src.contacts.parser import (
    clean_phone_number,
    contacts_to_markdown_table,
    normalize_role,
    parse_contact_batch,
    parse_json_array,
    parse_markdown_table,
)
from src.contacts.schemas import ContactCreate, ContactRole


def test_clean_phone_number():
    assert clean_phone_number("(44) 99999-1234") == "44999991234"
    assert clean_phone_number("+55 44 98888-5678") == "5544988885678"
    assert clean_phone_number("44999991234") == "44999991234"


def test_normalize_role():
    assert normalize_role("GESTOR") == ContactRole.EXECUTIVE
    assert normalize_role("diretor") == ContactRole.EXECUTIVE
    assert normalize_role("Esposa") == ContactRole.FAMILY_CORE
    assert normalize_role("Mãe") == ContactRole.FAMILY_CORE
    assert normalize_role("STAKEHOLDER") == ContactRole.STAKEHOLDER
    assert normalize_role("fornecedor") == ContactRole.SERVICE_VENDOR
    assert normalize_role("qualquer_coisa") == ContactRole.UNKNOWN


def test_parse_markdown_table():
    md_sample = """
    | Telefone | Nome | Papel | Empresa | Projetos |
    | :--- | :--- | :--- | :--- | :--- |
    | (44) 99999-1234 | João Silva | GESTOR | C.Vale | Silos, TMS |
    | 44988885678 | Dra. Camila | STAKEHOLDER | Consultoria | Sanidade Lote |
    | 44977771122 | Maria | ESPOSA | Família | Pessoal |
    """
    contacts = parse_markdown_table(md_sample)
    assert len(contacts) == 3

    c1 = contacts[0]
    assert c1.phone_number == "44999991234"
    assert c1.name == "João Silva"
    assert c1.role == ContactRole.EXECUTIVE
    assert c1.company == "C.Vale"
    assert "Silos" in c1.projects
    assert "TMS" in c1.projects

    c3 = contacts[2]
    assert c3.role == ContactRole.FAMILY_CORE


def test_parse_json_array():
    json_sample = """
    [
      {
        "phone_number": "44999991234",
        "name": "João Silva",
        "role": "EXECUTIVE",
        "company": "C.Vale",
        "projects": ["Silos", "TMS"]
      }
    ]
    """
    contacts = parse_json_array(json_sample)
    assert len(contacts) == 1
    assert contacts[0].name == "João Silva"
    assert contacts[0].role == ContactRole.EXECUTIVE


def test_parse_contact_batch_auto_detection():
    # Markdown
    md_text = "| Telefone | Nome | Papel |\n| 44999991234 | Carlos | COLEGA |"
    md_res = parse_contact_batch(md_text)
    assert len(md_res) == 1
    assert md_res[0].role == ContactRole.COLLEAGUE

    # JSON
    js_text = '[{"phone": "44988887777", "name": "Ana", "role": "FAMILY_CORE"}]'
    js_res = parse_contact_batch(js_text)
    assert len(js_res) == 1
    assert js_res[0].name == "Ana"
    assert js_res[0].role == ContactRole.FAMILY_CORE


def test_contacts_to_markdown_table():
    sample_list = [
        ContactCreate(
            phone_number="44999991234",
            name="João Silva",
            role=ContactRole.EXECUTIVE,
            company="C.Vale",
            projects=["Silos", "TMS"],
        )
    ]
    table_str = contacts_to_markdown_table(sample_list)
    assert "| Telefone | Nome | Papel | Empresa | Projetos |" in table_str
    assert "44999991234" in table_str
    assert "João Silva" in table_str
    assert "EXECUTIVE" in table_str


def test_parse_vcard_text():
    vcard_sample = """BEGIN:VCARD
VERSION:3.0
FN:Carlos Eduardo Gerente
N:Gerente;Carlos;Eduardo;;
ORG:Agro Cooperativa
item1.TEL:044 99916-2543
item1.X-ABLabel:
item2.EMAIL;TYPE=INTERNET:carlos@agro.com
CATEGORIES:Trabalho,myContacts
NOTE:Responsável pelo setor de insumos
PHOTO:https://lh3.googleusercontent.com/contacts/sample_avatar
END:VCARD
BEGIN:VCARD
VERSION:3.0
ORG:Fast Burger Palotina
TEL;TYPE=CELL:+55 44 99970-6727
END:VCARD"""

    contacts = parse_contact_batch(vcard_sample)
    assert len(contacts) == 2

    # Contato 1
    c1 = contacts[0]
    assert c1.name == "Carlos Eduardo Gerente"
    assert c1.phone_number == "5544999162543"
    assert c1.company == "Agro Cooperativa"
    assert "carlos@agro.com" in c1.notes
    assert "Trabalho" in c1.notes
    assert "Responsável pelo setor de insumos" in c1.notes

    # Contato 2 (sem FN, usando ORG como nome e normalizando +55)
    c2 = contacts[1]
    assert c2.name == "Fast Burger Palotina"
    assert c2.phone_number == "5544999706727"

