"""Schemas Pydantic para o Módulo de Contatos, Papéis e Prioridades."""

from datetime import datetime
from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class ContactRole(str, Enum):
    """Papéis hierárquicos e relacionais de contatos."""

    EXECUTIVE = "EXECUTIVE"  # Gestores diretos, diretores, líderes (peso 1.0)
    FAMILY_CORE = "FAMILY_CORE"  # Cônjuge, mãe, pai, filhos (peso 0.95)
    PRODUCER_COOPERATED = "PRODUCER_COOPERATED"  # Produtores rurais, cooperados, associados e integrados (peso 0.90)
    STAKEHOLDER = "STAKEHOLDER"  # Clientes chave, parceiros de projetos estratégicos (peso 0.85)
    COLLEAGUE = "COLLEAGUE"  # Colegas de trabalho, equipe, pares operacionais (peso 0.70)
    FAMILY_EXTENDED = "FAMILY_EXTENDED"  # Sogros, parentes, tios (peso 0.60)
    SERVICE_VENDOR = "SERVICE_VENDOR"  # Prestadores de serviços, fornecedores (peso 0.50)
    UNKNOWN = "UNKNOWN"  # Contatos novos / não classificados (peso 0.40)


ROLE_WEIGHTS: dict[ContactRole, float] = {
    ContactRole.EXECUTIVE: 1.00,
    ContactRole.FAMILY_CORE: 0.95,
    ContactRole.PRODUCER_COOPERATED: 0.90,
    ContactRole.STAKEHOLDER: 0.85,
    ContactRole.COLLEAGUE: 0.70,
    ContactRole.FAMILY_EXTENDED: 0.60,
    ContactRole.SERVICE_VENDOR: 0.50,
    ContactRole.UNKNOWN: 0.40,
}

# Sinônimos em português para facilitar o parsing de tabelas Markdown
ROLE_SYNONYMS: dict[str, ContactRole] = {
    "EXECUTIVE": ContactRole.EXECUTIVE,
    "GESTOR": ContactRole.EXECUTIVE,
    "GERENTE": ContactRole.EXECUTIVE,
    "DIRETOR": ContactRole.EXECUTIVE,
    "CHEFE": ContactRole.EXECUTIVE,
    "LIDER": ContactRole.EXECUTIVE,
    "FAMILY_CORE": ContactRole.FAMILY_CORE,
    "FAMILIA": ContactRole.FAMILY_CORE,
    "FAMÍLIA": ContactRole.FAMILY_CORE,
    "CONJUGE": ContactRole.FAMILY_CORE,
    "CÔNJUGE": ContactRole.FAMILY_CORE,
    "ESPOSA": ContactRole.FAMILY_CORE,
    "ESPOSO": ContactRole.FAMILY_CORE,
    "MARIDO": ContactRole.FAMILY_CORE,
    "MAE": ContactRole.FAMILY_CORE,
    "MÃE": ContactRole.FAMILY_CORE,
    "PAI": ContactRole.FAMILY_CORE,
    "FILHO": ContactRole.FAMILY_CORE,
    "FILHA": ContactRole.FAMILY_CORE,
    "PRODUCER_COOPERATED": ContactRole.PRODUCER_COOPERATED,
    "PRODUTOR": ContactRole.PRODUCER_COOPERATED,
    "PRODUTOR RURAL": ContactRole.PRODUCER_COOPERATED,
    "ASSOCIADO": ContactRole.PRODUCER_COOPERATED,
    "COOPERADO": ContactRole.PRODUCER_COOPERATED,
    "INTEGRADO": ContactRole.PRODUCER_COOPERATED,
    "AVICULTOR": ContactRole.PRODUCER_COOPERATED,
    "GRANJEIRO": ContactRole.PRODUCER_COOPERATED,
    "STAKEHOLDER": ContactRole.STAKEHOLDER,
    "CLIENTE": ContactRole.STAKEHOLDER,
    "PARCEIRO": ContactRole.STAKEHOLDER,
    "SPONSOR": ContactRole.STAKEHOLDER,
    "COLLEAGUE": ContactRole.COLLEAGUE,
    "COLEGA": ContactRole.COLLEAGUE,
    "EQUIPE": ContactRole.COLLEAGUE,
    "PAR": ContactRole.COLLEAGUE,
    "FAMILY_EXTENDED": ContactRole.FAMILY_EXTENDED,
    "PARENTES": ContactRole.FAMILY_EXTENDED,
    "SOGRA": ContactRole.FAMILY_EXTENDED,
    "SOGRO": ContactRole.FAMILY_EXTENDED,
    "TIO": ContactRole.FAMILY_EXTENDED,
    "TIA": ContactRole.FAMILY_EXTENDED,
    "CUNHADO": ContactRole.FAMILY_EXTENDED,
    "SERVICE_VENDOR": ContactRole.SERVICE_VENDOR,
    "FORNECEDOR": ContactRole.SERVICE_VENDOR,
    "PRESTADOR": ContactRole.SERVICE_VENDOR,
    "SERVICO": ContactRole.SERVICE_VENDOR,
    "SERVIÇO": ContactRole.SERVICE_VENDOR,
    "UNKNOWN": ContactRole.UNKNOWN,
    "DESCONHECIDO": ContactRole.UNKNOWN,
    "OUTRO": ContactRole.UNKNOWN,
}


class ContactBase(BaseModel):
    phone_number: str = Field(..., description="Número de telefone ou WhatsApp (com DDD)")
    name: str = Field(..., description="Nome completo ou identificador do contato")
    nickname: Optional[str] = Field(default=None, description="Apelido ou forma coloquial usada em áudios")
    role: ContactRole = Field(default=ContactRole.UNKNOWN, description="Papel ou categoria de relacionamento")
    company: Optional[str] = Field(default=None, description="Empresa, cooperativa ou contexto organizacional")
    projects: list[str] = Field(default_factory=list, description="Projetos ou temas vinculados a este contato")
    avatar_url: Optional[str] = Field(default=None, description="URL da foto de perfil do WhatsApp")
    custom_weight: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Peso manual customizado de 0.0 a 1.0 (opcional)"
    )
    notes: Optional[str] = Field(default=None, description="Anotações e observações adicionais")


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    phone_number: Optional[str] = None
    nickname: Optional[str] = None
    role: Optional[ContactRole] = None
    company: Optional[str] = None
    projects: Optional[list[str]] = None
    avatar_url: Optional[str] = None
    custom_weight: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    notes: Optional[str] = None


class ContactResponse(ContactBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    effective_weight: float = Field(..., description="Peso final calculado para priorização")
    latest_sentiment: Optional[str] = Field(default="NEUTRAL", description="Sentimento mais recente do contato")
    recent_sentiments: list[dict] = Field(default_factory=list, description="Últimos sentimentos e resumos de mensagens")
    created_at: datetime
    updated_at: datetime


class ContactBatchImportRequest(BaseModel):
    """Requisição para importação em lote via texto bruto (Tabela Markdown ou JSON)."""

    content: str = Field(..., description="Tabela Markdown ou Array JSON com a lista de contatos preenchida")


class ContactBatchImportResponse(BaseModel):
    """Resultado da importação em lote."""

    imported_count: int
    updated_count: int
    errors: list[str] = Field(default_factory=list)
    contacts: list[ContactResponse] = Field(default_factory=list)
