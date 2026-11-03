# Chatbot geral para WhatsApp

Assistente de propósito geral que recebe mensagens pelo webhook do WhatsApp da Twilio, responde usando a API da OpenAI e pode enviar eventos para automações no n8n. O comportamento do assistente, o modelo e as integrações são configuráveis por variáveis de ambiente.

## Requisitos

- Python 3.10 ou superior
- Uma conta/projeto na OpenAI e uma chave de API
- Uma conta Twilio com WhatsApp habilitado (Sandbox serve para desenvolvimento)
- n8n é opcional; pode ser local ou hospedado

## Instalação

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
```

No Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -3 -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edite `.env` com suas próprias credenciais. O arquivo `.env` é local e não deve ser enviado ao Git. Como um `.env` já estava rastreado neste repositório, ele foi removido do índice sem apagar sua cópia local. Essa remoção não apaga credenciais de commits anteriores; se o arquivo continha credenciais reais, revogue-as e gere novas.

```dotenv
OPENAI_API_KEY=sua-chave
OPENAI_MODEL=gpt-4o-mini
BOT_NAME=Assistente virtual

TWILIO_AUTH_TOKEN=seu-token
TWILIO_VALIDATE_SIGNATURE=false

# Opcional: URL do node Webhook do n8n
N8N_WEBHOOK_URL=
N8N_WEBHOOK_SECRET=
```

`CHATBOT_SYSTEM_PROMPT` pode substituir as instruções padrão do assistente. `MAX_HISTORY_MESSAGES` limita o contexto enviado ao modelo (padrão: 12 mensagens) e `MAX_CONVERSATIONS` limita conversas mantidas na memória (padrão: 1000). A porta padrão é `5000`.

## Executar localmente

```bash
python3 app.py
```

No Windows, use `py -3 app.py`.

Confirme que o servidor está disponível em `http://127.0.0.1:5000/health`. Para receber mensagens do WhatsApp em desenvolvimento, exponha a porta com um túnel HTTPS, como ngrok, e configure a URL pública terminada em `/whatsapp` como webhook de mensagens recebidas no console Twilio.

Em produção, defina `APP_ENV=production` para habilitar a validação da assinatura da Twilio por padrão (ou configure `TWILIO_VALIDATE_SIGNATURE=true`). Configure o proxy/servidor para que Flask receba a URL pública correta nas requisições. Não desabilite a validação em uma implantação pública.

## Integração com n8n

1. No n8n, crie um workflow com um node **Webhook**, método `POST`, e copie a **Production URL**.
2. Configure `N8N_WEBHOOK_URL` com essa URL e opcionalmente defina `N8N_WEBHOOK_SECRET`.
3. Ative o workflow. Se usar um segredo, valide o cabeçalho `X-Webhook-Secret` no início do fluxo.
4. No workflow, use um node **Switch** sobre `{{$json.event}}` para separar `message.received` e `message.responded`, e conecte ações como CRM, planilhas, notificações ou criação de tickets.

A aplicação envia eventos em segundo plano e não aguarda o n8n para responder ao usuário. Falhas de entrega ficam registradas no log da aplicação. Os eventos contêm o número de telefone e o texto da conversa; limite o acesso ao workflow, use HTTPS e não encaminhe dados pessoais para serviços desnecessários. O contrato e exemplos estão em [`n8n/README.md`](./n8n/README.md).

## Endpoints

| Método | Caminho | Uso |
|---|---|---|
| `GET` | `/health` | Estado do serviço e indicação não sensível de configuração de integrações |
| `POST` | `/whatsapp` | Webhook de mensagens recebidas da Twilio; campos `From` e `Body` |

O usuário pode enviar `reiniciar`, `reiniciar conversa`, `limpar conversa`, `começar de novo`, `comecar de novo` ou `reset` para apagar o contexto atual.

## Estado e limitações

- O histórico de conversa fica somente na memória do processo: reiniciar o serviço apaga o contexto e múltiplas instâncias não compartilham conversas.
- A aplicação não guarda conversas em CSV ou banco de dados. `dados_chatbot.csv` é um arquivo legado do antigo exemplo de pedidos e não é usado pelo assistente geral.
- A integração com n8n usa entrega assíncrona sem fila durável; falhas são registradas, mas não retentadas automaticamente. Para alto volume, use uma fila persistente.
- A resposta do modelo depende da disponibilidade e dos limites de uso do provedor configurado.

## Testes

```bash
python3 -m unittest discover -s tests -v
```

Os testes não chamam a OpenAI, Twilio ou um servidor n8n real.
