from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from src.config import settings
from src.ai_gateway.router import router as ai_router
from src.transcriber.router import router as transcriber_router
from src.dictionary.router import router as dictionary_router
from src.memory.router import router as memory_router
from src.contacts.router import router as contacts_router
from src.memory.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Executa a inicialização do banco de dados na partida."""
    init_db()
    yield


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

# Inclusão dos roteadores de microsserviços
app.include_router(transcriber_router)
app.include_router(ai_router)
app.include_router(dictionary_router)
app.include_router(memory_router)
app.include_router(contacts_router)




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
