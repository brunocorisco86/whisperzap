"""Router FastAPI para o Dicionário Léxico e Glossário Hermes."""

from fastapi import APIRouter, HTTPException, Query, status
from src.dictionary.schemas import (
    DictionaryHintResponse,
    DictionaryTerm,
    DictionaryTermCreate,
)
from src.dictionary.service import dictionary_service

router = APIRouter(prefix="/api/v1/dictionary", tags=["Dicionário Léxico & Glossário"])


@router.get("", response_model=list[DictionaryTerm])
async def list_terms(category: str | None = Query(default=None, description="Filtrar por categoria")):
    """Lista todos os termos cadastrados no glossário de domínio."""
    return dictionary_service.list_terms(category=category)


@router.post("", response_model=DictionaryTerm, status_code=status.HTTP_201_CREATED)
async def create_term(payload: DictionaryTermCreate):
    """Cadastra ou atualiza um termo no dicionário léxico."""
    return dictionary_service.add_term(payload)


@router.delete("/{term_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_term(term_id: str):
    """Remove um termo do dicionário."""
    success = dictionary_service.delete_term(term_id)
    if not success:
        raise HTTPException(status_code=404, detail="Termo não encontrado")
    return None


@router.get("/hints", response_model=DictionaryHintResponse)
async def get_dictionary_hints():
    """Retorna os prompts contextuais e vocabulário inicial para Whisper e LLMs."""
    terms = dictionary_service.list_terms()
    return DictionaryHintResponse(
        whisper_initial_prompt=dictionary_service.get_whisper_initial_prompt(),
        prompt_context_hint=dictionary_service.get_prompt_context_hint(),
        total_terms=len(terms),
    )
