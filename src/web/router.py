"""Router FastAPI para a Interface Web do Hermes Control Hub & Autenticação."""

import os
import hmac
import hashlib
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
