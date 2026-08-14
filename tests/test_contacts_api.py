"""Testes de integração para os endpoints da API de Contatos."""

import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.memory.database import init_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def test_contacts_api_crud_and_batch():
    # 1. Criação individual
    res_post = client.post(
        "/api/v1/contacts",
        json={
            "phone_number": "44999990000",
            "name": "Diretor Geral",
            "role": "EXECUTIVE",
            "company": "C.Vale",
            "projects": ["Expansão"],
        },
    )
    assert res_post.status_code == 201
    contact_id = res_post.json()["id"]
    assert res_post.json()["effective_weight"] == 1.0

    # 2. Listagem JSON
    res_get = client.get("/api/v1/contacts")
    assert res_get.status_code == 200
    assert any(c["id"] == contact_id for c in res_get.json())

    # 3. Exportação Tabela Markdown
    res_md = client.get("/api/v1/contacts/markdown-table")
    assert res_md.status_code == 200
    assert "| Telefone | Nome | Papel |" in res_md.text
    assert "44999990000" in res_md.text

    # 4. Importação em lote via Tabela Markdown
    batch_md = """
    | Telefone | Nome | Papel | Empresa | Projetos |
    | :--- | :--- | :--- | :--- | :--- |
    | 44988881111 | Maria Esposa | ESPOSA | - | Pessoal |
    | 44977772222 | Lucas Colega | COLEGA | Mtech | TMS |
    """
    res_batch = client.post(
        "/api/v1/contacts/batch-import",
        json={"content": batch_md},
    )
    assert res_batch.status_code == 200
    assert len(res_batch.json()["contacts"]) == 2
    assert res_batch.json()["imported_count"] + res_batch.json()["updated_count"] == 2


    # 5. Atualização PATCH
    res_patch = client.patch(
        f"/api/v1/contacts/{contact_id}",
        json={"nickname": "Chefe", "notes": "Contato prioritário"},
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["nickname"] == "Chefe"

    # 6. Deleção
    res_del = client.delete(f"/api/v1/contacts/{contact_id}")
    assert res_del.status_code == 204
