"""Testes automatizados para a Mineração Terminológica, Geração Fonética e Sugestões do Dicionário com spaCy."""

import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.dictionary.spacy_suggester import phonetic_variation_generator, spacy_term_miner
from src.memory.database import SessionLocal
from src.memory.models import MessageRecord
from datetime import datetime, timezone
from uuid import uuid4

client = TestClient(app)


def test_phonetic_variation_generator():
    """Valida a geração heurística de variações do Whisper para termos tecnológicos e do agronegócio."""
    # 1. Termo tecnológico com prefixo mtech
    vars_mtech = phonetic_variation_generator.generate("Mtech")
    assert any("emitech" in v or "m-tech" in v or "mtequi" in v for v in vars_mtech)

    # 2. Sigla com ponto C.Vale
    vars_cvale = phonetic_variation_generator.generate("C.Vale")
    assert any("cvale" in v or "sevale" in v or "c vale" in v for v in vars_cvale)

    # 3. Termo composto Agrocenter
    vars_agro = phonetic_variation_generator.generate("Agrocenter")
    assert any("agro center" in v or "senter" in v for v in vars_agro)

    # 4. Sigla em maiúsculas TMS
    vars_tms = phonetic_variation_generator.generate("TMS")
    assert any("t m s" in v or "tms" in v for v in vars_tms)


def test_spacy_term_miner_and_category_inference():
    """Valida a extração de jargões técnicos e inferência de categorias a partir de frases reais."""
    texts_sample = [
        {"text": "Precisamos calibrar o sensor de pressão estática do aviário 4.", "speaker": "Bruno Conter"},
        {"text": "Favor lançar os dados da pesagem no sistema FMIM até o final da tarde.", "speaker": "Valdecir"},
        {"text": "A curva de ganho de peso do lote de frango está excelente esta semana.", "speaker": "Debora Patel"},
    ]

    suggestions = spacy_term_miner.extract_candidate_terms_from_texts(
        texts_with_context=texts_sample,
        existing_terms={"Aviário", "Frango"},
        min_occurrences=1,
    )

    terms_found = {s.term: s for s in suggestions}
    assert len(suggestions) >= 1

    # Verifica se encontrou termos como 'pressão estática', 'FMIM' ou 'curva de ganho'
    assert any("Pressão Estática" in t or "FMIM" in t or "Curva De Ganho" in t or "Sensor De Pressão" in t for t in terms_found)

    # Valida que as sugestões têm variações fonéticas pré-calculadas
    for s in suggestions:
        assert isinstance(s.phonetic_variations, list)
        assert s.confidence_score >= 0.70


def test_dictionary_spacy_api_endpoints():
    """Testa os novos endpoints GET /suggestions e POST /generate-phonetics."""
    # 1. POST /generate-phonetics
    res_phon = client.post("/api/v1/dictionary/generate-phonetics", json={"term": "eProdutor"})
    assert res_phon.status_code == 200
    data_phon = res_phon.json()
    assert data_phon["term"] == "eProdutor"
    assert len(data_phon["phonetic_variations"]) >= 1

    # 2. GET /suggestions
    db = SessionLocal()
    try:
        msg = MessageRecord(
            id=str(uuid4()),
            created_at=datetime.now(timezone.utc),
            speaker="Técnico Avícola",
            revised_text="Verificar a ambiência e a cortina do galpão de frangos.",
        )
        db.merge(msg)
        db.commit()

        res_sug = client.get("/api/v1/dictionary/suggestions?min_occurrences=1&limit_messages=50")
        assert res_sug.status_code == 200
        data_sug = res_sug.json()
        assert isinstance(data_sug, list)
    finally:
        db.close()
