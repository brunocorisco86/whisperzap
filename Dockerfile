# ==============================================================================
# Dockerfile Multi-estágio Otimizado — Hermes Voice Memory API
# ==============================================================================

FROM python:3.12-slim AS builder

WORKDIR /app

# Instala dependências de build do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instala dependências Python em uma pasta de isolamento
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ==============================================================================
# Imagem Final de Execução
# ==============================================================================
FROM python:3.12-slim AS runner

WORKDIR /app

# Instala ffmpeg (necessário para decodificação de áudio OGG/Opus do WhatsApp) e curl (para health check)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Cria usuário não-root para execução segura
RUN useradd -m -u 1000 -s /bin/bash hermes && \
    mkdir -p /app/data /app/assets /home/hermes/.cache && \
    chown -R hermes:hermes /app /home/hermes/.cache

# Copia dependências instaladas pelo builder
COPY --from=builder /root/.local /home/hermes/.local
ENV PATH=/home/hermes/.local/bin:$PATH
ENV PYTHONPATH=/app

# Copia o código da aplicação
COPY --chown=hermes:hermes src /app/src

USER hermes

# Porta exposta da API FastAPI
EXPOSE 8000

# Health check nativo do container
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Comando de inicialização
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
