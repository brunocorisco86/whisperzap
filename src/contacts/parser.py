"""Parser Polimórfico para Importação/Exportação de Contatos (Tabela Markdown & JSON)."""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional
from src.ai_gateway.bypass import is_valid_contact_phone
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

        raw_last = item.get("last_interaction_at")
        last_dt = None
        if raw_last:
            try:
                clean_ts = str(raw_last).replace(" ", "T")
                if not clean_ts.endswith("Z") and "+" not in clean_ts:
                    clean_ts += "+00:00"
                last_dt = datetime.fromisoformat(clean_ts.replace("Z", "+00:00"))
            except Exception:
                pass

        results.append(
            ContactCreate(
                phone_number=phone,
                name=name,
                nickname=item.get("nickname") or item.get("apelido"),
                role=role_enum,
                company=company.strip() if isinstance(company, str) and company.strip() else None,
                projects=projects,
                avatar_url=item.get("avatar_url") or item.get("profilePicUrl") or item.get("foto"),
                custom_weight=item.get("custom_weight"),
                notes=item.get("notes") or item.get("notas"),
                last_interaction_at=last_dt,
            )
        )
    return results


def parse_vcard_text(vcard_text: str) -> list[ContactCreate]:
    """Faz o parsing ultra-resiliente de contatos a partir de texto no formato vCard (.vcf).
    
    Suporta vCard 2.1, 3.0 e 4.0 exportados do Google Contacts, Apple iCloud ou Android.
    Trata linhas dobradas (folding), unescape de caracteres, normalização avançada de telefones
    (regras Brasil DDI/DDD/CSP/9º dígito) e enriquecimento de notas, empresa e foto.
    """
    import unicodedata

    def clean_vcard_phone(raw_phone: str) -> Optional[str]:
        if not raw_phone:
            return None
        # Remove normalização e non-breaking spaces (\xa0)
        norm = unicodedata.normalize("NFKD", raw_phone)
        # Corta ramal / sufixos
        norm = re.split(r"[/,]|ext|ramal|#", norm, flags=re.IGNORECASE)[0].strip()
        digits = re.sub(r"\D", "", norm)
        if not digits:
            return None

        # Remove prefixo internacional 00
        if digits.startswith("00"):
            digits = digits[2:]

        # Remove código de operadora CSP (ex: 01544, 02144, 04144, 01444, 03144...)
        # Padrão: 0 + 2 dígitos de operadora + 2 dígitos de DDD + 8 ou 9 dígitos (13 ou 14 dígitos totais)
        if digits.startswith("0") and len(digits) in (13, 14):
            digits = digits[3:]
        # Remove 0 inicial único de DDD (ex: 044999162543 -> 44999162543)
        elif digits.startswith("0") and len(digits) in (11, 12):
            digits = digits[1:]

        # Se tem 10 ou 11 dígitos (DDD Brasil sem 55), adiciona 55
        if len(digits) in (10, 11) and not digits.startswith("55"):
            digits = f"55{digits}"

        # Valida tamanho e estrutura
        if is_valid_contact_phone(digits) or (10 <= len(digits) <= 15):
            return digits
        return None

    def unescape_vcard_value(val: str) -> str:
        if not val:
            return ""
        return (
            val.replace(r"\,", ",")
            .replace(r"\;", ";")
            .replace(r"\:", ":")
            .replace(r"\n", "\n")
            .replace(r"\N", "\n")
            .replace(r"\\", "\\")
            .strip()
        )

    # Divide pelos blocos BEGIN:VCARD ... END:VCARD
    vcard_blocks = re.findall(r"BEGIN:VCARD(.*?)END:VCARD", vcard_text, re.DOTALL | re.IGNORECASE)
    if not vcard_blocks and "BEGIN:VCARD" in vcard_text.upper():
        # Fallback se não tiver END:VCARD no último bloco
        vcard_blocks = [vcard_text]

    results: list[ContactCreate] = []

    for block in vcard_blocks:
        lines = block.splitlines()
        # Tratamento de unfolding (linhas continuadas com espaço ou tab)
        unfolded_lines: list[str] = []
        for line in lines:
            if (line.startswith(" ") or line.startswith("\t")) and unfolded_lines:
                unfolded_lines[-1] += line[1:]
            else:
                unfolded_lines.append(line.strip())

        fn = ""
        n_field = ""
        org = ""
        nickname = ""
        photo_url: Optional[str] = None
        phones: list[str] = []
        emails: list[str] = []
        categories: list[str] = []
        notes_list: list[str] = []

        for line in unfolded_lines:
            if not line or line.startswith(";"):
                continue

            upper_line = line.upper()

            # FN (Formatted Name)
            if upper_line.startswith("FN:") or upper_line.startswith("FN;"):
                parts = line.split(":", 1)
                if len(parts) == 2 and not fn:
                    fn = unescape_vcard_value(parts[1])

            # N (Structured Name)
            elif upper_line.startswith("N:") or upper_line.startswith("N;"):
                parts = line.split(":", 1)
                if len(parts) == 2 and not n_field:
                    n_field = unescape_vcard_value(parts[1])

            # NICKNAME
            elif upper_line.startswith("NICKNAME:") or upper_line.startswith("NICKNAME;"):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    nickname = unescape_vcard_value(parts[1])

            # ORG (Organization / Company)
            elif upper_line.startswith("ORG:") or upper_line.startswith("ORG;"):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    org = unescape_vcard_value(parts[1]).replace(";", " - ").strip()

            # PHOTO (Avatar URL)
            elif "PHOTO" in upper_line and "http" in line:
                m = re.search(r"https?://[^\s;]+", line)
                if m:
                    photo_url = m.group(0).strip()

            # TEL (Phones)
            elif re.match(r"^(?:ITEM\d+\.)?TEL[;:]", upper_line):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    clean_p = clean_vcard_phone(parts[1])
                    if clean_p and clean_p not in phones:
                        phones.append(clean_p)

            # EMAIL
            elif re.match(r"^(?:ITEM\d+\.)?EMAIL[;:]", upper_line):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    clean_email = parts[1].strip()
                    if clean_email and clean_email not in emails:
                        emails.append(clean_email)

            # CATEGORIES (Tags / Labels do Google)
            elif upper_line.startswith("CATEGORIES:") or upper_line.startswith("CATEGORIES;"):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    cats = [c.strip() for c in parts[1].split(",") if c.strip() and c.strip().lower() != "mycontacts"]
                    categories.extend(cats)

            # NOTE
            elif upper_line.startswith("NOTE:") or upper_line.startswith("NOTE;"):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    notes_list.append(unescape_vcard_value(parts[1]))

        # Resolução do Nome
        name = fn
        if not name and org:
            name = org
        elif not name and n_field:
            n_parts = [p.strip() for p in n_field.split(";") if p.strip()]
            if n_parts:
                name = " ".join(reversed(n_parts))
        elif not name and nickname:
            name = nickname
        elif not name and emails:
            name = emails[0].split("@")[0]

        if not name and not phones:
            continue

        # Monta notas enriquecidas com emails, categorias e notas originais
        extra_notes = []
        if notes_list:
            extra_notes.extend(notes_list)
        if emails:
            extra_notes.append(f"Email: {', '.join(emails)}")
        if categories:
            extra_notes.append(f"Categorias: {', '.join(categories)}")
        final_notes = " | ".join(extra_notes) if extra_notes else "Importado via Google vCard"

        # Se tiver telefones válidos, cria um registro para cada telefone
        if phones:
            for phone in phones:
                contact_name = name or phone
                results.append(
                    ContactCreate(
                        name=contact_name,
                        phone_number=phone,
                        nickname=nickname or None,
                        role=ContactRole.UNKNOWN,
                        company=org or None,
                        notes=final_notes,
                    )
                )
        elif name:
            # Contato sem telefone mas com nome (útil para grafo de entidades)
            results.append(
                ContactCreate(
                    name=name,
                    phone_number="",
                    nickname=nickname or None,
                    role=ContactRole.UNKNOWN,
                    company=org or None,
                    notes=final_notes,
                )
            )

    return results


def parse_contact_batch(raw_text: str) -> list[ContactCreate]:
    """Detecta automaticamente se a entrada é vCard (.vcf), JSON ou Tabela Markdown e executa o parsing."""
    trimmed = raw_text.strip()
    if "BEGIN:VCARD" in trimmed.upper():
        return parse_vcard_text(trimmed)
    elif trimmed.startswith("[") or trimmed.startswith("{"):
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
