# ☸️ Kubernetes Declarative Manifests — WhisperZap (Hermes Voice Memory)

Este diretório contém os manifestos declarativos para deploy e orquestração do ecossistema **WhisperZap** em qualquer cluster **Kubernetes (K8s, K3s, Minikube, EKS, GKE, AKS ou Bare-Metal)**.

---

## 📂 Estrutura dos Manifestos

| Arquivo | Descrição | Componentes |
| :--- | :--- | :--- |
| `00-namespace-and-config.yaml` | Namespace, ConfigMaps e Secrets | Namespace `whisperzap`, variáveis globais e credenciais seguras |
| `10-databases.yaml` | Armazenamento e Bancos de Dados | StatefulSets e PVCs para PostgreSQL (pgvector + Evolution) e Redis |
| `20-whisperzap-api.yaml` | Core Engine Backend | Deployment e Service do FastAPI (Faster-Whisper + AI Gateway) |
| `30-evolution-api.yaml` | Conector Oficial do WhatsApp | Deployment, PVC de instâncias e Service da Evolution API v2 |
| `40-n8n.yaml` | Motor de Orquestração de Fluxos | Deployment, PVC de workflows e Service do n8n |
| `50-ingress.yaml` | Roteamento Externo & TLS | Ingress Controller com regras de roteamento e certificados TLS |

---

## 🚀 Como Fazer o Deploy no Cluster

### 1. Criar o Namespace, Configurações e Secrets
Antes de aplicar, edite as chaves de API (`GEMINI_API_KEY`, senhas de banco) em `00-namespace-and-config.yaml`:

```bash
kubectl apply -f k8s/00-namespace-and-config.yaml
```

### 2. Subir os Bancos de Dados (StatefulSets & PVCs)
```bash
kubectl apply -f k8s/10-databases.yaml
```

Verifique se os volumes persistentes e pods estão `Running`:
```bash
kubectl get pods -n whisperzap -l app.kubernetes.io/part-of=whisperzap-storage
```

### 3. Subir a API Core do WhisperZap
```bash
kubectl apply -f k8s/20-whisperzap-api.yaml
```

### 4. Subir a Evolution API e o n8n
```bash
kubectl apply -f k8s/30-evolution-api.yaml
kubectl apply -f k8s/40-n8n.yaml
```

### 5. Configurar o Ingress & Domínios Externos
Edite o domínio host no arquivo `50-ingress.yaml` (ex: `hermes.seudominio.com`):

```bash
kubectl apply -f k8s/50-ingress.yaml
```

---

## 🔍 Monitoramento e Status dos Recursos

```bash
# Ver todos os recursos no namespace whisperzap
kubectl get all -n whisperzap

# Acompanhar logs da API WhisperZap
kubectl logs -n whisperzap -l app=hermes-api -f

# Acompanhar logs do n8n
kubectl logs -n whisperzap -l app=hermes-n8n -f
```
