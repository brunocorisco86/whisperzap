"""
Testes de integridade do ambiente e estrutura inicial do Hermes Voice Memory.
"""
from pathlib import Path
import pytest


@pytest.mark.environment
def test_documentation_files_exist(project_root: Path):
    """Verifica se a documentação básica e estrutural do projeto existe."""
    required_docs = [
        "README.md",
        "ROADMAP.md",
        "LOGS.md",
        "docs/architecture.md",
        "docs/graphify_guide.md",
        "docs/subagents/README.md",
    ]
    for doc in required_docs:
        doc_path = project_root / doc
        assert doc_path.exists(), f"O arquivo de documentação '{doc}' não foi encontrado."


@pytest.mark.environment
def test_subagent_files_exist(project_root: Path):
    """Verifica se todos os 6 subagentes especialistas possuem especificação."""
    subagents = [
        "arch_specialist.md",
        "cicd_specialist.md",
        "cybersec_specialist.md",
        "hermes_agent_specialist.md",
        "vps_alpine_specialist.md",
        "api_stack_specialist.md",
    ]
    subagent_dir = project_root / "docs" / "subagents"
    for sa in subagents:
        sa_path = subagent_dir / sa
        assert sa_path.exists(), f"O subagente '{sa}' não foi encontrado em docs/subagents."


@pytest.mark.environment
def test_env_example_contains_key_variables(env_example_path: Path):
    """Valida se o .env.example contém todas as chaves essenciais para a aplicação."""
    assert env_example_path.exists(), "O arquivo .env.example deve existir."
    content = env_example_path.read_text(encoding="utf-8")
    
    required_keys = [
        "AI_PROVIDER",
        "GEMINI_API_KEY",
        "WHISPER_MODEL",
        "POSTGRES_DB",
        "N8N_WEBHOOK_URL",
        "GRAPHIFY_GEMINI_MODEL",
    ]
    for key in required_keys:
        assert key in content, f"A variável chave '{key}' não está presente no .env.example."


@pytest.mark.environment
def test_gitignore_contains_sensitive_entries(project_root: Path):
    """Verifica se o .gitignore possui as proteções essenciais ativadas."""
    gitignore_path = project_root / ".gitignore"
    assert gitignore_path.exists(), "O arquivo .gitignore não foi encontrado."
    content = gitignore_path.read_text(encoding="utf-8")
    
    protected_entries = [".env", "graphify-out/", "__pycache__/"]
    for entry in protected_entries:
        assert entry in content, f"O elemento de segurança '{entry}' deve constar no .gitignore."


@pytest.mark.environment
def test_requirements_contains_essential_packages(project_root: Path):
    """Verifica se o requirements.txt especifica as bibliotecas da stack."""
    req_path = project_root / "requirements.txt"
    assert req_path.exists(), "O arquivo requirements.txt deve existir."
    content = req_path.read_text(encoding="utf-8")
    
    core_packages = ["fastapi", "pytest", "graphifyy", "networkx", "pgvector"]
    for pkg in core_packages:
        assert pkg in content, f"A biblioteca '{pkg}' é necessária no requirements.txt."
