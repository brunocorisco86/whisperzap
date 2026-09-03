"""Testes de integração para a Central de Operações de Contatos e Pipeline de Euterpe."""

import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.memory.database import init_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def test_euterpe_vcard_import_endpoint():
    vcard_sample = """BEGIN:VCARD
VERSION:3.0
FN:Produtor Teste Euterpe
TEL;TYPE=CELL:(44) 99123-4567
ORG:C.Vale Cooperativa
NOTE:Cooperado integrado de teste
END:VCARD"""

    # 1. Importação via raw content payload
    res = client.post("/api/v1/contacts/import-vcard", json={"content": vcard_sample})
    assert res.status_code == 200
    data = res.json()
    assert data["total_parsed"] == 1
    assert data["imported_count"] + data["updated_count"] == 1
    assert len(data["details"]) > 0


def test_euterpe_deduplicate_endpoint():
    res = client.post("/api/v1/contacts/deduplicate?dry_run=true")
    assert res.status_code == 200
    data = res.json()
    assert "contacts_merged_count" in data


def test_euterpe_pipeline_endpoint():
    vcard_sample = """BEGIN:VCARD
VERSION:3.0
FN:Veterinario Pipeline Teste
TEL;TYPE=CELL:(44) 99888-7766
ORG:Mtech
NOTE:Consultor zootecnico
END:VCARD"""

    res = client.post("/api/v1/contacts/pipeline", json={"content": vcard_sample})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "import_stats" in data
    assert "dedup_stats" in data
    assert "avatar_stats" in data
    assert len(data["details"]) > 0


def test_euterpe_ui_and_terminal_elements():
    # Verifica index.html
    res_html = client.get("/")
    assert res_html.status_code == 200
    assert "euterpe-environments-panel" in res_html.text
    assert "Evolution API" in res_html.text
    assert ("Webhook Nativo" in res_html.text or "n8n" in res_html.text)
    assert "euterpe-sync-panel" in res_html.text
    assert "btn-euterpe-pipeline" in res_html.text
    assert "euterpe-terminal-logs" in res_html.text
    assert "btn-euterpe-deduplicate" in res_html.text
    assert "btn-euterpe-sync-avatars" in res_html.text

    # Verifica app.js
    res_js = client.get("/static/js/app.js")
    assert res_js.status_code == 200
    assert "logToEuterpeTerminal" in res_js.text
    assert "handleEuterpeFullPipeline" in res_js.text
    assert "handleEuterpeDeduplicate" in res_js.text
    assert "handleEuterpeSyncAvatars" in res_js.text

    # Verifica style.css
    res_css = client.get("/static/css/style.css")
    assert res_css.status_code == 200
    assert ".euterpe-terminal-screen" in res_css.text
    assert ".env-hub-grid" in res_css.text
    assert ".env-card" in res_css.text

