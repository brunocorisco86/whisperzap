"""Router FastAPI para a Interface Web do Hermes Control Hub & Autenticação."""

import os
import hmac
import hashlib
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Header, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from src.config import settings

router = APIRouter(tags=["Hermes Web Control Hub"])

# Caminhos dos templates e estáticos
WEB_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(WEB_DIR, "templates")
STATIC_DIR = os.path.join(WEB_DIR, "static")


from sqlalchemy.orm import Session
from src.memory.database import get_db
from src.web.security_service import security_service

def generate_auth_token(password: str = "") -> str:
    """Gera token estável de sessão criptográfica de 30 dias."""
    secret = settings.DASHBOARD_SESSION_SECRET or "whisperzap_secret_2026"
    return hmac.new(secret.encode(), b"mnemosine_authenticated_user_session_v1", hashlib.sha256).hexdigest()


def verify_auth_token(token: str) -> bool:
    """Valida se o token fornecido corresponde à sessão ativa ou ao token legado."""
    if not token:
        return False
    secret = settings.DASHBOARD_SESSION_SECRET or "whisperzap_secret_2026"
    stable = generate_auth_token()
    legacy = hmac.new(secret.encode(), settings.DASHBOARD_PASSWORD.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(token, stable) or hmac.compare_digest(token, legacy)


def require_auth(request: Request, x_dashboard_token: str | None = Header(default=None, alias="X-Dashboard-Token")):
    """Dependência para proteger endpoints administrativos."""
    if not settings.DASHBOARD_AUTH_ENABLED:
        return True
    cookie_token = request.cookies.get("whisperzap_session")
    token = x_dashboard_token or cookie_token
    if not token or not verify_auth_token(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticação necessária.")
    return True


class LoginRequest(BaseModel):
    password: str = Field(..., description="Senha de acesso ao dashboard")


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., description="Senha atual")
    new_password: str = Field(..., description="Nova senha desejada")
    confirm_password: str = Field(..., description="Confirmação da nova senha")


class Fido2RegisterVerifyRequest(BaseModel):
    credential_json: str = Field(..., description="JSON de resposta do navigator.credentials.create()")
    device_name: str = Field("Pico Key", description="Rótulo amigável da chave")


class Fido2LoginVerifyRequest(BaseModel):
    credential_json: str = Field(..., description="JSON de resposta do navigator.credentials.get()")


@router.post("/api/auth/login", summary="Autenticação no Dashboard")
@router.post("/mnemosine/api/auth/login", include_in_schema=False)
async def login(req: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """Autentica o usuário e define cookie de sessão de 30 dias."""
    if not settings.DASHBOARD_AUTH_ENABLED:
        return {"authenticated": True, "token": "open", "message": "Autenticação desativada"}

    if security_service.verify_password(req.password, db):
        token = generate_auth_token()
        # Seta cookie persistente por 30 dias (evita digitar senha a cada F5)
        response.set_cookie(
            key="whisperzap_session",
            value=token,
            max_age=30 * 86400,
            httponly=True,
            samesite="lax",
            secure=False,
        )
        return {"authenticated": True, "token": token, "message": "Autenticado com sucesso"}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Senha incorreta.",
    )


@router.get("/api/auth/check", summary="Verifica status da sessão")
@router.get("/mnemosine/api/auth/check", include_in_schema=False)
async def check_auth(
    request: Request,
    x_dashboard_token: str | None = Header(default=None, alias="X-Dashboard-Token"),
):
    """Verifica se o usuário já possui sessão ativa (cookie ou token)."""
    if not settings.DASHBOARD_AUTH_ENABLED:
        return {"authenticated": True, "auth_enabled": False}

    cookie_token = request.cookies.get("whisperzap_session")
    token = x_dashboard_token or cookie_token

    if token and verify_auth_token(token):
        return {"authenticated": True, "auth_enabled": True}

    return {"authenticated": False, "auth_enabled": True}


@router.post("/api/auth/logout", summary="Encerra sessão")
@router.post("/mnemosine/api/auth/logout", include_in_schema=False)
async def logout(response: Response):
    """Remove o cookie de sessão."""
    response.delete_cookie("whisperzap_session")
    return {"authenticated": False, "message": "Sessão encerrada"}


# ===================== ENDPOINTS ADMINISTRATIVOS DE SEGURANÇA =====================

@router.post("/api/auth/password/change", summary="Altera a senha mestra")
@router.post("/mnemosine/api/auth/password/change", include_in_schema=False)
async def change_password(
    req: ChangePasswordRequest,
    db: Session = Depends(get_db),
    _auth=Depends(require_auth),
):
    """Altera a senha mestra do sistema com persistência em banco via PBKDF2."""
    if req.new_password != req.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A confirmação de senha não confere.")

    success, msg = security_service.change_password(
        current_password=req.current_password,
        new_password=req.new_password,
        db=db,
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    return {"success": True, "message": msg}


@router.post("/api/auth/fido2/register/options", summary="Gera opções para registro de chave FIDO2")
@router.post("/mnemosine/api/auth/fido2/register/options", include_in_schema=False)
async def fido2_register_options(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_auth),
):
    """Gera desafio WebAuthn para registrar uma nova chave de hardware (Pico Key, YubiKey)."""
    host = request.headers.get("host")
    options_json = security_service.generate_fido2_registration_options(host_header=host, db=db)
    return Response(content=options_json, media_type="application/json")


@router.post("/api/auth/fido2/register/verify", summary="Valida e salva chave FIDO2")
@router.post("/mnemosine/api/auth/fido2/register/verify", include_in_schema=False)
async def fido2_register_verify(
    req: Fido2RegisterVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_auth),
):
    """Valida a atestação física da chave FIDO2 e salva no banco de dados."""
    host = request.headers.get("host")
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    success, msg = security_service.verify_fido2_registration(
        registration_json=req.credential_json,
        device_name=req.device_name,
        host_header=host,
        scheme=scheme,
        db=db,
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "message": msg}


@router.get("/api/auth/fido2/keys", summary="Lista chaves FIDO2 cadastradas")
@router.get("/mnemosine/api/auth/fido2/keys", include_in_schema=False)
async def fido2_list_keys(
    db: Session = Depends(get_db),
    _auth=Depends(require_auth),
):
    """Retorna lista de chaves FIDO2 ativas para o usuário."""
    return security_service.list_fido2_keys(db=db)


@router.delete("/api/auth/fido2/keys/{key_id}", summary="Remove uma chave FIDO2")
@router.delete("/mnemosine/api/auth/fido2/keys/{key_id}", include_in_schema=False)
async def fido2_delete_key(
    key_id: str,
    db: Session = Depends(get_db),
    _auth=Depends(require_auth),
):
    """Exclui uma chave FIDO2."""
    if security_service.delete_fido2_key(key_id=key_id, db=db):
        return {"success": True, "message": "Chave excluída com sucesso."}
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chave não encontrada.")


@router.post("/api/auth/fido2/login/options", summary="Gera desafio para login com chave FIDO2")
@router.post("/mnemosine/api/auth/fido2/login/options", include_in_schema=False)
async def fido2_login_options(
    request: Request,
    db: Session = Depends(get_db),
):
    """Gera desafio público WebAuthn para autenticação via Pico Key / YubiKey."""
    host = request.headers.get("host")
    options_json = security_service.generate_fido2_authentication_options(host_header=host, db=db)
    return Response(content=options_json, media_type="application/json")


@router.post("/api/auth/fido2/login/verify", summary="Valida chave FIDO2 e efetua login")
@router.post("/mnemosine/api/auth/fido2/login/verify", include_in_schema=False)
async def fido2_login_verify(
    req: Fido2LoginVerifyRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Valida a assinatura da chave de hardware e emite o cookie de sessão."""
    host = request.headers.get("host")
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    success, msg = security_service.verify_fido2_authentication(
        authentication_json=req.credential_json,
        host_header=host,
        scheme=scheme,
        db=db,
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=msg)

    token = generate_auth_token()
    response.set_cookie(
        key="whisperzap_session",
        value=token,
        max_age=30 * 86400,
        httponly=True,
        samesite="lax",
        secure=False,
    )
    return {"authenticated": True, "token": token, "message": msg}


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
@router.get("/mnemosine", response_class=HTMLResponse, include_in_schema=False)
@router.get("/mnemosine/", response_class=HTMLResponse, include_in_schema=False)
@router.get("/mnemosine/ui", response_class=HTMLResponse, include_in_schema=False)
async def serve_dashboard():
    """Entrega o painel de controle executivo Hermes Control Hub."""
    index_file = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Hermes Control Hub: Carregando...</h1>")


@router.get("/whatsapp-qr", response_class=HTMLResponse, summary="Página de Pareamento do WhatsApp")
@router.get("/whatsapp-connect", response_class=HTMLResponse, include_in_schema=False)
@router.get("/mnemosine/whatsapp-qr", response_class=HTMLResponse, include_in_schema=False)
@router.get("/mnemosine/whatsapp-connect", response_class=HTMLResponse, include_in_schema=False)
async def serve_whatsapp_qr():
    """Entrega a interface visual de pareamento e monitoramento do WhatsApp na Evolution API."""
    qr_file = os.path.join(TEMPLATES_DIR, "whatsapp_qr.html")
    if os.path.exists(qr_file):
        with open(qr_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Carregando QR Code...</h1>")


@router.get("/api/whatsapp/status", summary="Status e QR Code do WhatsApp em Tempo Real")
@router.get("/mnemosine/api/whatsapp/status", include_in_schema=False)
async def get_whatsapp_status():
    """Consulta a Evolution API e retorna o estado de conexão e base64 do QR Code."""
    instance = settings.EVOLUTION_INSTANCE
    api_url = settings.EVOLUTION_API_URL.rstrip("/")
    api_key = settings.EVOLUTION_API_KEY

    headers = {"apikey": api_key, "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            # 1. Tenta buscar o estado da conexão
            state_resp = await client.get(f"{api_url}/instance/connectionState/{instance}", headers=headers)
            state_data = state_resp.json() if state_resp.status_code == 200 else {}
            state = (state_data.get("instance") or {}).get("state", "connecting")

            if state == "open":
                # Busca detalhes da instância conectada
                fetch_resp = await client.get(f"{api_url}/instance/fetchInstances", headers=headers)
                instances = fetch_resp.json() if fetch_resp.status_code == 200 else []
                curr = next((i for i in instances if i.get("name") == instance), {})
                return {
                    "state": "open",
                    "instance": instance,
                    "profileName": curr.get("profileName") or settings.USER_NAME,
                    "ownerJid": curr.get("ownerJid"),
                    "number": curr.get("number") or settings.USER_PHONE_NUMBER,
                }

            # 2. Se não estiver aberto, busca o QR Code
            qr_resp = await client.get(f"{api_url}/instance/connect/{instance}", headers=headers)
            qr_data = qr_resp.json() if qr_resp.status_code == 200 else {}

            base64_str = qr_data.get("base64") or (qr_data.get("qrcode") or {}).get("base64") or ""
            return {
                "state": "connecting",
                "instance": instance,
                "base64": base64_str,
                "count": qr_data.get("count", 0),
            }
    except Exception as e:
        return {
            "state": "connecting",
            "instance": instance,
            "error": str(e),
            "base64": "",
        }
