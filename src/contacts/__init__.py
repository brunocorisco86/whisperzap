"""Módulo de Contatos, Papéis e Ponderação de Prioridades Hermes."""

from src.contacts.models import ContactRecord
from src.contacts.router import router
from src.contacts.service import contact_service

__all__ = ["router", "contact_service", "ContactRecord"]
