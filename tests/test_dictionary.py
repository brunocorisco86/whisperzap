"""Testes unitários para o Dicionário Léxico e Glossário de Domínio."""

import pytest
from src.dictionary.schemas import DictionaryTermCreate
from src.dictionary.service import DictionaryService


@pytest.fixture
def temp_dict_service(tmp_path):
    """Cria uma instância temporária do DictionaryService isolada para testes."""
    temp_file = str(tmp_path / "test_dictionary.json")
    return DictionaryService(persistence_path=temp_file)


def test_default_terms_loaded(temp_dict_service):
    """Verifica se os termos padrão (FAL, eProdutor, C.Vale, etc.) são inicializados."""
    terms = temp_dict_service.list_terms()
    assert len(terms) >= 5
    term_names = [t.term for t in terms]
    assert "FAL" in term_names
    assert "C.Vale" in term_names
    assert "eProdutor" in term_names


def test_add_and_list_term(temp_dict_service):
    """Testa a adição de um novo termo e filtragem por categoria."""
    new_term_data = DictionaryTermCreate(
        term="Aviário Dark House",
        phonetic_variations=["dark house", "aviario dark", "darkhouse"],
        expansion="Aviário Climatizado com Pressão Negativa e Vedação de Luz",
        category="EQUIPAMENTOS",
        description="Estrutura de alta tecnologia para controle de ambiência.",
    )
    created = temp_dict_service.add_term(new_term_data)
    assert created.id is not None
    assert created.term == "Aviário Dark House"

    # Filtra por categoria
    equip_terms = temp_dict_service.list_terms(category="EQUIPAMENTOS")
    assert any(t.term == "Aviário Dark House" for t in equip_terms)


def test_delete_term(temp_dict_service):
    """Testa a remoção de termos."""
    new_term = temp_dict_service.add_term(DictionaryTermCreate(term="TermoParaDeletar"))
    assert temp_dict_service.get_term(new_term.id) is not None

    deleted = temp_dict_service.delete_term(new_term.id)
    assert deleted is True
    assert temp_dict_service.get_term(new_term.id) is None


def test_hints_generation(temp_dict_service):
    """Testa a geração de strings de hints para Whisper e prompts LLM."""
    initial_prompt = temp_dict_service.get_whisper_initial_prompt()
    assert "FAL" in initial_prompt
    assert "C.Vale" in initial_prompt

    context_hint = temp_dict_service.get_prompt_context_hint()
    assert "### Glossário de Termos e Jargões do Domínio:" in context_hint
    assert "Ficha de Acompanhamento de Lote" in context_hint


def test_apply_lexical_corrections(temp_dict_service):
    """Testa a correção léxica determinística de variações fonéticas."""
    raw_text = "hoje na Sevale precisamos preencher a FAU do lote"
    corrected = temp_dict_service.apply_lexical_corrections(raw_text)
    assert "C.Vale" in corrected or "FAL" in corrected


def test_merge_similar_terms_with_spacy(temp_dict_service):
    """Testa a mesclagem autônoma de termos semelhantes, plurais e variações com spaCy."""
    # Adiciona termos semelhantes / flexionados
    temp_dict_service.add_term(DictionaryTermCreate(
        term="Clorador",
        phonetic_variations=["clorador de agua"],
        category="EQUIPAMENTOS",
        description="Equipamento de cloração da água dos aviários",
    ))
    temp_dict_service.add_term(DictionaryTermCreate(
        term="cloradores",
        phonetic_variations=["cloradoris"],
        category="EQUIPAMENTOS",
    ))

    clusters = temp_dict_service.merge_similar_terms(similarity_threshold=0.80)
    assert len(clusters) >= 1
    cluster = next(c for c in clusters if "clorador" in c["canonical_term"].lower())
    assert "cloradores" in cluster["merged_terms"] or "Clorador" == cluster["canonical_term"]

    # Termos restantes no dicionário
    term_names = [t.term for t in temp_dict_service.list_terms()]
    assert "Clorador" in term_names or "clorador" in term_names
    # O plural não deve ser um termo isolado, mas sim incorporado nas variações
    canonical_term = next(t for t in temp_dict_service.list_terms() if t.term.lower() == "clorador")
    assert any("cloradores" in v.lower() for v in canonical_term.phonetic_variations)


def test_dictionary_merge_api_endpoint():
    """Testa o endpoint POST /api/v1/dictionary/merge-similar."""
    from fastapi.testclient import TestClient
    from src.main import app

    client = TestClient(app)
    res = client.post("/api/v1/dictionary/merge-similar")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "merged_terms_count" in data
    assert "merged_clusters_count" in data
    assert "clusters" in data
    assert "message" in data
