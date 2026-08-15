"""Testes de integridade e sintaxe dos arquivos de workflow n8n."""

import json
from pathlib import Path
import pytest


def test_all_workflows_are_valid_json():
    """Valida se todos os arquivos .json na pasta workflows/ são JSONs válidos com nós e conexões."""
    workflows_dir = Path(__file__).parent.parent / "workflows"
    assert workflows_dir.exists(), "Diretório workflows/ não encontrado"

    json_files = list(workflows_dir.glob("*.json"))
    assert len(json_files) >= 4, f"Esperado pelo menos 4 workflows, encontrados {len(json_files)}"

    for jf in json_files:
        with open(jf, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "name" in data, f"Workflow {jf.name} deve possuir 'name'"
        assert "nodes" in data, f"Workflow {jf.name} deve possuir lista de 'nodes'"
        assert "connections" in data, f"Workflow {jf.name} deve possuir 'connections'"
        assert len(data["nodes"]) > 0, f"Workflow {jf.name} deve conter pelo menos 1 nó"
