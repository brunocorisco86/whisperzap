"""Testes automatizados para Central de Segurança, Troca de Senha e FIDO2 / WebAuthn."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.main import app
from src.config import settings
from src.memory.models import Base, AdminSettingRecord, Fido2CredentialRecord
from src.memory.database import get_db
from src.web.security_service import security_service

# Engine SQLite em memória para testes isolados (com StaticPool para persistência na mesma memória)
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)


def test_password_default_and_change_workflow():
    db = TestingSessionLocal()
    try:
        # 1. Verifica senha padrão
        assert security_service.verify_password(settings.DASHBOARD_PASSWORD, db) is True
        assert security_service.verify_password("senha_errada_123", db) is False

        # 2. Tenta trocar com senha atual incorreta
        ok, msg = security_service.change_password("senha_errada", "nova_senha_forte", db)
        assert ok is False
        assert "Senha atual incorreta" in msg

        # 3. Troca com sucesso
        ok, msg = security_service.change_password(settings.DASHBOARD_PASSWORD, "minha_nova_senha_2026", db)
        assert ok is True

        # 4. Antiga senha não funciona mais
        assert security_service.verify_password(settings.DASHBOARD_PASSWORD, db) is False

        # 5. Nova senha funciona
        assert security_service.verify_password("minha_nova_senha_2026", db) is True
    finally:
        db.close()


def test_api_change_password_endpoint():
    db = TestingSessionLocal()
    try:
        # Autentica e pega cookie
        login_res = client.post("/api/auth/login", json={"password": settings.DASHBOARD_PASSWORD})
        assert login_res.status_code == 200
        cookie = login_res.cookies.get("whisperzap_session")

        # Troca de senha via API
        change_res = client.post(
            "/api/auth/password/change",
            json={
                "current_password": settings.DASHBOARD_PASSWORD,
                "new_password": "senha_alterada_api_123",
                "confirm_password": "senha_alterada_api_123",
            },
            cookies={"whisperzap_session": cookie},
        )
        assert change_res.status_code == 200
        assert change_res.json()["success"] is True

        # Tenta login com a nova senha
        new_login = client.post("/api/auth/login", json={"password": "senha_alterada_api_123"})
        assert new_login.status_code == 200
        assert new_login.json()["authenticated"] is True
    finally:
        db.close()


def test_fido2_options_generation():
    db = TestingSessionLocal()
    try:
        # Gera opções de registro
        reg_options_json = security_service.generate_fido2_registration_options(
            host_header="brunoconter.duckdns.org",
            db=db,
        )
        assert "challenge" in reg_options_json
        assert "rp" in reg_options_json
        assert "brunoconter.duckdns.org" in reg_options_json

        # Gera opções de login
        auth_options_json = security_service.generate_fido2_authentication_options(
            host_header="brunoconter.duckdns.org",
            db=db,
        )
        assert "challenge" in auth_options_json
        assert "rpId" in auth_options_json
    finally:
        db.close()


def test_fido2_keys_management_api():
    db = TestingSessionLocal()
    try:
        # Insere chave mockada diretamente no banco
        key_mock = Fido2CredentialRecord(
            id="mock_credential_id_12345",
            public_key="mock_public_key_67890",
            sign_count=1,
            device_name="Pico Key de Teste",
        )
        db.add(key_mock)
        db.commit()

        # Login para obter sessão
        login_res = client.post("/api/auth/login", json={"password": settings.DASHBOARD_PASSWORD})
        cookie = login_res.cookies.get("whisperzap_session")

        # Lista chaves
        list_res = client.get("/api/auth/fido2/keys", cookies={"whisperzap_session": cookie})
        assert list_res.status_code == 200
        keys = list_res.json()
        assert len(keys) == 1
        assert keys[0]["device_name"] == "Pico Key de Teste"

        # Exclui chave
        del_res = client.delete("/api/auth/fido2/keys/mock_credential_id_12345", cookies={"whisperzap_session": cookie})
        assert del_res.status_code == 200

        # Lista novamente (deve estar vazia)
        list_res2 = client.get("/api/auth/fido2/keys", cookies={"whisperzap_session": cookie})
        assert len(list_res2.json()) == 0
    finally:
        db.close()


def test_extract_challenge_from_credential():
    import json
    import base64

    # Simula clientDataJSON padrão WebAuthn
    client_data_raw = json.dumps({
        "type": "webauthn.get",
        "challenge": "my_exact_secret_challenge_12345",
        "origin": "https://brunoconter.duckdns.org",
        "crossOrigin": False
    }).encode("utf-8")

    client_data_b64 = base64.urlsafe_b64encode(client_data_raw).decode("ascii").rstrip("=")

    credential_payload = json.dumps({
        "id": "mock_id",
        "rawId": "mock_raw_id",
        "response": {
            "clientDataJSON": client_data_b64,
            "authenticatorData": "mock_auth_data",
            "signature": "mock_sig"
        }
    })

    extracted = security_service._extract_challenge_from_credential(credential_payload)
    assert extracted == "my_exact_secret_challenge_12345"
