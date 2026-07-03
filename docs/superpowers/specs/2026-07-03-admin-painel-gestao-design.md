# Painel de Gestão de Assinaturas — Auto Ads

**Data:** 2026-07-03
**Status:** Aprovado (design) — pronto pra plano de implementação

## Objetivo

Um painel web protegido pra controlar as assinaturas do Auto Ads: ver clientes ativos, seus dados, data de entrada, extrato de pagamentos, e **desativar** um cliente manualmente (parando cobrança + gasto). Fecha o ciclo operacional do produto sem depender do Supabase cru.

## Não-objetivos (YAGNI)

- Multiusuário / RBAC (é senha única compartilhada).
- Editar dados do cliente pela tela (só leitura + desativar).
- Reativar pela tela nesta v1 (reativação é rara; faz-se manual/SQL por ora).
- Gráficos/BI. Só os números essenciais (total ativos, MRR estimado).

## Arquitetura

- **Frontend:** `admin.html` — página estática única (HTML/CSS/JS puro, sem framework), no padrão visual dark premium das demais páginas do Auto Ads. Vive em `/Users/renanreal/Desktop/Quirk Auto Ads - Páginas/admin.html` e sobe pro cPanel em `https://autoads.quirkgrowth.com.br/admin.html`.
- **Backend:** endpoints webhook no **n8n** (instância `n8n.quirkgrowth.online`), que já detém as credenciais Supabase + Asaas + Meta. Sem servidor novo.
- **A página é um cliente burro:** não contém dados nem a passphrase; tudo vem dos endpoints, e só com a passphrase correta.

```
admin.html  ──fetch(passphrase)──►  n8n webhooks  ──►  Supabase / Asaas / Meta
   (browser)                        (fronteira de segurança real)
```

## Segurança

- **Passphrase única** guardada em `auto_ads.config` (chave `admin_passphrase`).
- A passphrase é digitada na tela de login → mantida em `sessionStorage` → enviada em **todo** request (campo no body JSON, sobre HTTPS).
- **Todo endpoint revalida a passphrase server-side** antes de qualquer ação. Mismatch → HTTP 401 e zero dado.
- Honestidade: modelo simples, adequado a admin interno de baixo tráfego. Sem multiusuário. Por isso toda desativação é registrada em `auto_ads.audit_log`.
- A passphrase inicial será definida junto do Renan e inserida no config (não hardcoded no HTML nem nos nós).

## Endpoints n8n

Todos `POST`, corpo JSON com no mínimo `{ "passphrase": "..." }`. Todos começam por um check de passphrase; se falhar, respondem `401 {ok:false, erro:"unauthorized"}`.

### 1. `POST /webhook/admin-auth`
Valida só a passphrase (pra tela de login liberar o dashboard).
- **Resp OK:** `{ ok:true }`

### 2. `POST /webhook/admin-clientes`
Lista os clientes + contagem de campanhas.
- **Body:** `{ passphrase, somente_ativos?: boolean }` (default `true`)
- **Fonte:** Supabase. Query:
  ```sql
  SELECT c.telefone, c.nome_cliente, c.email, c.status, c.ativo,
         c.criado_em, c.subscription_started_at, c.subscription_canceled_at,
         c.ad_account_id, c.page_id, c.gateway, c.subscription_id,
         COUNT(cp.id) AS n_campanhas
  FROM auto_ads.clientes c
  LEFT JOIN auto_ads.campanhas cp ON cp.telefone = c.telefone
  WHERE ($somente_ativos = false OR c.status = 'ativo')
  GROUP BY c.telefone, c.nome_cliente, c.email, c.status, c.ativo,
           c.criado_em, c.subscription_started_at, c.subscription_canceled_at,
           c.ad_account_id, c.page_id, c.gateway, c.subscription_id
  ORDER BY c.criado_em DESC;
  ```
- **Resp OK:** `{ ok:true, clientes:[...], total_ativos, mrr_estimado }`
  - `mrr_estimado` = (nº de status `ativo`) × 497.

### 3. `POST /webhook/admin-extrato`
Extrato de pagamentos de um cliente, ao vivo do Asaas.
- **Body:** `{ passphrase, subscription_id }`
- **Fonte:** Asaas `GET /v3/payments?subscription={subscription_id}&limit=50` (header `access_token` = `asaas_api_key` do config). Usa `subscription_id` (não precisa de customer_id).
- **Resp OK:** `{ ok:true, pagamentos:[{ id, value, status, billingType, dueDate, paymentDate, invoiceUrl }] }`
- Se `subscription_id` vazio/nulo → `{ ok:true, pagamentos:[] }`.

### 4. `POST /webhook/admin-desativar`
Executa os 3 passos. Best-effort: cada passo roda e reporta seu resultado; um passo que falha **não** impede os outros.
- **Body:** `{ passphrase, telefone }`
- **Passos (executados nesta ordem — estanca dinheiro primeiro, grava status por último):**
  1. **Asaas:** `DELETE /v3/subscriptions/{subscription_id}` (cancela → para de cobrar). Se já cancelada/inexistente, trata como ok → `passo_asaas`
  2. **Meta:** busca `campaign_id`s em `auto_ads.campanhas WHERE telefone=$tel AND status != 'DELETED'`; pra cada um, `POST graph.facebook.com/v21.0/{campaign_id}` com `status=PAUSED` (token Meta do config). → `passo_meta` (com contagem de campanhas pausadas)
  3. **Supabase:** `UPDATE auto_ads.clientes SET status='inativo', ativo=false, subscription_canceled_at=now(), status_atualizado_em=now() WHERE telefone=$tel` → `passo_status`
  - Best-effort: cada passo é independente e reporta seu próprio resultado; um passo que falha não impede os demais.
- **Auditoria:** grava 1 linha em `auto_ads.audit_log` com a ação, telefone, e o resultado de cada passo.
- **Resp OK:** `{ ok:true, passo_status, passo_asaas, passo_meta:{ pausadas, total } }`

## Frontend (admin.html)

- **Tela de login:** campo de passphrase → chama `admin-auth`. Se ok, guarda em `sessionStorage` e mostra o dashboard.
- **Dashboard:**
  - Cabeçalho com **total de ativos** e **MRR estimado**.
  - Toggle **Ativos / Todos**.
  - Tabela: Nome · telefone · email · **data de entrada** (`subscription_started_at` ou `criado_em`) · status (badge colorido) · ad account · página · nº campanhas · gateway.
  - Clique na linha → **painel de detalhe** (drawer/modal): todos os dados + **extrato** (lazy via `admin-extrato`) + botão **Desativar**.
- **Desativar:** modal de confirmação listando os 3 efeitos + exige clicar "Confirmar desativação" → chama `admin-desativar` → mostra o resultado de cada passo (✓/✗). Atualiza a lista.
- **Erros:** 401 → volta pra tela de login com aviso "senha incorreta". Falha de rede/endpoint → mensagem clara, sem quebrar a tela.
- **Estilo:** reusa as variáveis/estética das páginas existentes (fundo `#001D41`, azul `#1D80FF`, ciano `#00E5FF`, verde `#39b54a`, fontes Sora + Poppins).

## Tratamento de erros

- Endpoints sempre retornam JSON estruturado; passphrase errada → 401.
- No desativar, cada passo reporta sucesso/falha independente (a UI mostra exatamente o que aconteceu).
- Falhas de Asaas/Meta são reportadas, não silenciadas, e não bloqueiam os demais passos.

## Testes

1. **Auth:** passphrase certa → dashboard; errada → 401, nenhum dado retornado por nenhum endpoint.
2. **Lista:** renderiza os 2 clientes de teste atuais (Renan `5511980838409`, Nathalie `5511980838444`); toggle Ativos/Todos funciona; nº de campanhas confere.
3. **Extrato:** contra uma `subscription_id` real do Asaas → lista os pagamentos.
4. **Desativar:** num cliente de teste → confere os 3 passos (status no Supabase, assinatura cancelada no Asaas, campanhas `PAUSED` na Meta) + linha no `audit_log`. Depois **restaura** o cliente de teste.
5. **Resiliência:** desativar um cliente sem `subscription_id` ou sem campanhas → não quebra; reporta cada passo coerentemente.

## Deploy

- Backend: criar/ativar o(s) workflow(s) n8n via API (padrão dos scripts `e_*`/`d_*`), com backup antes se editar workflow existente. Inserir `admin_passphrase` no `auto_ads.config`.
- Frontend: salvar `admin.html` na pasta das páginas + subir no cPanel (mesma pasta do subdomínio `autoads.quirkgrowth.com.br`).
- Versionar scripts + spec no repo `quirk_auto_ads` (git, branch `main`).
