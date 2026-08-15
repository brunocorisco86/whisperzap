"""Testes de validação dos manifestos e infraestrutura de produção (Fase 6)."""

import os
from pathlib import Path
import pytest


def test_dockerfile_structure():
    """Valida se o Dockerfile possui configurações de segurança, multi-stage e ffmpeg."""
    root_dir = Path(__file__).parent.parent
    dockerfile = root_dir / "Dockerfile"

    assert dockerfile.exists(), "Dockerfile não encontrado"
    content = dockerfile.read_text(encoding="utf-8")

    assert "FROM python:3.12-slim" in content
    assert "ffmpeg" in content
    assert "USER hermes" in content
    assert "EXPOSE 8000" in content
    assert "HEALTHCHECK" in content
    assert "uvicorn" in content


def test_docker_compose_structure():
    """Valida se o docker-compose.yml contém os 3 serviços essenciais e volumes persistentes."""
    root_dir = Path(__file__).parent.parent
    compose_file = root_dir / "docker-compose.yml"

    assert compose_file.exists(), "docker-compose.yml não encontrado"
    content = compose_file.read_text(encoding="utf-8")

    assert "hermes-db:" in content
    assert "pgvector/pgvector:pg16" in content
    assert "hermes-api:" in content
    assert "caddy:" in content
    assert "postgres_data:" in content
    assert "hermes_data:" in content
    assert "hermes-network" in content


def test_caddyfile_structure():
    """Valida se o Caddyfile está configurado para proxy reverso da API com cabeçalhos de segurança."""
    root_dir = Path(__file__).parent.parent
    caddyfile = root_dir / "Caddyfile"

    assert caddyfile.exists(), "Caddyfile não encontrado"
    content = caddyfile.read_text(encoding="utf-8")

    assert "reverse_proxy hermes-api:8000" in content
    assert "X-Frame-Options" in content
    assert "Strict-Transport-Security" in content
    assert "encode zstd gzip" in content


def test_dockerignore_structure():
    """Valida se o .dockerignore exclui arquivos sensíveis e pastas de ambiente virtual."""
    root_dir = Path(__file__).parent.parent
    dockerignore = root_dir / ".dockerignore"

    assert dockerignore.exists(), ".dockerignore não encontrado"
    content = dockerignore.read_text(encoding="utf-8")

    assert ".venv" in content
    assert ".git" in content
    assert ".env" in content
    assert "__pycache__" in content


def test_scripts_are_executable():
    """Valida se todos os scripts operacionais existem e têm permissão de execução."""
    root_dir = Path(__file__).parent.parent
    scripts_dir = root_dir / "scripts"

    assert scripts_dir.exists(), "Pasta scripts/ não encontrada"

    required_scripts = ["deploy_vps_alpine.sh", "backup_db.sh", "health_check_prod.sh"]
    for script_name in required_scripts:
        script_path = scripts_dir / script_name
        assert script_path.exists(), f"Script {script_name} não encontrado"
        assert os.access(script_path, os.X_OK), f"Script {script_name} deve possuir permissão de execução"
