"""
Fixtures globais para a suite de testes do Hermes Voice Memory.
"""
from pathlib import Path
import pytest


@pytest.fixture
def project_root() -> Path:
    """Retorna o caminho raiz do projeto."""
    return Path(__file__).parent.parent


@pytest.fixture
def env_example_path(project_root: Path) -> Path:
    """Retorna o caminho do arquivo .env.example."""
    return project_root / ".env.example"
