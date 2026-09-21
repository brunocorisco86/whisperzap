"""Serviço de Subtarefas, Checklists e Progresso Percentual para o Terpsícore.

Permite estruturar tarefas consolidadas em subtarefas acionáveis em markdown:
- [ ] Subtarefa pendente
- [x] Subtarefa concluída
Calcula automaticamente a taxa de conclusão percentual e formata cabeçalhos executivos.
"""

import re
from typing import Any, Dict, List, Optional


class SubtaskService:
    """Gerencia a extração, formatação e alternância de subtarefas interativas."""

    SUBTASK_REGEX = re.compile(r"^\s*-\s*\[([ xX])\]\s*(.+)$", re.MULTILINE)
    HEADER_REGEX = re.compile(r"###\s*📋\s*Subtarefas\s*\(.*?\):", re.IGNORECASE)

    def parse_subtasks(self, notes: Optional[str]) -> Dict[str, Any]:
        """Extrai a lista de subtarefas, contagem e percentual de progresso."""
        if not notes:
            return {
                "has_subtasks": False,
                "total": 0,
                "completed": 0,
                "percentage": 0,
                "subtasks": [],
            }

        matches = list(self.SUBTASK_REGEX.finditer(notes))
        if not matches:
            return {
                "has_subtasks": False,
                "total": 0,
                "completed": 0,
                "percentage": 0,
                "subtasks": [],
            }

        subtasks = []
        completed_count = 0

        for idx, m in enumerate(matches):
            is_done = m.group(1).strip().lower() == "x"
            item_text = m.group(2).strip()
            if is_done:
                completed_count += 1

            # Extrai referência de áudio se presente (ex: "🎙️ Áudio: msg_123" ou "🎙️ Ref: msg_123")
            audio_match = re.search(r"🎙️\s*(?:Áudio|Ref|Msg):\s*([a-zA-Z0-9_\-]+)", item_text)
            audio_ref = audio_match.group(1) if audio_match else None
            clean_title = re.sub(r"\(🎙️\s*(?:Áudio|Ref|Msg):\s*[a-zA-Z0-9_\-]+\)", "", item_text).strip()

            subtasks.append({
                "index": idx,
                "completed": is_done,
                "text": item_text,
                "title": clean_title,
                "audio_ref": audio_ref,
            })

        total = len(subtasks)
        pct = round((completed_count / total * 100)) if total > 0 else 0

        return {
            "has_subtasks": True,
            "total": total,
            "completed": completed_count,
            "percentage": pct,
            "subtasks": subtasks,
        }

    def format_progress_header(self, completed: int, total: int) -> str:
        """Gera o cabeçalho executivo formatado com contagem e percentual."""
        pct = round((completed / total * 100)) if total > 0 else 0
        return f"### 📋 Subtarefas ({completed}/{total} concluídas - {pct}%):"

    def _are_titles_equivalent(self, t1: Optional[str], t2: Optional[str]) -> bool:
        """Determina se dois títulos de tarefas/subtarefas são equivalentes ou redundantes."""
        if not t1 or not t2:
            return False
        clean1 = re.sub(r"[^\w\s]", "", t1.lower()).strip()
        clean2 = re.sub(r"[^\w\s]", "", t2.lower()).strip()
        if clean1 == clean2:
            return True
        if clean1 in clean2 or clean2 in clean1:
            if min(len(clean1), len(clean2)) >= 10:
                return True
        from difflib import SequenceMatcher
        return SequenceMatcher(None, clean1, clean2).ratio() >= 0.82

    def deduplicate_subtasks(self, notes: Optional[str]) -> str:
        """Sanitiza e remove subtarefas duplicadas existentes dentro do bloco de notas."""
        if not notes:
            return ""
        parsed = self.parse_subtasks(notes)
        if not parsed["has_subtasks"] or len(parsed["subtasks"]) <= 1:
            return notes

        seen_titles: List[str] = []
        unique_subtasks: List[Dict[str, Any]] = []
        for st in parsed["subtasks"]:
            title = st["title"]
            is_dup = any(self._are_titles_equivalent(title, seen) for seen in seen_titles)
            if not is_dup:
                seen_titles.append(title)
                unique_subtasks.append(st)
            else:
                # Se a duplicata estava marcada como concluída, propaga o status concluído
                if st["completed"]:
                    for u in unique_subtasks:
                        if self._are_titles_equivalent(title, u["title"]):
                            u["completed"] = True
                            break

        if len(unique_subtasks) == len(parsed["subtasks"]):
            return notes

        total = len(unique_subtasks)
        completed = sum(1 for u in unique_subtasks if u["completed"])
        new_header = self.format_progress_header(completed, total)

        subtask_lines = [
            f"- [{'x' if u['completed'] else ' '}] {u['text']}"
            for u in unique_subtasks
        ]

        # Mantém quaisquer anotações complementares fora do checklist
        lines = notes.splitlines()
        remaining_lines = []
        for line in lines:
            if self.HEADER_REGEX.match(line) or self.SUBTASK_REGEX.match(line):
                continue
            remaining_lines.append(line)

        body = "\n".join(remaining_lines).strip()
        checklist_block = f"{new_header}\n" + "\n".join(subtask_lines)
        if body:
            return f"{checklist_block}\n\n{body}"
        return checklist_block

    def add_or_merge_subtask(
        self,
        existing_notes: Optional[str],
        primary_title: str,
        primary_audio_ref: Optional[str],
        duplicate_title: str,
        duplicate_audio_ref: Optional[str],
    ) -> str:
        """Incorpora a tarefa duplicada como uma nova subtarefa no checklist da primária.
        
        Se a primária ainda não possuir subtarefas, converte o título da primária
        na primeira subtarefa e, caso a duplicata traga uma ação distinta, anexa como segunda subtarefa.
        Evita a criação de subtarefas idênticas repetidas.
        """
        notes = (existing_notes or "").strip()
        parsed = self.parse_subtasks(notes)

        ref_a = f" (🎙️ Ref: {primary_audio_ref})" if primary_audio_ref else ""
        ref_b = f" (🎙️ Ref: {duplicate_audio_ref})" if duplicate_audio_ref else ""

        is_same_as_primary = self._are_titles_equivalent(primary_title, duplicate_title)

        if not parsed["has_subtasks"]:
            if is_same_as_primary:
                # Títulos equivalentes: não duplica a ação! Mantém 1 subtarefa e registra a referência
                header = self.format_progress_header(completed=0, total=1)
                subtask_1 = f"- [ ] {primary_title.strip()}{ref_a or ref_b}"
                subtasks_block = f"{header}\n{subtask_1}"
            else:
                header = self.format_progress_header(completed=0, total=2)
                subtask_1 = f"- [ ] {primary_title.strip()}{ref_a}"
                subtask_2 = f"- [ ] {duplicate_title.strip()}{ref_b}"
                subtasks_block = f"{header}\n{subtask_1}\n{subtask_2}"

            if notes:
                return f"{subtasks_block}\n\n{notes}"
            return subtasks_block

        # Já possui subtarefas: verifica se a duplicata já existe no checklist
        for st in parsed["subtasks"]:
            if self._are_titles_equivalent(st["title"], duplicate_title):
                # Subtarefa já existe, não insere duplicata repetida
                return self.deduplicate_subtasks(notes)

        # Adiciona a nova ação ao checklist
        new_subtask_line = f"- [ ] {duplicate_title.strip()}{ref_b}"
        lines = notes.splitlines()
        new_lines = []
        subtask_inserted = False

        for i, line in enumerate(lines):
            if self.SUBTASK_REGEX.match(line):
                new_lines.append(line)
                if i == len(lines) - 1 or not self.SUBTASK_REGEX.match(lines[i + 1]):
                    if not subtask_inserted:
                        new_lines.append(new_subtask_line)
                        subtask_inserted = True
            else:
                new_lines.append(line)

        if not subtask_inserted:
            new_lines.append(new_subtask_line)

        joined_notes = "\n".join(new_lines)
        recalculated = self.parse_subtasks(joined_notes)
        new_header = self.format_progress_header(recalculated["completed"], recalculated["total"])

        if self.HEADER_REGEX.search(joined_notes):
            return self.HEADER_REGEX.sub(new_header, joined_notes, count=1)
        return f"{new_header}\n{joined_notes}"

    def toggle_subtask(self, notes: str, subtask_index: int, target_state: Optional[bool] = None) -> str:
        """Alterna o estado de uma subtarefa ([ ] <-> [x]) pelo índice e recalcula o percentual."""
        if not notes:
            return ""

        matches = list(self.SUBTASK_REGEX.finditer(notes))
        if subtask_index < 0 or subtask_index >= len(matches):
            return notes

        target_match = matches[subtask_index]
        current_state = target_match.group(1).strip().lower() == "x"
        new_state = (not current_state) if target_state is None else target_state
        mark = "x" if new_state else " "

        start_span, end_span = target_match.span()
        matched_line = target_match.group(0)
        new_line = re.sub(r"\[([ xX])\]", f"[{mark}]", matched_line, count=1)

        updated_notes = notes[:start_span] + new_line + notes[end_span:]

        # Recalcula o cabeçalho com a nova contagem
        parsed = self.parse_subtasks(updated_notes)
        new_header = self.format_progress_header(parsed["completed"], parsed["total"])

        if self.HEADER_REGEX.search(updated_notes):
            return self.HEADER_REGEX.sub(new_header, updated_notes, count=1)
        return updated_notes

    def remove_subtask(self, notes: str, audio_ref: Optional[str] = None, title: Optional[str] = None) -> str:
        """Remove uma subtarefa das anotações pelo audio_ref ou título e recalcula o progresso."""
        if not notes:
            return ""

        parsed = self.parse_subtasks(notes)
        items = parsed.get("subtasks", [])
        if not items:
            return notes

        remaining_items = []
        for it in items:
            # Compara audio_ref se fornecido
            if audio_ref and it.get("audio_ref") and it["audio_ref"].strip() == audio_ref.strip():
                continue
            # Compara título se fornecido
            if title and (
                (it.get("title") and it["title"].strip().lower() == title.strip().lower())
                or (it.get("text") and title.strip().lower() in it["text"].strip().lower())
            ):
                continue
            remaining_items.append(it)

        # Se nenhuma subtarefa foi removida, retorna inalterado
        if len(remaining_items) == len(items):
            return notes

        # Remove todas as linhas antigas de subtarefas e cabeçalho
        non_subtask_lines = []
        for line in notes.splitlines():
            if self.HEADER_REGEX.match(line) or self.SUBTASK_REGEX.match(line):
                continue
            non_subtask_lines.append(line)

        trailing_notes = "\n".join(non_subtask_lines).strip()

        if not remaining_items:
            return trailing_notes

        completed = sum(1 for it in remaining_items if it["completed"])
        total = len(remaining_items)
        header = self.format_progress_header(completed, total)

        checklist_lines = []
        for it in remaining_items:
            box = "[x]" if it["completed"] else "[ ]"
            checklist_lines.append(f"- {box} {it['text']}")

        block = f"{header}\n" + "\n".join(checklist_lines)
        if trailing_notes:
            return f"{block}\n\n{trailing_notes}"
        return block


subtask_service = SubtaskService()
