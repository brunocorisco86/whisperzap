# 📁 Resultados dos Testes de Áudio (Hermes Benchmarks)

Esta pasta armazena o histórico e os relatórios de execução dos testes com arquivos de áudio reais do WhatsApp e gravações de voz processadas pela API Hermes.

---

## 📄 Arquivos Nesta Pasta

| Arquivo | Descrição |
| :--- | :--- |
| [`audio_test_report.md`](audio_test_report.md) | Relatório executivo consolidado em Markdown (tabelas de desempenho, RTF, transcrições e segmentos). |
| [`audio_test_report.json`](audio_test_report.json) | Relatório estruturado em JSON com telemetria completa, tempos em milissegundos e respostas da API. |

---

## 🚀 Como Executar os Testes Novamente

1. **Suba o backend FastAPI**:
   ```bash
   .venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000
   ```

2. **Execute o script de benchmark**:
   ```bash
   .venv/bin/python scripts/run_audio_tests.py
   ```

Os relatórios nesta pasta serão atualizados automaticamente com os novos dados de latência, taxa de tempo real (RTF) e transcrições.
