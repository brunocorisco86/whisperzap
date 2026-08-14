"""Parser Polimórfico para Importação/Exportação de Contatos (Tabela Markdown & JSON)."""

import json
import logging
import re
from typing import Any
from src.contacts.schemas import (
    ROLE_SYNONYMS,
    ContactCreate,
    ContactResponse,
    ContactRole,
)


logger = logging.getLogger(__name__)


def clean_phone_number(raw_phone: str) -> str:
    """Extrai apenas os dígitos do número de telefone."""
    digits = re.sub(r"\D", "", raw_phone.strip())
    return digits or raw_phone.strip()


def normalize_role(raw_role: str) -> ContactRole:
    """Normaliza o papel a partir de texto (português ou inglês) para o Enum ContactRole."""
    cleaned = raw_role.strip().upper().replace(" ", "_")
    return ROLE_SYNONYMS.get(cleaned, ContactRole.UNKNOWN)


def parse_markdown_table(md_text: str) -> list[ContactCreate]:
    """Faz o parsing de uma tabela Markdown contendo colunas de contatos.

    Exemplo esperado:
    | Telefone | Nome | Papel | Empresa | Projetos |
    | :--- | :--- | :--- | :--- | :--- |
    | 44999991234 | João Silva | GESTOR | C.Vale | Silos, TMS |
    """
    lines = [line.strip() for line in md_text.strip().splitlines() if line.strip()]
    if not lines:
        return []

    # Encontra linha de cabeçalho
    header_idx = -1
    headers: list[str] = []
    for idx, line in enumerate(lines):
        if "|" in line and any(h in line.lower() for h in ["telefone", "phone", "nome", "name", "papel", "role"]):
            headers = [col.strip().lower() for col in line.split("|") if col.strip()]
            header_idx = idx
            break

    if header_idx == -1:
        # Tenta interpretar sem cabeçalho explícito se todas as linhas tiverem pipes
        table_lines = [l for l in lines if "|" in l and not re.match(r"^\|?\s*[-:]+[-| :]*$", l)]
        # Default column mapping: 0=telefone, 1=nome, 2=papel, 3=empresa, 4=projetos
        headers = ["telefone", "nome", "papel", "empresa", "projetos"]
    else:
        # Pula cabeçalho e linha separadora (ex: |:---|:---|)
        table_lines = []
        for l in lines[header_idx + 1 :]:
            if "|" in l and not re.match(r"^\|?\s*[-:]+[-| :]*$", l):
                table_lines.append(l)

    results: list[ContactCreate] = []

    for line in table_lines:
        cols = [c.strip() for c in line.split("|")]
        # Remove primeiro e último elemento vazios resultantes do split em pipes externos
        if line.startswith("|") and len(cols) > 0 and cols[0] == "":
            cols = cols[1:]
        if line.endswith("|") and len(cols) > 0 and cols[-1] == "":
            cols = cols[:-1]

        if not cols or len(cols) < 2:
            continue

        row_data: dict[str, str] = {}
        for idx, col_val in enumerate(cols):
            if idx < len(headers):
                h_name = headers[idx]
                row_data[h_name] = col_val

        # Extrai campos com fallback por nome de cabeçalho ou posição
        phone = (
            row_data.get("telefone")
            or row_data.get("phone")
            or row_data.get("numero")
            or (cols[0] if len(cols) > 0 else "")
        )
        name = (
            row_data.get("nome")
            or row_data.get("name")
            or row_data.get("contato")
            or (cols[1] if len(cols) > 1 else "")
        )
        role_raw = (
            row_data.get("papel")
            or row_data.get("role")
            or row_data.get("funcao")
            or (cols[2] if len(cols) > 2 else "UNKNOWN")
        )
        company = (
            row_data.get("empresa")
            or row_data.get("company")
            or (cols[3] if len(cols) > 3 else None)
        )
        projects_raw = (
            row_data.get("projetos")
            or row_data.get("projects")
            or (cols[4] if len(cols) > 4 else "")
        )

        phone_clean = clean_phone_number(phone)
        name_clean = name.strip()
        if not phone_clean or not name_clean or phone_clean.lower() == "telefone":
            continue

        role_enum = normalize_role(role_raw)
        company_clean = company.strip() if company and company.strip() not in ("-", "—", "null", "None") else None

        projects_list = []
        if projects_raw and projects_raw.strip() not in ("-", "—", "null", "None"):
            projects_list = [p.strip() for p in re.split(r"[,;/]+", projects_raw) if p.strip()]

        results.append(
            ContactCreate(
                phone_number=phone_clean,
                name=name_clean,
                role=role_enum,
                company=company_clean,
                projects=projects_list,
            )
        )

    return results


def parse_json_array(json_text: str) -> list[ContactCreate]:
    """Faz o parsing de uma lista JSON de contatos."""
    data = json.loads(json_text)
    if isinstance(data, dict):
        data = [data]

    results: list[ContactCreate] = []
    for item in data:
        phone = clean_phone_number(str(item.get("phone_number") or item.get("phone") or item.get("telefone", "")))
        name = str(item.get("name") or item.get("nome", "")).strip()
        if not phone or not name:
            continue

        role_raw = str(item.get("role") or item.get("papel", "UNKNOWN"))
        role_enum = normalize_role(role_raw)

        company = item.get("company") or item.get("empresa")
        projects = item.get("projects") or item.get("projetos") or []
        if isinstance(projects, str):
            projects = [p.strip() for p in projects.split(",") if p.strip()]

        results.append(
            ContactCreate(
                phone_number=phone,
                name=name,
                nickname=item.get("nickname") or item.get("apelido"),
                role=role_enum,
                company=company.strip() if isinstance(company, str) and company.strip() else None,
                projects=projects,
                custom_weight=item.get("custom_weight"),
                notes=item.get("notes") or item.get("notas"),
            )
        )
    return results


def parse_contact_batch(raw_text: str) -> list[ContactCreate]:
    """Detecta automaticamente se a entrada é JSON ou Tabela Markdown e executa o parsing."""
    trimmed = raw_text.strip()
    if trimmed.startswith("[") or trimmed.startswith("{"):
        try:
            return parse_json_array(trimmed)
        except json.JSONDecodeError:
            logger.warning("Falha ao decodificar JSON. Tentando fallback para Markdown Table.")

    return parse_markdown_table(trimmed)


def contacts_to_markdown_table(contacts: list[Any]) -> str:
    """Gera uma string de Tabela Markdown a partir de uma lista de contatos."""
    if not contacts:
        return (
            "| Telefone | Nome | Papel | Empresa | Projetos |\n"
            "| :--- | :--- | :--- | :--- | :--- |\n"
        )

    lines = [
        "| Telefone | Nome | Papel | Empresa | Projetos |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]

    for c in contacts:
        phone = getattr(c, "phone_number", "")
        name = getattr(c, "name", "")
        role = getattr(c, "role", "UNKNOWN")
        company = getattr(c, "company", None) or "-"
        projects = getattr(c, "projects", None) or getattr(c, "projects_json", None) or []
        projects_str = ", ".join(projects) if projects else "-"

        lines.append(f"| {phone} | {name} | {role} | {company} | {projects_str} |")

    return "\n".join(lines)
