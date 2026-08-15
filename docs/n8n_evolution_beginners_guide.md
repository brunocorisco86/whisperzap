# 📱 Guia Descomplicado: Evolution API + n8n para WhatsApp

Este guia foi feito especialmente para quem nunca mexeu com a **Evolution API** ou **n8n**. É mais simples do que parece!

---

## 🧩 1. O que é cada coisa? (Em 30 segundos)

- **WhatsApp no Celular**: Onde você grava áudios e recebe as respostas.
- **Evolution API** (`http://localhost:8080`): É um "conector de WhatsApp". Ele gera um QR Code (igualzinho ao WhatsApp Web). Quando você escaneia com a câmera do WhatsApp, ele ganha a habilidade de enviar e receber mensagens via automação.
- **n8n** (`http://localhost:5678`): É uma tela visual cheia de caixinhas conectadas. Exemplo: *"Quando chegar áudio no WhatsApp ➔ Mande para a API do Hermes ➔ Devolva o texto limpo no WhatsApp"*.

---

## ⚡ 2. Passo 1: Subir os Serviços (1 Comando)

No terminal do seu computador, basta executar:

```bash
./scripts/start_homelab_whatsapp.sh
```

Pronto! O Docker vai baixar e inicializar automaticamente a Evolution API e o n8n em segundo plano.

---

## 📲 3. Passo 2: Conectar o seu WhatsApp (Escanear o QR Code)

1. No seu navegador, abra o Swagger da Evolution API: 👉 **`http://localhost:8080/docs`** (ou acesse a rota direta de instâncias).
2. **Criar a Instância `hermes`**:
   - Vá no endpoint `POST /instance/create`.
   - Clique em "Try it out".
   - No campo `instanceName`, digite: `"hermes"`.
   - No campo `token`, digite: `"hermes_evolution_token_secret_123"`.
   - Clique em **Execute**.
3. **Conectar e Escanear QR Code**:
   - Vá no endpoint `GET /instance/connect/hermes`.
   - Clique em "Try it out" ➔ **Execute**.
   - O sistema vai exibir o **QR Code** na tela (ou em formato base64/imagem).
   - No seu celular, abra o WhatsApp ➔ **Aparelhos Conectados** ➔ **Conectar Aparelho** ➔ Aponte a câmera para a tela.
   - 🎉 **Pronto! Seu WhatsApp agora está conectado à API!**

---

## ⚙️ 4. Passo 3: Importar os Workflows no n8n

1. Abra o n8n no navegador: 👉 **`http://localhost:5678`**
2. No primeiro acesso, crie seu usuário e senha de administrador local (ex: seu e-mail e uma senha qualquer).
3. Na tela inicial do n8n:
   - Clique no botão **"Add workflow"** (ou "+") no canto superior direito.
   - Clique nos **três pontinhos (...)** no canto superior direito da tela do fluxo.
   - Clique em **"Import from File"**.
   - Selecione o arquivo [`workflows/n8n_whatsapp_voice_transcription.json`](file:///home/brunoconter/Documentos/4_HOMELAB/9_Voice_Assistant/workflows/n8n_whatsapp_voice_transcription.json).
   - O fluxo visual de transcrição vai se desenhar na sua tela na hora!
4. **Ativar o Fluxo**:
   - No canto superior direito, mude o botão de **"Inactive"** para **"Active"** (🟢 Ativo).

*(Repita o mesmo processo de importação para os outros 3 arquivos da pasta `workflows/`: `n8n_daily_summary_cron.json`, `n8n_weekly_plan_cron.json` e `n8n_hermes_qa_whatsapp.json`).*

---

## 🎙️ 5. Passo 4: O Teste de Ouro!

1. Pegue o seu celular.
2. Abra a conversa do WhatsApp conectado (ou mande mensagem de outro número para o número conectado).
3. **Grave um áudio falando qualquer coisa**, por exemplo:
   > *"Então amanhã eu preciso falar com o João sobre o sensor de ração do silo 3."*
4. Em 2 a 3 segundos, você receberá de volta no WhatsApp:
   > *"Então, amanhã eu preciso falar com o João sobre o sensor de ração do Silo 3."*

---

## 🧠 6. Testando o Agente Hermes pelo WhatsApp

Envie uma mensagem de texto começando com `?` no WhatsApp:
> `? Quem é o responsável pelos silos?`

O Hermes consultará a memória gravada dos seus áudios anteriores e responderá no WhatsApp citando os nomes e detalhes!
