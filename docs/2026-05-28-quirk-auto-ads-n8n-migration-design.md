# Quirk Auto Ads — Migração Make → n8n + Fase E embutida

**Data:** 2026-05-28
**Autor:** brainstorming Renan ↔ Claude
**Status:** Aprovado pra implementação
**Escopo:** Opção B (migração 1:1 + Fase E: token centralizado, logs estruturados, retry)

---

## 1. Por quê migrar

O Make.com está rodando o cenário Quirk Auto Ads desde mai/2026. Após 14 versões iteradas, a Fase D (criação de campanha CTWA) está quase fechada — D.1 e D.2 passam, D.3/D.4 trava por falta de método de pagamento (não-código). Mas o uso continuado revelou três fricções estruturais:

1. **Custo em escala**: Make cobra por operations. Projeção a 100 clientes ativos: ~90k ops/mês → ~$99/mês no plano Teams; a 500 clientes: ~$300-500/mês. n8n self-hosted: $0 (servidor `n8n.quirkgrowth.online` já rodando para outros workflows da Quirk).

2. **Concorrência limitada**: Make Pro tem 2-5 execuções simultâneas. Em picos com múltiplos clientes mandando mensagem ao mesmo tempo, vai gerar fila perceptível. n8n self-hosted: ilimitado.

3. **Ciclo de edição lento**: API do Make só aceita blueprint inteiro como input. Blueprint do Quirk Auto Ads tem ~180KB, excede limite das tool calls do Claude. Resultado: cada mudança requer ciclo manual de "Claude gera JSON → Renan baixa → importa → Save → corrige scheduling resetado → testa". n8n tem API REST que aceita edição node-por-node, eliminando esse ciclo.

Os pontos 1 e 2 são econômicos/escalabilidade. O ponto 3 é o que mais impacta velocidade hoje.

---

## 2. Decisões fechadas no brainstorming

| Decisão | Escolha | Por quê |
|---|---|---|
| Filosofia | **B** — migração 1:1 + Fase E embutida (token centralizado, logs, retry) | Aproveita a janela de migração pra resolver gaps documentados sem explodir escopo. Fase F (relatórios) fica out-of-scope, vira spec separado. |
| Acesso ao n8n | **A** — Claude com API key dedicada | Elimina ciclo "exporta-importa-save" do Make. Renan revoga key quando quiser. |
| Storage | **C** — Supabase Postgres em schema `auto_ads` isolado | Credencial já existe (`Supabase SDR Quirk` no n8n). SQL real, queries flexíveis, gratuito até 500MB. Schema isolado pra não tocar tabelas existentes. |
| WhatsApp | **Manter UAZAPI** | Evolution API teve problema histórico. UAZAPI já validado, sem motivo pra mudar. |
| Cutover | **A** — desliga Make, liga n8n | Renan é único testando hoje, multi-cliente real ainda não saiu. Rollback pro Make em 30s se quebrar. |
| Versão do prompt | **Consolidação direta v13 + v14 + fix do mod 39** | Sem versionamento incremental no n8n; começa direto na versão final consolidada. |
| Node de IA | **`n8n-nodes-base.anthropicAi`** nativo | Mais limpo que HTTP genérico. n8n versão recente suporta. |

---

## 3. Arquitetura geral

Um único workflow no n8n com duas branches internas roteadas por tipo de mensagem.

```
UAZAPI webhook (POST → n8n)
    ↓
[Webhook Trigger node]
    ↓
[Switch: $json.message.type]
   ├── "text"  → fluxo TEXTO (conversa + classifier + execução condicional)
   └── "media" → fluxo MÍDIA (download + persiste + confirma)
```

**Storage:** Supabase Postgres existente, schema `auto_ads` (isolado de `public` e outras tabelas).

**Credenciais:** centralizadas via Credentials do n8n e variáveis de ambiente do servidor.

**Componentes:**
- 1 workflow ativo `Quirk Auto Ads`
- 4 tabelas em `auto_ads` schema
- 3 credentials n8n (Anthropic, UAZAPI HTTP header, Postgres)
- 3 variáveis de ambiente (META_ACCESS_TOKEN, ANTHROPIC_API_KEY, UAZAPI_TOKEN)

---

## 4. Schema Supabase

```sql
CREATE SCHEMA IF NOT EXISTS auto_ads;

-- ──────────────────────────────────────────────
-- Cadastro multi-cliente
-- Substitui o Data Store do Make (registros por telefone)
-- O access_token NÃO fica aqui (saiu pra variável de ambiente — Fase E)
-- ──────────────────────────────────────────────
CREATE TABLE auto_ads.clientes (
  telefone TEXT PRIMARY KEY,           -- formato "5511980838409" (só dígitos, normalizado)
  ad_account_id TEXT NOT NULL,         -- conta de anúncio Meta do cliente (sem prefixo act_)
  page_id TEXT NOT NULL,               -- página Facebook do cliente
  wa_link TEXT NOT NULL,               -- "https://wa.me/<numero>" do WhatsApp do cliente
  nome_cliente TEXT,                   -- opcional, pra logs humanos
  ativo BOOLEAN DEFAULT TRUE,
  criado_em TIMESTAMPTZ DEFAULT NOW()
);

-- ──────────────────────────────────────────────
-- Conversas (memória + criativos)
-- 1:1 com clientes — chave estrangeira no telefone
-- ──────────────────────────────────────────────
CREATE TABLE auto_ads.conversas (
  telefone TEXT PRIMARY KEY REFERENCES auto_ads.clientes(telefone),
  historico TEXT DEFAULT '',           -- últimos 20 turnos separados por |||TURN|||
  criativo_url TEXT DEFAULT '',        -- URLs dos criativos recebidos (uma por linha)
  ultima_atualizacao TIMESTAMPTZ DEFAULT NOW()
);

-- ──────────────────────────────────────────────
-- Tracking de campanhas criadas — Fase E
-- Permite auditoria, relatório, troubleshooting
-- ──────────────────────────────────────────────
CREATE TABLE auto_ads.campanhas (
  id BIGSERIAL PRIMARY KEY,
  telefone TEXT REFERENCES auto_ads.clientes(telefone),
  nome_campanha TEXT,
  ad_account_id TEXT,
  campaign_id TEXT,                    -- ID retornado D.1
  adset_id TEXT,                       -- ID retornado D.2
  creative_id TEXT,                    -- ID retornado D.3
  ad_id TEXT,                          -- ID retornado D.4
  status TEXT,                         -- "PAUSED", "CREATED", "FAILED"
  json_extrator JSONB,                 -- snapshot do JSON estruturado gerado pelo Extrator
  criada_em TIMESTAMPTZ DEFAULT NOW()
);

-- ──────────────────────────────────────────────
-- Audit log — Fase E
-- Eventos importantes pra debug e observabilidade
-- ──────────────────────────────────────────────
CREATE TABLE auto_ads.audit_log (
  id BIGSERIAL PRIMARY KEY,
  telefone TEXT,                       -- pode ser NULL pra eventos não-cliente
  evento TEXT NOT NULL,                -- "msg_recebida", "campanha_criada", "erro_meta", "erro_validacao", etc.
  detalhes JSONB,                      -- payload contextual
  ts TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para queries de relatório (Fase F futuro)
CREATE INDEX idx_campanhas_telefone ON auto_ads.campanhas(telefone);
CREATE INDEX idx_campanhas_criada ON auto_ads.campanhas(criada_em DESC);
CREATE INDEX idx_audit_telefone ON auto_ads.audit_log(telefone);
CREATE INDEX idx_audit_ts ON auto_ads.audit_log(ts DESC);
CREATE INDEX idx_audit_evento ON auto_ads.audit_log(evento);
```

**Diferenças vs Data Store do Make:**
- `access_token` saiu da tabela `clientes` (centralizado em ENV — Fase E)
- Separação `clientes` ↔ `conversas` (no Make estava tudo junto)
- Adição de `campanhas` e `audit_log` (não existiam no Make)

---

## 5. Workflow detalhado

### 5.1 Branch TEXTO

```
[Webhook Trigger]
   ↓
[Function: normaliza telefone]                ← remove +, espaços, hífen do chat.phone
   ↓
[Postgres SELECT FROM auto_ads.clientes WHERE telefone = $1]
   ↓
[IF cliente.length === 0]                    ← cliente não cadastrado
   ├── TRUE  → [HTTP UAZAPI: "olá, esse número não está cadastrado. Contate a Quirk pra ativar"]
   │           → [Postgres INSERT audit_log evento='nao_cadastrado'] → [END]
   └── FALSE ↓
[Postgres SELECT FROM auto_ads.conversas WHERE telefone = $1]
   ↓
[Anthropic — agente principal]                ← system: prompt v13/v14 mesclado
   │                                           ← user: histórico + nova mensagem
   ↓
[Anthropic — classifier]                      ← decide CONFIRMADO/PENDENTE
   │                                           ← system: prompt classifier v9
   ↓
[Function: monta novo histórico]              ← concatena truncado em últimos 20 turnos com |||TURN|||
   ↓
[Postgres UPSERT auto_ads.conversas SET historico = $1]
   ↓
[HTTP UAZAPI POST /send/text]                 ← responde ao cliente
   ↓
[IF classifier.result === "CONFIRMADO"]
   ├── FALSE → [Postgres INSERT audit_log evento='msg_processada'] → [END]
   └── TRUE  ↓
[Anthropic — extrator]                        ← gera JSON estruturado da campanha
   ↓
[Function: parse JSON + validate]             ← roda as 9 validações + retorna {ok, motivo}
   ↓
[IF validation.ok === false]
   ├── TRUE  → [Postgres INSERT audit_log 'erro_validacao' + detalhes]
   │           → [HTTP UAZAPI: alerta pra equipe Quirk com motivo]
   │           → [HTTP UAZAPI: "campanha em revisão, equipe vai te chamar"] → [END]
   └── FALSE ↓
[HTTP POST graph.facebook.com/v25.0/act_{{ad_account_id}}/campaigns]    ← D.1
   │   (retry 3x com backoff 2/4/8s, continue on fail)
   ↓
[IF D.1 falhou]
   ├── TRUE  → [Postgres INSERT audit_log 'erro_meta_d1'] → [HTTP UAZAPI: alerta Quirk] → [END]
   └── FALSE ↓
[HTTP POST .../adsets]                       ← D.2 (mesmo padrão retry)
   ↓
[IF D.2 falhou → mesmo tratamento de erro]
   ↓
[HTTP POST .../adcreatives]                  ← D.3
   ↓
[IF D.3 falhou → mesmo tratamento]
   ↓
[HTTP POST .../ads]                          ← D.4
   ↓
[IF D.4 falhou → mesmo tratamento]
   ↓
[Postgres INSERT auto_ads.campanhas]         ← grava todos os IDs Meta + JSON snapshot
   ↓
[Postgres INSERT audit_log 'campanha_criada']
   ↓
[HTTP UAZAPI: "Campanha 'XYZ' criada em PAUSED. Revise no Ads Manager."]
   ↓
[END]
```

### 5.2 Branch MÍDIA

```
[Webhook Trigger]
   ↓
[Switch: message.type === "media"]
   ↓
[Function: normaliza telefone]
   ↓
[Postgres SELECT FROM auto_ads.clientes]    ← valida cadastro
   ↓
[IF cliente.length === 0]
   ├── TRUE  → [HTTP UAZAPI: "número não cadastrado"] → [END]
   └── FALSE ↓
[HTTP POST quirkgrowth.uazapi.com/message/download]
   │   body: { "id": "{{ $json.message.id }}" }   ← FIX do hardcode antigo
   │   headers: { "token": "{{ $env.UAZAPI_TOKEN }}", "Content-Type": "application/json" }
   ↓
[Postgres SELECT criativo_url FROM auto_ads.conversas]
   ↓
[Function: anexa novo URL ao criativo_url existente]
   │   `${criativo_url_antigo}${$json.data.fileURL}\n`
   ↓
[Postgres UPSERT auto_ads.conversas SET criativo_url = $1]
   ↓
[Function: anexa nota no histórico]
   │   `${historico}|||TURN|||[Sistema: criativo recebido em ${now}]`
   ↓
[Postgres UPSERT auto_ads.conversas SET historico = $1]
   ↓
[HTTP UAZAPI: "criativo recebido, vou usar nessa campanha"]
   ↓
[Postgres INSERT audit_log 'criativo_recebido']
   ↓
[END]
```

---

## 6. Credenciais e variáveis de ambiente

### 6.1 n8n Credentials (UI)

| Nome | Tipo | Conteúdo |
|---|---|---|
| `Quirk Anthropic` | Anthropic API | `sk-ant-...` |
| `Quirk Supabase Postgres` | Postgres | host + db + auth (já existe como "Supabase SDR Quirk", reusa) |

### 6.2 Variáveis de ambiente n8n (`.env` do servidor)

```bash
# Adicionar ao .env do n8n e restart
META_ACCESS_TOKEN=EAAqtFmgGCYkB...
ANTHROPIC_API_KEY=sk-ant-...
UAZAPI_TOKEN=8120269d-c572-4adc-b8a8-ddeda2177d99
```

**Por que ambiente, não Credential do n8n?**
- META_ACCESS_TOKEN: usado em headers de chamadas HTTP genéricas (D.1-D.4). n8n permite acessar via `{{ $env.NOME }}` nos expression fields.
- ANTHROPIC_API_KEY: idealmente como Credential do n8n (UI), mas pode duplicar como ENV se conveniente.
- UAZAPI_TOKEN: usado em header `token` das chamadas HTTP UAZAPI. Mesmo padrão.

### 6.3 Mudança crítica vs Make

No Make, o `access_token` ficava no Data Store, **duplicado por cliente**. Renovar token = atualizar N registros.

No n8n, fica em **um único lugar** (variável ambiente). Renovação: trocar uma variável + restart n8n.

---

## 7. Validação determinística (Function node)

As 9 condições da Fase C do Make portadas pra JavaScript no node Function:

```javascript
const json = items[0].json.json_extrator;  // output do Anthropic Extrator parseado
const cliente = items[0].json.cliente;
const conversa = items[0].json.conversa;

const errors = [];

if (!json.campanha?.verba_diaria || json.campanha.verba_diaria < 10) errors.push('verba_diaria < 10');
if (json.campanha.verba_diaria > 100) errors.push('verba_diaria > 100');
if (!json.campanha.objetivo_meta) errors.push('objetivo_meta vazio');
if (!json.conjunto?.geo) errors.push('geo vazio');
if (!json.publico_escolhido) errors.push('publico_escolhido vazio');
if (!conversa.criativo_url) errors.push('criativo_url vazio');
if (!cliente.ad_account_id) errors.push('ad_account_id vazio');
if (!json.targeting_meta) errors.push('targeting_meta vazio');
if (!json.targeting_meta?.geo_locations) errors.push('geo_locations vazio');

return [{ json: { ok: errors.length === 0, motivos: errors, json_extrator: json } }];
```

---

## 8. Error handling e retry

### 8.1 Retry nos HTTP Meta (D.1-D.4)

Cada node HTTP da Meta tem:
- **Continue on Fail**: true
- **Retry on Fail**: true, 3 tentativas, backoff 2s/4s/8s
- IF logo depois checa `$json.error`. Se erro persistente → branch de tratamento.

### 8.2 Branch de erro Meta

```
[IF Meta retornou error]
   ↓
[Postgres INSERT auto_ads.audit_log]         ← evento='erro_meta_d{N}', detalhes={error, body, etc}
   ↓
[HTTP UAZAPI: alerta canal Quirk]            ← número interno da equipe
   │   "ALERTA: campanha de {{telefone}} falhou no D.{{N}}: {{error.message}}"
   ↓
[HTTP UAZAPI cliente]                        ← "sua campanha está em revisão, equipe vai te chamar"
   ↓
[END]
```

### 8.3 Erros não-Meta (UAZAPI down, Anthropic timeout, Postgres unreachable)

- n8n Settings → Workflow Settings → Error Workflow: criar workflow `Quirk Auto Ads — Error Handler` que recebe execução com erro e notifica via WhatsApp.

---

## 9. Plano de migração

| # | Passo | Responsável | Reversível? |
|---|---|---|---|
| 1 | Criar schema `auto_ads` + 4 tabelas no Supabase via Postgres MCP | Claude | Sim (DROP SCHEMA) |
| 2 | Inserir cadastro de teste (telefone 5511980838409) | Claude | Sim |
| 3 | Adicionar 3 variáveis de ambiente no `.env` do n8n | Renan (SSH) | Sim |
| 4 | Reiniciar n8n pra carregar variáveis | Renan | — |
| 5 | Criar workflow vazio "Quirk Auto Ads" via n8n API | Claude | Sim (DELETE workflow) |
| 6 | Adicionar nodes do fluxo TEXTO via API | Claude | Sim |
| 7 | Adicionar nodes do fluxo MÍDIA via API | Claude | Sim |
| 8 | Validar workflow lendo via API | Claude | — |
| 9 | Ativar workflow (Active = true) via API | Claude | Sim |
| 10 | Capturar webhook URL gerada | Claude (via API) | — |
| 11 | Trocar webhook URL no painel UAZAPI | Renan | Sim |
| 12 | Desativar cenário Make via API | Claude | Sim |
| 13 | Teste end-to-end: enviar mensagem real pelo WhatsApp pessoal | Renan | — |
| 14 | Iterar fix de bugs via n8n API direta | Claude | Sim |
| 15 | Validar campanha aparece no Ads Manager em PAUSED | Renan | — |

**Critério de cutover bem-sucedido:** Renan envia mensagem → fluxo completo → campanha em PAUSED no Ads Manager com targeting correto (Pub Quirk + cidade+raio) + sem erros no audit_log.

---

## 10. Critérios de sucesso

A migração é considerada concluída quando, em testes end-to-end:

1. **Mensagem texto** dispara conversa, agente responde, classifier funciona, mensagem chega no WhatsApp.
2. **Imagem enviada** é baixada, persistida em `criativo_url`, confirmada ao cliente.
3. **Confirmação `CONFIRMADO`** dispara fluxo execução, todas as 9 validações passam, D.1-D.4 criam campanha em PAUSED.
4. **Campanha aparece no Ads Manager** com:
   - Nome correto (definido pelo cliente)
   - Targeting refinado (Pub Quirk + interesses reais + cidade+raio)
   - Verba correta
   - Status PAUSED
5. **Log na tabela `auto_ads.campanhas`** com todos os IDs Meta.
6. **Sem entradas em `auto_ads.audit_log` com evento de erro** durante o fluxo bem-sucedido.

---

## 11. Riscos conhecidos

| Risco | Probabilidade | Mitigação |
|---|---|---|
| n8n versão não suporta nodes esperados (Anthropic, etc) | Baixa | Verificar versão via API antes de criar; se faltar, usar HTTP genérico |
| Webhook URL do n8n não acessível pela UAZAPI (firewall) | Baixa | URL é pública (`n8n.quirkgrowth.online`); testar com curl antes de cutover |
| Variável de ambiente META_ACCESS_TOKEN não carrega após restart | Média | Validar com node Function que imprime `$env.META_ACCESS_TOKEN.substring(0,10)` antes do D.1 |
| Postgres lento → fluxo timeout (n8n default 5min) | Baixa | Supabase é rápido, queries são simples (PK lookup); aumentar timeout do workflow se necessário |
| Edição via API quebra workflow ativo durante teste do Renan | Média | Sempre criar versão "draft" antes de ativar; rollback via Make em 30s se preciso |
| Race condition: 2 mensagens do mesmo cliente simultâneas → conflito em `conversas` | Baixa | n8n executa em ordem; Postgres `UPSERT` é atômico |
| Tokens Meta expiram durante migração | Baixa | System User Token "never expires"; mas validar antes de migrar |

---

## 12. Out of scope

Coisas conscientemente NÃO incluídas neste design — viram specs separados depois:

- **Fase F — Relatórios sob demanda** (cliente pede "/relatório campanha XYZ" e recebe métricas da Meta API). Mais complexo, exige Ads Insights API + formatação. Spec separado quando MVP estiver estável.
- **Edição de campanhas existentes** (pausar, alterar orçamento, etc). Já documentado em conversa anterior com Renan como Fase F'.
- **Onboarding automático de cliente novo via WhatsApp**. Hoje é manual via INSERT no Supabase. Spec separado.
- **Migração das outras automações do n8n já existentes** (Comercial Quirk, Google Ads, etc). Foco: só Quirk Auto Ads.
- **Dashboard/UI de monitoramento**. Por enquanto, queries SQL ad-hoc no Supabase.

---

## 13. Próximo passo

Spec aprovado pelo Renan → invocar `superpowers:writing-plans` skill pra detalhar passo a passo da implementação (cada item da seção 9 com sub-passos verificáveis).
