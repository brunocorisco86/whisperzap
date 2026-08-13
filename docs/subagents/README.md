# 🤖 Subagentes Especialistas — Hermes Voice Memory

Para garantir alta eficiência, modularidade e especialização no desenvolvimento do **Hermes Voice Memory**, definimos 6 papéis de subagentes especialistas.

---

## 📜 Lista de Especialistas

| Subagente | Especialidade | Arquivo de Especificação |
| :--- | :--- | :--- |
| 🏗️ **`arch-specialist`** | Arquitetura de Sistemas & Pipeline de Memória | [`arch_specialist.md`](file:///home/brunoconter/Documentos/4_HOMELAB/9_Voice_Assistant/docs/subagents/arch_specialist.md) |
| 🔄 **`cicd-specialist`** | CI/CD, Pytest & Automação de Deploy | [`cicd_specialist.md`](file:///home/brunoconter/Documentos/4_HOMELAB/9_Voice_Assistant/docs/subagents/cicd_specialist.md) |
| 🛡️ **`cybersec-specialist`** | Segurança de APIs, Redes (Tailscale) & Segredos | [`cybersec_specialist.md`](file:///home/brunoconter/Documentos/4_HOMELAB/9_Voice_Assistant/docs/subagents/cybersec_specialist.md) |
| 🧠 **`hermes-agent-specialist`** | Agente Hermes, Prompts & Recuperação de Memória | [`hermes_agent_specialist.md`](file:///home/brunoconter/Documentos/4_HOMELAB/9_Voice_Assistant/docs/subagents/hermes_agent_specialist.md) |
| 🐧 **`vps-alpine-specialist`** | VPS, Alpine Linux, Docker & Raspberry Pi 3B | [`vps_alpine_specialist.md`](file:///home/brunoconter/Documentos/4_HOMELAB/9_Voice_Assistant/docs/subagents/vps_alpine_specialist.md) |
| ⚡ **`api-stack-specialist`** | FastAPI, PostgreSQL/pgvector, NetworkX & Whisper | [`api_stack_specialist.md`](file:///home/brunoconter/Documentos/4_HOMELAB/9_Voice_Assistant/docs/subagents/api_stack_specialist.md) |

---

## 💡 Como Invocar ou Consultar os Subagentes
Durante o desenvolvimento no assistente de código, subagentes especializados podem ser invocados usando `define_subagent` ou `invoke_subagent` com base nos prompts e escopos descritos em cada arquivo desta pasta.
