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
