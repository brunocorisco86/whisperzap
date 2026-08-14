"""Módulo de Dicionário Léxico e Glossário de Domínio Hermes."""

from src.dictionary.router import router
from src.dictionary.service import dictionary_service

__all__ = ["router", "dictionary_service"]
