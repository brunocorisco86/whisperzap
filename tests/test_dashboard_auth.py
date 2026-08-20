"""Testes para o fluxo de autenticação do Dashboard Web."""

import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.config import settings

client = TestClient(app)


def test_auth_check_unauthenticated():
    response = client.get('/api/auth/check')
    assert response.status_code == 200
    data = response.json()
    assert data['authenticated'] is False
    assert data['auth_enabled'] is True


def test_auth_login_invalid_password():
    response = client.post('/api/auth/login', json={'password': 'wrongpassword123'})
    assert response.status_code == 401
    assert 'Senha incorreta' in response.json()['detail']


def test_auth_login_valid_password():
    response = client.post('/api/auth/login', json={'password': settings.DASHBOARD_PASSWORD})
    assert response.status_code == 200
    data = response.json()
    assert data['authenticated'] is True
    assert 'token' in data
    token = data['token']
    assert len(token) > 16

    check_resp = client.get('/api/auth/check', headers={'X-Dashboard-Token': token})
    assert check_resp.status_code == 200
    assert check_resp.json()['authenticated'] is True

    check_cookie_resp = client.get('/api/auth/check', cookies={'whisperzap_session': token})
    assert check_cookie_resp.status_code == 200
    assert check_cookie_resp.json()['authenticated'] is True

    logout_resp = client.post('/api/auth/logout')
    assert logout_resp.status_code == 200
    assert logout_resp.json()['authenticated'] is False
