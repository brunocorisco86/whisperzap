# 🕸️ Guia de Uso do Graphify — Contexto e Economia de Tokens

O **Graphify** é a nossa ferramenta de inteligência relacional para o código-fonte e documentação do projeto **Hermes Voice Memory**.

---

## 🎯 Por que usamos o Graphify?

1. **Economia de Tokens**: Em vez de passar dezenas de arquivos inteiros para o contexto do LLM, o Graphify gera um grafo de conhecimento local e permite consultas direcionadas (`BFS`/`DFS`).
2. **Contexto Completo**: Permite aos agentes de IA entenderem as dependências entre rotas do FastAPI, modelos de banco de dados, fluxos do n8n e especificações sem alucinar caminhos de arquivos.
3. **Persistência**: O grafo e suas análises ficam salvos no diretório `graphify-out/` (ignorado no Git).

---

## 🛠️ Comandos Principais

### 1. Gerar ou Atualizar o Grafo do Projeto
Para construir o grafo inicial ou atualizar após mudanças na documentação/código:

```bash
# Processamento completo do diretório atual
graphify .

# Atualização incremental (processa apenas arquivos novos/alterados)
graphify . --update

# Execução profunda (extração semântica rica)
graphify . --mode deep
```

### 2. Consultar o Grafo (GraphRAG / BFS Traversal)
Para responder a perguntas sobre o sistema com orçamento controlado de tokens:

```bash
# Consulta genérica
graphify query "Como o AI Gateway faz a revisão contextual?"

# Consulta limitando o orçamento de tokens (ex: 1500 tokens)
graphify query "Qual a taxonomia de intenções e entidades?" --budget 1500

# Rastrear caminho entre dois conceitos
graphify path "WhisperAPI" "PostgreSQL"

# Explicar um nó ou módulo específico
graphify explain "AIGatewayRouter"
```

---

## 📊 Arquivos Gerados (`graphify-out/`)
- `graph.html`: Visualizador interativo de grafos no navegador.
- `GRAPH_REPORT.md`: Relatório de auditoria e métricas de coesão/God Nodes.
- `graph.json`: Grafo estruturado para agentes e queries de GraphRAG.
- `cost.json`: Histórico e controle de consumo de tokens em extrações.

---

## 💡 Diretrizes para Agentes de IA
- Sempre verifique se `graphify-out/graph.json` existe antes de ler arquivos em lote.
- Ao investigar uma dúvida de arquitetura, utilize primeiramente `graphify query "<pergunta>"` para obter context com menor consumo de tokens.
