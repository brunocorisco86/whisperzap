"""Router FastAPI para a Interface Web do Hermes Control Hub & Autenticação."""

import os
import hmac
import hashlib
import httpx
from fastapi import APIRouter, HTTPException, Request, Response, Header, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from src.config import settings

router = APIRouter(tags=["Hermes Web Control Hub"])

# Caminhos dos templates e estáticos
WEB_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(WEB_DIR, "templates")
STATIC_DIR = os.path.join(WEB_DIR, "static")


def generate_auth_token(password: str) -> str:
    """Gera token seguro baseado na senha e segredo da sessão."""
    secret = settings.DASHBOARD_SESSION_SECRET or "whisperzap_secret_2026"
    return hmac.new(secret.encode(), password.encode(), hashlib.sha256).hexdigest()


def verify_auth_token(token: str) -> bool:
    """Valida se o token fornecido corresponde à senha configurada."""
    expected = generate_auth_token(settings.DASHBOARD_PASSWORD)
    return hmac.compare_digest(token, expected)


class LoginRequest(BaseModel):
    password: str = Field(..., description="Senha de acesso ao dashboard")


@router.post("/api/auth/login", summary="Autenticação no Dashboard")
async def login(req: LoginRequest, response: Response):
    """Autentica o usuário e define cookie de sessão de 30 dias."""
    if not settings.DASHBOARD_AUTH_ENABLED:
        return {"authenticated": True, "token": "open", "message": "Autenticação desativada"}

    if req.password == settings.DASHBOARD_PASSWORD:
        token = generate_auth_token(req.password)
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
async def logout(response: Response):
    """Remove o cookie de sessão."""
    response.delete_cookie("whisperzap_session")
    return {"authenticated": False, "message": "Sessão encerrada"}


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
async def serve_dashboard():
    """Entrega o painel de controle executivo Hermes Control Hub."""
    index_file = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Hermes Control Hub: Carregando...</h1>")


@router.get("/whatsapp-qr", response_class=HTMLResponse, summary="Página de Pareamento do WhatsApp")
@router.get("/whatsapp-connect", response_class=HTMLResponse, include_in_schema=False)
async def serve_whatsapp_qr():
    """Entrega a interface visual de pareamento e monitoramento do WhatsApp na Evolution API."""
    qr_file = os.path.join(TEMPLATES_DIR, "whatsapp_qr.html")
    if os.path.exists(qr_file):
        with open(qr_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Carregando QR Code...</h1>")


@router.get("/api/whatsapp/status", summary="Status e QR Code do WhatsApp em Tempo Real")
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
