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

            subtasks.append({
                "index": idx,
                "completed": is_done,
                "text": item_text,
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

    def add_or_merge_subtask(
        self,
        existing_notes: Optional[str],
        primary_title: str,
        primary_audio_ref: Optional[str],
        duplicate_title: str,
        duplicate_audio_ref: Optional[str],
    ) -> str:
        """Incorpora a tarefa duplicada como uma nova subtarefa no checklist da primária.
        
        Se a primária ainda não possuir subtarefas, converte o título da própria primária
        na primeira subtarefa e anexa a duplicata como a segunda subtarefa.
        """
        notes = (existing_notes or "").strip()
        parsed = self.parse_subtasks(notes)

        ref_a = f" (🎙️ Ref: {primary_audio_ref})" if primary_audio_ref else ""
        ref_b = f" (🎙️ Ref: {duplicate_audio_ref})" if duplicate_audio_ref else ""

        if not parsed["has_subtasks"]:
            # Cria a estrutura inicial com as duas ações
            header = self.format_progress_header(completed=0, total=2)
            subtask_1 = f"- [ ] {primary_title.strip()}{ref_a}"
            subtask_2 = f"- [ ] {duplicate_title.strip()}{ref_b}"
            
            subtasks_block = f"{header}\n{subtask_1}\n{subtask_2}"
            if notes:
                return f"{subtasks_block}\n\n{notes}"
            return subtasks_block

        # Já possui subtarefas: adiciona a nova ao final da lista e recalcula o cabeçalho
        new_subtask_line = f"- [ ] {duplicate_title.strip()}{ref_b}"
        lines = notes.splitlines()
        new_lines = []
        subtask_inserted = False

        for i, line in enumerate(lines):
            if self.SUBTASK_REGEX.match(line):
                new_lines.append(line)
                # Se for a última linha ou a próxima linha não for subtarefa, insere aqui
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


subtask_service = SubtaskService()
