"""Testes para a integração de interface e fluxos entre Calíope e Clio."""

import pytest
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def test_dashboard_html_and_assets_served():
    """Verifica que o dashboard HTML e assets estáticos são servidos corretamente."""
    response = client.get("/")
    assert response.status_code == 200
    assert "MNEMOSINE" in response.text
    assert "tab-messages" in response.text
    assert "modal-contact" in response.text

    # Verifica se app.js contém as funções de cadastro de Clio em Calíope
    js_response = client.get("/static/js/app.js")
    assert js_response.status_code == 200
    assert "findContactForMessage" in js_response.text
    assert "openRegisterContactModal" in js_response.text
    assert "btn-clio-register" in js_response.text
    assert "Cadastrar em Clio" in js_response.text

    # Verifica se style.css contém os estilos do botão e badges
    css_response = client.get("/static/css/style.css")
    assert css_response.status_code == 200
    assert ".btn-clio-register" in css_response.text
    assert ".badge-unrecognized" in css_response.text
