# 🤖 Subagentes Especialistas — Mnemosine Voice Intelligence

Para garantir alta eficiência, modularidade e especialização no desenvolvimento e governança do **Mnemosine**, definimos 6 papéis de subagentes especialistas.

---

## 📜 Lista de Especialistas

| Subagente | Especialidade | Arquivo de Especificação |
| :--- | :--- | :--- |
| 🏗️ **`arch-specialist`** | Arquitetura de Sistemas, As 9 Musas & Pipeline de Memória | [`arch_specialist.md`](./arch_specialist.md) |
| 🔄 **`cicd-specialist`** | CI/CD, Pytest, Auditoria de Qualidade & Deploy | [`cicd_specialist.md`](./cicd_specialist.md) |
| 🛡️ **`cybersec-specialist`** | Segurança de APIs, Criptografia, Redes (Tailscale) & Segredos | [`cybersec_specialist.md`](./cybersec_specialist.md) |
| 🧠 **`hermes-agent-specialist`** | Agentes IA, Prompts, spaCy NLP & Recuperação RAG Híbrido | [`hermes_agent_specialist.md`](./hermes_agent_specialist.md) |
| 🐧 **`vps-alpine-specialist`** | VPS Hostinger, Alpine Linux, Docker Compose & Homelab | [`vps_alpine_specialist.md`](./vps_alpine_specialist.md) |
| ⚡ **`api-stack-specialist`** | FastAPI, PostgreSQL/pgvector, Faster-Whisper & Prosódia | [`api_stack_specialist.md`](./api_stack_specialist.md) |

---

## 💡 Como Invocar ou Consultar os Subagentes
Durante o desenvolvimento no assistente de código, subagentes especializados podem ser invocados usando `define_subagent` ou `invoke_subagent` com base nos prompts e escopos descritos em cada arquivo desta pasta.
