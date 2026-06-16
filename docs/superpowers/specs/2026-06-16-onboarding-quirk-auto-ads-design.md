# Onboarding autônomo Quirk Auto Ads — design

**Data:** 2026-06-16
**Autor:** Renan Real (CEO Quirk Growth) + Claude
**Status:** Aprovado para implementação

---

## Problema

Hoje, adicionar um novo cliente ao Quirk Auto Ads é manual:

1. Renan recebe a notificação do lead em algum canal (form da LP, WhatsApp direto)
2. Cobra pagamento manualmente
3. Pede pro cliente compartilhar a Ad Account + Página da BM dele com a BM Quirk
4. Verifica manualmente se foi compartilhado
5. Insere uma linha em `auto_ads.clientes` via Supabase UI

Isso bloqueia escala. Pra vender pra centenas de corretores via LP + tráfego pago, o processo precisa ser autônomo: do clique de compra ao primeiro anúncio no ar, sem intervenção humana da Quirk.

## Objetivo

Cliente compra na LP, recebe boas-vindas no WhatsApp, é guiado por uma IA pra conectar a Meta dele à BM Quirk, sistema valida automaticamente, e libera o uso do Auto Ads. Tudo em português, com travas em cada fase pra evitar que cliente sem pagamento ou sem integração use o produto.

## Visão geral — 4 fases

```
A. GATE DE PAGAMENTO  →  B. ONBOARDING  →  C. REVISÃO  →  D. AUTO ADS
   (checa gateway)        (IA orienta)      (valida Meta)     (libera)
```

Cada fase tem um status no DB e o roteador no n8n decide pra onde mandar a mensagem do cliente baseado nesse status.

## Estados do cliente

Substituir `auto_ads.clientes.ativo: boolean` por `auto_ads.clientes.status: text` com 5 valores:

| Status | Significado |
|--------|-------------|
| `pago_aguardando_meta` | Pagamento confirmado, ainda não recebeu boas-vindas (criado pelo webhook gateway) |
| `em_onboarding` | Recebeu boas-vindas, está no fluxo guiado de conexão Meta |
| `em_revisao` | Cliente disse "PRONTO", sistema rodando validação Meta |
| `ativo` | Tudo OK — pode usar Auto Ads normalmente |
| `inativo` | Cancelou, pagamento falhou, ou foi desligado |

## Arquitetura

### Componentes novos

1. **Workflow n8n `Quirk Auto Ads — Webhook Gateway`** — recebe POST do Asaas, cria/atualiza cliente
2. **Roteador por status no workflow principal** — switch após `select_cliente` que decide o caminho
3. **Sub-fluxo Onboarding** — IA conversacional que orienta os 4 passos de conexão Meta + detecta `PRONTO`
4. **Sub-fluxo Revisão** — Code node que valida via Meta API + atualiza status
5. **Migration DB** — adiciona `status`, `email`, `gateway`, `subscription_id`, `subscription_started_at`, `subscription_canceled_at`

### Componentes existentes reutilizados

- `select_cliente` (já busca por telefone)
- `if_em_gestao` / fluxo conversacional Auto Ads completo
- `meta_access_token` (System User Token da BM Quirk)
- Toda a stack uazapi → n8n → Meta Ads API

### Schema da tabela `auto_ads.clientes` (depois da migration)

```sql
telefone                    text PRIMARY KEY
nome_cliente                text
email                       text                    -- NOVO
status                      text NOT NULL           -- NOVO (5 valores)

-- Dados Meta (preenchidos só após revisão OK)
ad_account_id               text
page_id                     text
wa_link                     text

-- Dados de assinatura (preenchidos pelo webhook gateway)
gateway                     text                    -- NOVO ('asaas' por enquanto)
subscription_id             text                    -- NOVO
subscription_started_at     timestamptz             -- NOVO
subscription_canceled_at    timestamptz             -- NOVO

-- Auditoria
criado_em                   timestamptz default now()
status_atualizado_em        timestamptz             -- NOVO

-- DEPRECATED (mantém por compat até migration completa)
ativo                       boolean                 -- removido após migration verify
```

### Fluxo no n8n (alto nível)

```
webhook (uazapi) → normalize_phone → select_cliente
                                          ↓
                                    switch_status
                                          ↓
       ┌──────────────┬────────────┬──────────────┬──────────────┐
       ↓              ↓            ↓              ↓              ↓
   não cadastrado  pago_aguard  em_onboarding  em_revisao     ativo
       ↓              ↓            ↓              ↓              ↓
   send_trava     send_welcome  agente_onbo  validar_meta  if_em_gestao
                                                ↓           (fluxo atual)
                                          OK / NÃO OK
```

E em paralelo:

```
webhook (asaas) → parse_payment → upsert_cliente_assinatura
                                       ↓
                               send_welcome_async (uazapi)
```

## Sub-fluxo Gate (Fase A)

Disparado quando `select_cliente` não acha o telefone OU acha mas `status='inativo'`.

- Sem pagamento → mensagem padrão: *"Você ainda não é assinante do Auto Ads. Pra ativar por R$ 497/mês, acesse autoads.quirkgrowth.com.br"*
- Inativo → *"Sua assinatura está pausada. Pra reativar, atualize o pagamento em [link cliente Asaas]"*

## Sub-fluxo Onboarding (Fase B)

Cliente com `status='pago_aguardando_meta'` recebe sequência de boas-vindas (mensagens disparadas pelo webhook gateway, não pela primeira mensagem do cliente). Após a mensagem 5 ser enviada com sucesso, status muda pra `em_onboarding` e a partir daí toda mensagem do cliente é processada pelo agente IA.

**Importante:** o roteador no n8n consulta APENAS o `status` no DB (fonte de verdade). Não consulta o gateway a cada mensagem — isso é caro e cria latência. Quando o gateway envia webhook de cancelamento, o status no DB é atualizado pra `inativo` e o roteador passa a tratar como inativo naturalmente.

Mensagens disparadas em sequência (com delay de 30s entre cada pra não parecer bot agressivo):

1. **Boas-vindas + contexto**: "Oi, [nome]! Sou o assistente do Quirk Auto Ads. Pagamento confirmado ✓. Antes de subir teu primeiro anúncio, preciso te ajudar a conectar tua conta Meta. Vai levar uns 10 minutos."

2. **Passo 1 (BM)**: "Primeiro: você precisa ter um Business Manager Meta. Acessa business.facebook.com/overview. Se já tem, ótimo. Se não, cria um no nome da tua empresa (ou nome próprio mesmo) — leva 1 min."

3. **Passo 2 (Ad Account)**: "Agora compartilha tua conta de anúncios com a BM Quirk. Tutorial: [link de vídeo + tutorial texto]. ID da BM Quirk: `1612905538806887`. Permissão: Gerenciar Campanhas."

4. **Passo 3 (Página)**: "Compartilha tua Página Facebook com a BM Quirk (mesma BM, mesma permissão)."

5. **Passo 4 (WhatsApp)**: "Por último, me manda 3 coisas em uma mensagem só:
   - Nome da tua Página Facebook
   - Teu link WhatsApp comercial (o número que vai aparecer no botão do anúncio)
   - Teu Ad Account ID (números só, encontra no Gerenciador)"

Durante essa fase, **toda mensagem do cliente é roteada pra um agente IA com prompt de onboarding**, não pro agente Auto Ads. O agente:
- Responde dúvidas sobre BM, Ad Account, página
- Repete passos se cliente pede
- Detecta gatilhos: `PRONTO`, `FIZ`, `TERMINEI` → marca `status='em_revisao'` e dispara Fase C
- **Bloqueia comandos do Auto Ads** (criar campanha, alterar, etc) e explica: "Termina o onboarding primeiro 😊"

### Prompt do agente onboarding (esboço)

```
Você é o assistente de onboarding do Quirk Auto Ads. Sua função é:

1. Conduzir o cliente pelos 4 passos de conexão Meta:
   - Criar/acessar Business Manager
   - Compartilhar Ad Account com BM Quirk (ID: 1612905538806887)
   - Compartilhar Página com BM Quirk
   - Reportar Nome Página + WhatsApp comercial + Ad Account ID

2. Tirar dúvidas em português, tom direto, sem firula.

3. Quando o cliente confirmar que terminou (mensagens tipo "PRONTO", "FIZ", "TERMINEI"),
   responda APENAS com a tag: <REVISAO_REQUEST/>

4. Se o cliente pedir pra criar/pausar/alterar campanha, responda:
   "Termina o onboarding primeiro — só consigo subir anúncio depois que sua Meta tiver conectada."

5. NUNCA finja que campanha subiu. NUNCA invente IDs ou métricas.
```

## Sub-fluxo Revisão (Fase C)

Disparado quando o agente onboarding emite `<REVISAO_REQUEST/>` → status muda pra `em_revisao` → Code node valida:

```javascript
// Pseudocódigo
const token = $('load_meta_token').first().json.valor;
const bmQuirkId = '1612905538806887';

// 1. Lista ad accounts compartilhadas com a BM Quirk
const adAccounts = await getJson(`/v25.0/${bmQuirkId}/client_ad_accounts?access_token=${token}`);

// 2. Lista páginas compartilhadas com a BM Quirk
const pages = await getJson(`/v25.0/${bmQuirkId}/client_pages?access_token=${token}`);

// 3. Pareia com o que o cliente reportou
const reportadoPeloCliente = parseRelatoCliente($('agente_onboarding').first().json);
// → { nome_pagina, ad_account_id, wa_link }

const adAccountEncontrada = adAccounts.find(a => a.account_id === reportadoPeloCliente.ad_account_id);
const paginaEncontrada = pages.find(p => p.name === reportadoPeloCliente.nome_pagina);

if (!adAccountEncontrada) return { ok: false, motivo: 'ad_account_nao_compartilhada' };
if (!paginaEncontrada)    return { ok: false, motivo: 'pagina_nao_compartilhada' };

// 4. Testa se consegue listar campanhas (sanity check de permissão)
const campanhas = await getJson(`/v25.0/act_${reportadoPeloCliente.ad_account_id}/campaigns?...`);
if (campanhas.error) return { ok: false, motivo: 'sem_permissao_campanhas' };

// 5. OK — atualiza cliente
await db.update({
  status: 'ativo',
  ad_account_id: reportadoPeloCliente.ad_account_id,
  page_id: paginaEncontrada.id,
  wa_link: reportadoPeloCliente.wa_link
});
```

Se falhou: agente onboarding manda mensagem explicando exatamente o que faltou (`motivo` é mapeado pra mensagem amigável) e volta pra `status='em_onboarding'`.

Se ok: dispara mensagem de "ativação confirmada" + orientação pra criar primeira campanha.

## Sub-fluxo Auto Ads (Fase D)

`status='ativo'` → fluxo atual do n8n é executado normalmente (`if_em_gestao` → tudo que já existe).

## Webhook do Asaas

Configurar em `config.asaas.com/notifications`:

- URL: `https://n8n.quirkgrowth.online/webhook/quirk-auto-ads-payment`
- Eventos:
  - `PAYMENT_CONFIRMED` (cobrança paga) → cria/atualiza cliente, status `pago_aguardando_meta`
  - `PAYMENT_REFUNDED` ou `SUBSCRIPTION_DELETED` → status `inativo`, pausa todas campanhas

Workflow `Quirk Auto Ads — Webhook Gateway` processa:

1. Valida HMAC do Asaas (header `asaas-access-token`)
2. Extrai customer phone + email + subscription_id
3. UPSERT em `auto_ads.clientes` com novo status
4. Dispara mensagem de boas-vindas via uazapi (se status novo for `pago_aguardando_meta`)
5. Se `inativo`: chama Meta API pra pausar todas as campanhas do cliente

## Tratamento de erros

- **Cliente não cadastrado manda mensagem antes de pagar**: gate manda link da LP, não tenta cadastrar
- **Webhook Asaas chega antes da mensagem do cliente**: cria cliente com `status=pago_aguardando_meta` e tenta mandar boas-vindas — se uazapi falhar (cliente nunca conversou com o número antes), agenda retry
- **Cliente paga mas nunca volta pra fazer onboarding**: cron diário (novo workflow simples) varre `pago_aguardando_meta` há +24h e remanda boas-vindas
- **Cliente reporta dados Meta errados**: agente onboarding repete passo, validação tenta de novo
- **Asaas envia webhook duplicado**: idempotência via `subscription_id` UNIQUE no DB

## Testabilidade

- **Webhook gateway**: testar com curl simulando payload Asaas
- **Onboarding**: testar com telefone fake, mock do gateway, conversar com a IA
- **Revisão**: testar com ad account + página real compartilhada com BM Quirk
- **Roteador**: testar cada status → cada caminho

## Escopo desta entrega

✅ Tudo descrito acima.
❌ Fora de escopo:
- Frontend admin pra gerenciar clientes (Renan ainda usa Supabase UI quando precisa)
- Multi-gateway (só Asaas por enquanto, mas a estrutura suporta swap)
- Recuperação automática de cobrança falhada (Asaas já faz dunning nativo)
- Dashboard pra cliente ver performance fora do WhatsApp (futuro)

## Decisões tomadas por padrão (sem consulta do user)

Como o user pediu para "lidar com problemas sem consultar":

- **Gateway**: Asaas (brasileiro, recorrência cartão + Pix, webhook robusto)
- **IA onboarding**: mesmo modelo do agente Auto Ads (Claude Sonnet), prompt separado
- **Idioma**: 100% português, tom direto sem firulas, igual ao agente Auto Ads atual
- **Migração de status**: `ativo=true` → `status='ativo'`, demais → `status='inativo'`. O único cliente atual (Renan) vira `ativo`.
- **Webhook signature**: validação obrigatória do header Asaas pra evitar disparos falsos
- **Mensagens em sequência**: delay de 30s entre cada (não parecer bot agressivo)
- **Detecção do "PRONTO"**: feita pelo agente IA (não regex simples) pra cobrir variações ("acabei", "finalizei", etc)
