# Automação de eventos do WhatsApp com n8n

O chatbot envia um `POST` JSON para `N8N_WEBHOOK_URL` sem bloquear a resposta da Twilio. Configure o node **Webhook** do n8n para aceitar `POST` e use a Production URL depois de ativar o workflow.

## Eventos

### `message.received`

```json
{
  "event": "message.received",
  "occurred_at": "2026-01-15T12:30:00+00:00",
  "source": "whatsapp-chatbot",
  "data": {
    "phone": "whatsapp:+5511999999999",
    "message": "Quais são os horários?",
    "received_at": "2026-01-15T12:30:00+00:00"
  }
}
```

### `message.responded`

Tem o mesmo envelope; `data` inclui `phone`, `message`, `response` e `responded_at`.

## Exemplo de fluxo

1. **Webhook**: método `POST`, caminho à sua escolha. Se configurou `N8N_WEBHOOK_SECRET`, proteja o node usando autenticação por header `X-Webhook-Secret` com o mesmo valor.
2. **Switch**: avalie `{{$json.body.event}}` (ou `{{$json.event}}`, conforme a configuração do node) e crie saídas para `message.received` e `message.responded`.
3. **Ações**: por exemplo, registre mensagens em uma planilha/CRM, envie uma notificação para atendimento humano ou crie um ticket. Conecte as ações apenas às saídas que devem dispará-las para evitar duplicidade.

O n8n pode apresentar o JSON recebido diretamente ou dentro de `body`, dependendo da versão/configuração do Webhook. Confirme o caminho no primeiro teste de execução e ajuste a expressão do Switch.

## Segurança e operação

- Use HTTPS para a URL do webhook e mantenha o segredo fora do workflow exportado/versionado.
- Os payloads incluem telefone e conteúdo das mensagens. Aplique controles de acesso, retenção e minimização de dados nos nodes seguintes.
- A entrega ocorre em thread de fundo com timeout configurável (`N8N_TIMEOUT_SECONDS`). Uma falha gera erro no log do chatbot; o evento não é retentado nem colocado em fila persistente.
- O workflow precisa estar ativo e usar a Production URL. A Test URL só funciona enquanto o n8n está aguardando uma execução de teste.
