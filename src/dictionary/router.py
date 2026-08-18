"""Router FastAPI para o Dicionário Léxico, Glossário e Aprendizado Ativo Hermes."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from src.dictionary.harvester import lexical_harvester
from src.dictionary.schemas import (
    DictionaryHintResponse,
    DictionaryTerm,
    DictionaryTermCreate,
)
from src.dictionary.service import dictionary_service
from src.memory.database import get_db
from src.memory.models import (
    LexicalCandidateRecord,
    LexicalCandidateResponse,
    LexicalHarvestResult,
)

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


# ===================== Rotas do Agente Pescador & Buffer Léxico =====================


@router.get("/candidates", response_model=list[LexicalCandidateResponse])
async def list_lexical_candidates(
    status_filter: str | None = Query(default=None, alias="status", description="Filtrar por PENDING, HARVESTED, REJECTED"),
    db: Session = Depends(get_db),
):
    """Lista termos dúbios e candidatos no buffer de aprendizado ativo."""
    query = db.query(LexicalCandidateRecord)
    if status_filter:
        query = query.filter(LexicalCandidateRecord.status == status_filter.upper())
    return query.order_by(LexicalCandidateRecord.occurrence_count.desc(), LexicalCandidateRecord.created_at.desc()).all()


@router.post("/harvest", response_model=LexicalHarvestResult)
async def trigger_lexical_harvest(db: Session = Depends(get_db)):
    """Executa o Agente Pescador Léxico (rotina das 19:00 ou sob demanda)."""
    return await lexical_harvester.harvest_pending_candidates(db=db)


@router.patch("/candidates/{candidate_id}/promote", response_model=DictionaryTerm)
async def manual_promote_candidate(
    candidate_id: str,
    term_override: str | None = None,
    category: str = "GERAL",
    db: Session = Depends(get_db),
):
    """Promove manualmente um candidato para o Dicionário Oficial."""
    cand = db.query(LexicalCandidateRecord).filter(LexicalCandidateRecord.id == candidate_id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidato não encontrado")

    term_name = (term_override or cand.suggested_term or cand.raw_term).strip()
    term = dictionary_service.add_term(
        DictionaryTermCreate(
            term=term_name,
            phonetic_variations=[cand.raw_term] if cand.raw_term != term_name else [],
            category=category or cand.category or "GERAL",
            description=f"Promovido manualmente a partir de: '{cand.raw_term}' ({cand.context[:60] if cand.context else ''})",
        )
    )

    cand.status = "HARVESTED"
    cand.resolution_notes = f"Promovido manualmente como '{term_name}'"
    db.commit()
    return term


# ===================== Sugestões Inteligentes de Dicionário com spaCy NLP =====================


@router.get("/suggestions", summary="Retorna sugestões inteligentes de termos minerados com spaCy")
async def get_spacy_dictionary_suggestions(
    min_occurrences: int = Query(default=1, ge=1, description="Frequência mínima de ocorrência"),
    limit_messages: int = Query(default=100, ge=10, le=500, description="Quantidade de mensagens recentes a analisar"),
    db: Session = Depends(get_db),
):
    """Varre as mensagens recentes do banco de dados e sugere novos termos técnicos com spaCy."""
    from src.memory.models import MessageRecord
    from src.dictionary.spacy_suggester import spacy_term_miner

    messages = (
        db.query(MessageRecord)
        .filter(MessageRecord.revised_text.isnot(None))
        .order_by(MessageRecord.created_at.desc())
        .limit(limit_messages)
        .all()
    )

    texts_with_context = [
        {
            "text": msg.revised_text or msg.raw_text or "",
            "speaker": msg.speaker or "",
        }
        for msg in messages
    ]

    existing_terms = {t.term for t in dictionary_service.list_terms()}
    suggestions = spacy_term_miner.extract_candidate_terms_from_texts(
        texts_with_context=texts_with_context,
        existing_terms=existing_terms,
        min_occurrences=min_occurrences,
    )
    return suggestions


@router.post("/generate-phonetics", summary="Gera variações fonéticas prováveis para qualquer termo")
async def generate_phonetic_variations(payload: dict):
    """Gera variações fonéticas e transcrições prováveis do Whisper para um determinado termo."""
    from src.dictionary.spacy_suggester import phonetic_variation_generator

    term = str(payload.get("term") or "").strip()
    if not term:
        raise HTTPException(status_code=400, detail="Campo 'term' é obrigatório")

    variations = phonetic_variation_generator.generate(term)
    return {
        "term": term,
        "phonetic_variations": variations,
        "total_variations": len(variations),
    }



@router.delete("/candidates/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_or_reject_candidate(candidate_id: str, db: Session = Depends(get_db)):
    """Rejeita ou descarta um candidato a termo léxico."""
    cand = db.query(LexicalCandidateRecord).filter(LexicalCandidateRecord.id == candidate_id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidato não encontrado")

    cand.status = "REJECTED"
    cand.resolution_notes = "Descartado manualmente pelo operador"
    db.commit()
    return None
