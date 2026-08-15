from contextlib import asynccontextmanager
from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from src.config import settings
from src.ai_gateway.router import router as ai_router
from src.transcriber.router import router as transcriber_router
from src.dictionary.router import router as dictionary_router
from src.memory.router import router as memory_router
from src.contacts.router import router as contacts_router
from src.analytics.router import router as analytics_router
from src.web.router import router as web_router, STATIC_DIR
from src.memory.database import init_db
from src.scheduler.cron_service import start_scheduler, stop_scheduler
from fastapi.staticfiles import StaticFiles
import os


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Executa a inicialização do banco de dados e rotinas de agendamento em background."""
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description="Hermes Voice Memory — Transformando comunicação não estruturada em memória e inteligência.",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# Configuração de CORS para requisições do n8n / frontend / webhooks
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Monta arquivos estáticos do frontend web
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Inclusão dos roteadores de microsserviços
app.include_router(web_router)
app.include_router(transcriber_router)
app.include_router(ai_router)
app.include_router(dictionary_router)
app.include_router(memory_router)
app.include_router(contacts_router)
app.include_router(analytics_router)




@app.get(
    "/health",
    status_code=status.HTTP_200_OK,
    tags=["Health"],
    summary="Verificação de integridade da API",
)
async def health_check():
    """Retorna o status de saúde da aplicação e configurações ativas."""
    return {
        "status": "healthy",
        "version": settings.API_VERSION,
        "environment": settings.ENVIRONMENT,
        "ai_provider": settings.AI_PROVIDER,
        "whisper_model": settings.WHISPER_MODEL,
        "whisper_device": settings.WHISPER_DEVICE,
    }


@app.get(
    "/whatsapp-qr",
    response_class=Response,
    tags=["WhatsApp"],
    summary="Exibe QR Code do WhatsApp para pareamento com celular",
)
async def whatsapp_qr_page():
    """Gera página HTML com o QR Code ao vivo da Evolution API para escanear no celular."""
    import urllib.request
    import json

    token = settings.WHATSAPP_API_TOKEN or "seu_token_whatsapp_aqui"
    req = urllib.request.Request(
        "http://localhost:8080/instance/connect/hermes",
        headers={"apikey": token},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            b64 = data.get("base64", "")
            if b64:
                img_tag = f'<img src="{b64}" style="border: 8px solid white; border-radius: 12px; width: 320px; height: 320px; box-shadow: 0 10px 30px rgba(0,0,0,0.5);" />'
            else:
                img_tag = '<p style="color:#4ade80;font-size:18px;font-weight:bold;">✅ WhatsApp já conectado com sucesso!</p>'
    except Exception as e:
        img_tag = f'<p style="color:#f87171;">⚠️ Não foi possível carregar o QR Code: {e}</p>'

    html = f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hermes — Conectar WhatsApp</title>
    <style>
        body {{
            margin: 0;
            padding: 0;
            background: linear-gradient(135deg, #0f172a, #1e293b);
            color: #f8fafc;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
        }}
        .card {{
            background: #1e293b;
            border: 1px solid #334155;
            padding: 40px;
            border-radius: 20px;
            text-align: center;
            max-width: 440px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
        }}
        h1 {{ font-size: 24px; margin-bottom: 8px; color: #38bdf8; }}
        p {{ font-size: 15px; color: #94a3b8; line-height: 1.5; margin-bottom: 24px; }}
        .step {{ background: #0f172a; padding: 12px 16px; border-radius: 8px; font-size: 13px; color: #cbd5e1; margin-bottom: 20px; text-align: left; }}
        .footer {{ font-size: 12px; color: #64748b; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>📱 Parear WhatsApp com o Hermes</h1>
        <div class="step">
            1. Abra o WhatsApp no celular<br>
            2. Toque em <b>Menu / Configurações</b> ➔ <b>Aparelhos Conectados</b><br>
            3. Toque em <b>Conectar Aparelho</b> e aponte a câmera
        </div>
        {img_tag}
        <div class="footer">Instância: hermes | Evolution API v2</div>
    </div>
</body>
</html>"""
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)

