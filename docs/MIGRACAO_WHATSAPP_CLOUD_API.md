# Migração WhatsApp: UAZAPI → Cloud API oficial (Meta)

> **Decisão:** migrar o número atual do Auto Ads + montar **direto na Cloud API da Meta** (sem BSP).
> **Motivo:** acabar com queda de sessão da UAZAPI (`session is not reconnectable`) e com o bloqueio de início de conversa (erro `463`). A Cloud API é hospedada pela Meta — não tem QR/sessão pra cair.
> **Status:** preparação (este doc). O cutover real (Fases 2–3) derruba o número — fazer em momento controlado.

---

## ⚠️ Antes de começar (riscos do cutover)

1. O número precisa **sair do app do WhatsApp** (apagar a conta dele no app). Depois vira 100% API — **irreversível** pro uso no app.
2. **Histórico de conversa não migra.**
3. Janela de **downtime** entre apagar (UAZAPI/app) e registrar na Cloud API.
4. Precisa receber **SMS/ligação** no número pra confirmar o código.

---

## Fases (cliques no Meta = você; n8n = Claude)

| Fase | O quê | Quem |
|---|---|---|
| 1 | App "Quirk Auto Ads" → Adicionar produto **WhatsApp** → cria a WABA | Você (guiado) |
| 2 | Desconectar UAZAPI + **apagar conta WhatsApp** do número | Você |
| 3 | Registrar número na Cloud API (nome de exibição + código SMS) → pega **`phone_number_id`** | Você (guiado) |
| 4 | **Token permanente** (system user QuirkOps, escopos `whatsapp_business_messaging` + `whatsapp_business_management`) + **webhook** (campo `messages`) | Você (guiado) |
| 5 | Submeter **template de boas-vindas** (abaixo) pra aprovação | Você |
| 6 | Trocar os 15 nós de envio + parse de entrada pra Cloud API | Claude (n8n) |

---

## Template de boas-vindas (pronto pra submeter)

No **WhatsApp Manager → Message Templates → Create template**:

- **Name:** `ativacao_auto_ads`
- **Category:** **Utility** (é follow-up de uma transação — pagamento confirmado)
- **Language:** Portuguese (BR) — `pt_BR`
- **Header:** (nenhum)
- **Body:**
  ```
  Oi, {{1}}! 👋 Seu pagamento do Quirk Auto Ads foi confirmado ✓

  Falta só um passo rápido pra subir seu primeiro anúncio: conectar sua conta Meta. Toque em "Quero começar" que eu te guio por aqui, passo a passo.
  ```
  - **Variável {{1}}** = primeiro nome. **Exemplo pra aprovação:** `Renan`
- **Footer:**
  ```
  Quirk Auto Ads
  ```
- **Buttons** (2):
  1. **Quick reply** → texto: `Quero começar`
  2. **Visit website (URL)** → texto: `Ver guia completo` · URL: `https://lp.quirkgrowth.com.br/autoads/onboarding.html`

> O botão **Quero começar** é a peça-chave: quando o cliente toca, conta como mensagem recebida → abre a janela de 24h → o bot manda o guia + instruções como texto livre (sem template, sem custo extra).

---

## Mudança no fluxo de boas-vindas (gateway)

**Hoje (UAZAPI):** `send_welcome` manda 3 textos livres de uma vez.

**Cloud API:**
1. Gateway manda **1 template** (`ativacao_auto_ads`) com o nome do cliente.
2. Cliente toca **"Quero começar"** → entra no workflow do bot como inbound.
3. O bot, ao detectar esse primeiro contato pós-pagamento (status `pago_aguardando_meta`), dispara o resto da sequência (guia + pedido dos 2 dados Meta) como **texto livre**.

> As mensagens 2 e 3 do atual `build_welcome_msgs` (guia + instruções) **migram pro bot** (gatilho = cliente respondeu), não saem mais junto no push.

---

## Bodies da Cloud API (pros nós HTTP do n8n)

Base: `POST https://graph.facebook.com/v21.0/{{phone_number_id}}/messages`
Header: `Authorization: Bearer {{token}}` · `Content-Type: application/json`
(`phone_number_id` e `token` virão da tabela `auto_ads.config` — ver abaixo.)

**1) Template (push de boas-vindas — substitui o `send_welcome`):**
```json
{
  "messaging_product": "whatsapp",
  "to": "{{ $json.telefone }}",
  "type": "template",
  "template": {
    "name": "ativacao_auto_ads",
    "language": { "code": "pt_BR" },
    "components": [
      { "type": "body", "parameters": [ { "type": "text", "text": "{{ primeiro_nome }}" } ] }
    ]
  }
}
```

**2) Texto livre (substitui todos os outros `send_*` do bot — só vale dentro da janela de 24h):**
```json
{
  "messaging_product": "whatsapp",
  "to": "{{ $json.telefone }}",
  "type": "text",
  "text": { "body": {{ JSON.stringify($json.text) }} }
}
```

---

## Parse de ENTRADA (webhook) — UAZAPI vs Cloud API

A Cloud API manda payload diferente. Mapeamento pro parse de entrada (nos dois workflows):

| Dado | Cloud API (caminho no payload) |
|---|---|
| telefone do cliente | `entry[0].changes[0].value.messages[0].from` |
| nome do contato | `entry[0].changes[0].value.contacts[0].profile.name` |
| texto | `...messages[0].text.body` |
| tipo | `...messages[0].type` (`text` / `button` / `image` / `interactive`) |
| toque em botão (quick reply) | `...messages[0].button.text` **ou** `...messages[0].interactive.button_reply.title` |
| imagem (print) | `...messages[0].image.id` → baixar via `GET /v21.0/{media_id}` → `url` (com Bearer) |

> **Verificação do webhook (GET):** a Meta faz um `GET` com `hub.mode`, `hub.verify_token`, `hub.challenge`. O nó de webhook precisa responder o `hub.challenge` quando `hub.verify_token` bater. (Configurar no cutover.)

---

## Config a adicionar (tabela `auto_ads.config`)

```sql
INSERT INTO auto_ads.config (chave, valor) VALUES
  ('whatsapp_phone_number_id', '<preencher no cutover>'),
  ('whatsapp_token',           '<token permanente do system user>'),
  ('whatsapp_verify_token',    '<string aleatória que você define no webhook>')
ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor;
```

> Manter o token **só** no config/credential — nunca hardcoded no body dos nós (mesma regra dos outros segredos).

---

## Checklist de cutover (dia D)

- [ ] Fase 1: produto WhatsApp adicionado ao app + WABA criada
- [ ] Template `ativacao_auto_ads` **aprovado**
- [ ] Fase 2: UAZAPI desconectada + conta WhatsApp do número apagada
- [ ] Fase 3: número registrado → `phone_number_id` anotado
- [ ] Fase 4: token permanente gerado + webhook configurado (campo `messages`, `hub.challenge` ok)
- [ ] Config preenchida (`whatsapp_phone_number_id`, `whatsapp_token`, `whatsapp_verify_token`)
- [ ] Claude: backup dos 2 workflows → swap dos 15 nós de envio + parse de entrada → ativar
- [ ] Teste: reenviar webhook de pagamento → template chega → tocar botão → bot continua → enviar print → IA responde
```
