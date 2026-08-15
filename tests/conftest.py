"""
Fixtures globais para a suite de testes do Hermes Voice Memory.
Garante o isolamento total do banco de dados e do grafo durante os testes.
"""
import os
import shutil
import tempfile
from pathlib import Path
import pytest


@pytest.fixture(scope="session", autouse=True)
def isolate_test_environment(tmp_path_factory):
    """Cria ambiente de banco e grafo temporário isolado para a sessão de testes do pytest."""
    temp_dir = tmp_path_factory.mktemp("hermes_test_data")
    temp_db_path = temp_dir / "hermes_test.db"
    temp_graph_path = temp_dir / "hermes_test_graph.json"

    # Define variáveis de ambiente e reconfigura o engine do banco para o banco temporário
    test_db_url = f"sqlite:///{temp_db_path}"
    os.environ["DATABASE_URL"] = test_db_url
    os.environ["GRAPH_STORAGE_PATH"] = str(temp_graph_path)

    from src.memory.database import init_db, set_database_url
    set_database_url(test_db_url)
    init_db()

    yield

    # Limpeza após os testes
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass


@pytest.fixture
def project_root() -> Path:
    """Retorna o caminho raiz do projeto."""
    return Path(__file__).parent.parent


@pytest.fixture
def env_example_path(project_root: Path) -> Path:
    """Retorna o caminho do arquivo .env.example."""
    return project_root / ".env.example"

