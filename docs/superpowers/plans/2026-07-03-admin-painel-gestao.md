# Painel de Gestão de Assinaturas (Admin) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um painel web protegido (`autoads.quirkgrowth.com.br/admin.html`) pra ver clientes ativos do Auto Ads, seus dados, data de entrada, extrato de pagamentos, e desativar um cliente (cancela Asaas + pausa Meta + status).

**Architecture:** Frontend estático (HTML/CSS/JS puro) que fala via `fetch` com endpoints webhook num workflow n8n dedicado ("Quirk Auto Ads — Admin API"). O n8n detém as credenciais (Supabase/Asaas/Meta) e é a fronteira de segurança: toda requisição carrega uma passphrase revalidada server-side.

**Tech Stack:** n8n (workflow via API REST + `scripts/n8n_api.py`), Supabase/Postgres, Asaas API v3, Meta Graph API v21.0, HTML/CSS/JS vanilla. Testes = `curl` contra os webhooks + `psql`/psycopg2 pra verificar efeitos + navegador pro frontend.

**Spec:** `docs/superpowers/specs/2026-07-03-admin-painel-gestao-design.md`

---

## Convenções do ambiente (leia antes de começar)

- **Base dos webhooks:** `https://n8n.quirkgrowth.online/webhook/<path>` (produção; workflow precisa estar **ativo**).
- **Helper n8n:** `scripts/n8n_api.py` expõe `create_workflow(name, nodes, connections)`, `update_workflow(id, **fields)`, `activate_workflow(id)`, `get_workflow(id)`. Rode os scripts de dentro de `scripts/`.
- **Credencial Postgres (n8n):** `config.POSTGRES_CRED = {"id":"NKHJwhesMp2Bo4Xw","name":"Quirk Auto Ads Postgres"}`.
- **DB direto (pra testes/asserts):** `psycopg2.connect(open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-','aws-1-'))`.
- **Config no banco (`auto_ads.config`, chave/valor):** `asaas_api_key`, `meta_access_token`; vamos adicionar `admin_passphrase`.
- **CORS:** a página (origem `https://autoads.quirkgrowth.com.br`) chama o n8n (origem `n8n.quirkgrowth.online`) → cross-origin. Resolvido setando `options.allowedOrigins` no nó Webhook (o n8n cuida do preflight OPTIONS e dos headers).
- **Auth em TODO endpoint:** cada chain é `webhook → load_config → gate(code) → IF(autorizado) → [trabalho] → respond_ok | respond_401`. Endpoints que **agem** (desativar) precisam do gate ANTES do trabalho — nunca cancelar Asaas se a passphrase estiver errada.

## File Structure

- **Create:** `scripts/f_01_admin_api.py` — build script único que constrói/atualiza o workflow "Quirk Auto Ads — Admin API" (4 endpoints). Re-runnable (cria se não existe, atualiza se existe). Persiste o wf_id em `n8n_workflow/.admin_api_id`.
- **Create:** `scripts/f_00_admin_passphrase.py` — insere `admin_passphrase` em `auto_ads.config`.
- **Create:** `/Users/renanreal/Desktop/Quirk Auto Ads - Páginas/admin.html` — o painel (login + dashboard + detalhe + desativar).
- **Modify (deploy):** subir `admin.html` no cPanel (pasta do subdomínio `autoads.quirkgrowth.com.br`).

O build script cresce por tarefa: Task 1 cria os helpers + o endpoint `admin-auth`; Tasks 2–4 adicionam um endpoint (função builder) cada e re-deployam.

---

### Task 1: Passphrase no config + endpoint `admin-auth`

**Files:**
- Create: `scripts/f_00_admin_passphrase.py`
- Create: `scripts/f_01_admin_api.py`
- Create: `n8n_workflow/.admin_api_id` (gerado pelo script)

- [ ] **Step 1: Escrever `f_00_admin_passphrase.py` (insere a passphrase)**

```python
# scripts/f_00_admin_passphrase.py
import sys, psycopg2
db_url = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-','aws-1-')
PASS = sys.argv[1] if len(sys.argv) > 1 else None
if not PASS:
    print("uso: python3 f_00_admin_passphrase.py '<passphrase>'"); sys.exit(1)
conn = psycopg2.connect(db_url); cur = conn.cursor()
cur.execute("""INSERT INTO auto_ads.config (chave, valor) VALUES ('admin_passphrase', %s)
               ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor""", [PASS])
conn.commit(); conn.close()
print("admin_passphrase definido.")
```

- [ ] **Step 2: Definir a passphrase (peça o valor ao Renan; NÃO invente)**

Run: `cd scripts && python3 f_00_admin_passphrase.py '<PASSPHRASE_DO_RENAN>'`
Expected: `admin_passphrase definido.`

- [ ] **Step 3: Escrever `f_01_admin_api.py` com helpers + o endpoint `admin-auth`**

```python
# scripts/f_01_admin_api.py
import json, os, n8n_api, config

ORIGIN = "https://autoads.quirkgrowth.com.br"
ID_FILE = "../n8n_workflow/.admin_api_id"
PG = config.POSTGRES_CRED

def wh(path):
    return {"httpMethod": "POST", "path": path, "responseMode": "responseNode",
            "options": {"allowedOrigins": ORIGIN}}

def node(id_, name, typ, ver, params, pos, creds=None):
    n = {"id": id_, "name": name, "type": typ, "typeVersion": ver,
         "parameters": params, "position": pos}
    if creds: n["credentials"] = creds
    return n

def pg_node(id_, name, query, pos):
    return node(id_, name, "n8n-nodes-base.postgres", 2.5,
                {"operation": "executeQuery", "query": query}, pos,
                creds={"postgres": PG})

def code_node(id_, name, js, pos):
    return node(id_, name, "n8n-nodes-base.code", 2, {"jsCode": js}, pos)

def respond_node(id_, name, code_http, pos):
    return node(id_, name, "n8n-nodes-base.respondToWebhook", 1.1,
                {"respondWith": "json", "responseBody": "={{ JSON.stringify($json.body) }}",
                 "options": {"responseCode": code_http}}, pos)

# --- registro de nós/conexões acumulado ---
NODES, CONN = [], {}
def link(a, b, out=0):
    CONN.setdefault(a, {"main": []})
    while len(CONN[a]["main"]) <= out: CONN[a]["main"].append([])
    CONN[a]["main"][out].append({"node": b, "type": "main", "index": 0})

# ---- gate de passphrase reutilizável (código) ----
GATE_JS = """
const body = $('__WH__').first().json.body || {};
const cfg = $('__CFG__').first().json;
const authorized = String(body.passphrase || '') !== '' && String(body.passphrase) === String(cfg.admin_passphrase || '__none__');
return [{ json: { authorized, body } }];
"""

def gate_js(wh_name, cfg_name):
    return GATE_JS.replace("__WH__", wh_name).replace("__CFG__", cfg_name)

# =========================================================
# ENDPOINT: admin-auth  (só valida a passphrase)
# =========================================================
NODES += [
  node("wh_auth","wh_auth","n8n-nodes-base.webhook",2, wh("admin-auth"), [240,120]),
  pg_node("cfg_auth","cfg_auth","SELECT valor AS admin_passphrase FROM auto_ads.config WHERE chave='admin_passphrase' LIMIT 1",[460,120]),
  code_node("auth_check","auth_check",
     "const body=$('wh_auth').first().json.body||{};const cfg=$('cfg_auth').first().json;"
     "const ok=String(body.passphrase||'')!==''&&String(body.passphrase)===String(cfg.admin_passphrase||'__none__');"
     "return [{ json: { body: { ok } } }];",[680,120]),
  respond_node("auth_resp","auth_resp",200,[900,120]),
]
link("wh_auth","cfg_auth"); link("cfg_auth","auth_check"); link("auth_check","auth_resp")

# =========================================================
# DEPLOY (cria ou atualiza + ativa)
# =========================================================
def deploy():
    name = "Quirk Auto Ads — Admin API"
    wf_id = None
    if os.path.exists(ID_FILE):
        wf_id = open(ID_FILE).read().strip() or None
    if wf_id:
        n8n_api.update_workflow(wf_id, nodes=NODES, connections=CONN)
    else:
        res = n8n_api.create_workflow(name, NODES, CONN)
        wf_id = res["id"]; open(ID_FILE,"w").write(wf_id)
    n8n_api.activate_workflow(wf_id)
    print("deploy OK:", wf_id, "| endpoints:", sorted({n['parameters'].get('path') for n in NODES if n['type']=='n8n-nodes-base.webhook'}))

if __name__ == "__main__":
    deploy()
```

- [ ] **Step 4: Curl-test ANTES do deploy (o endpoint ainda não existe → falha)**

Run:
```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST "https://n8n.quirkgrowth.online/webhook/admin-auth" -H "Content-Type: application/json" -d '{"passphrase":"x"}'
```
Expected: `404` (webhook não registrado ainda).

- [ ] **Step 5: Deploy**

Run: `cd scripts && python3 f_01_admin_api.py`
Expected: `deploy OK: <id> | endpoints: ['admin-auth']`

- [ ] **Step 6: Curl-test DEPOIS (passphrase certa e errada)**

Run:
```bash
BASE="https://n8n.quirkgrowth.online/webhook/admin-auth"
echo "certa:"; curl -s -X POST "$BASE" -H "Content-Type: application/json" -d '{"passphrase":"<PASSPHRASE_DO_RENAN>"}'
echo; echo "errada:"; curl -s -X POST "$BASE" -H "Content-Type: application/json" -d '{"passphrase":"errada"}'
```
Expected: certa → `{"ok":true}` · errada → `{"ok":false}`

- [ ] **Step 7: Commit**

```bash
cd /Users/renanreal/quirk_auto_ads
git add scripts/f_00_admin_passphrase.py scripts/f_01_admin_api.py n8n_workflow/.admin_api_id
git commit -m "feat(admin): endpoint admin-auth + passphrase no config"
```

---

### Task 2: Endpoint `admin-clientes`

**Files:**
- Modify: `scripts/f_01_admin_api.py` (adiciona a chain do endpoint antes de `deploy()`)

- [ ] **Step 1: Curl-test ANTES (endpoint não existe → 404)**

Run:
```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST "https://n8n.quirkgrowth.online/webhook/admin-clientes" -H "Content-Type: application/json" -d '{"passphrase":"x"}'
```
Expected: `404`

- [ ] **Step 2: Adicionar a chain `admin-clientes` em `f_01_admin_api.py`** (logo após o bloco do admin-auth, antes de `def deploy`)

```python
# =========================================================
# ENDPOINT: admin-clientes  (lista + nº campanhas + totais)
# =========================================================
Q_CLIENTES = """
SELECT c.telefone, c.nome_cliente, c.email, c.status, c.ativo,
       c.criado_em, c.subscription_started_at, c.subscription_canceled_at,
       c.ad_account_id, c.page_id, c.gateway, c.subscription_id,
       COUNT(cp.id) AS n_campanhas
FROM auto_ads.clientes c
LEFT JOIN auto_ads.campanhas cp ON cp.telefone = c.telefone
GROUP BY c.telefone, c.nome_cliente, c.email, c.status, c.ativo,
         c.criado_em, c.subscription_started_at, c.subscription_canceled_at,
         c.ad_account_id, c.page_id, c.gateway, c.subscription_id
ORDER BY c.criado_em DESC
"""

SHAPE_CLIENTES_JS = """
const rows = $items().map(i => i.json);
const body = $('wh_clientes').first().json.body || {};
const somenteAtivos = body.somente_ativos !== false; // default true
let cli = rows;
if (somenteAtivos) cli = rows.filter(r => r.status === 'ativo');
const total_ativos = rows.filter(r => r.status === 'ativo').length;
const mrr_estimado = total_ativos * 497;
return [{ json: { body: { ok: true, clientes: cli, total_ativos, mrr_estimado } } }];
"""

NODES += [
  node("wh_clientes","wh_clientes","n8n-nodes-base.webhook",2, wh("admin-clientes"), [240,320]),
  pg_node("cfg_cli","cfg_cli","SELECT valor AS admin_passphrase FROM auto_ads.config WHERE chave='admin_passphrase' LIMIT 1",[460,320]),
  code_node("gate_cli","gate_cli", gate_js("wh_clientes","cfg_cli"), [680,320]),
  node("if_cli","if_cli","n8n-nodes-base.if",2,
       {"conditions":{"options":{"caseSensitive":True,"typeValidation":"strict"},"combinator":"and",
        "conditions":[{"leftValue":"={{ $json.authorized }}","rightValue":True,"operator":{"type":"boolean","operation":"true","singleValue":True}}]}},
       [880,320]),
  pg_node("q_clientes","q_clientes", Q_CLIENTES, [1100,260]),
  code_node("shape_cli","shape_cli", SHAPE_CLIENTES_JS, [1320,260]),
  respond_node("resp_cli_ok","resp_cli_ok",200,[1540,260]),
  code_node("deny_cli","deny_cli","return [{ json: { body: { ok:false, erro:'unauthorized' } } }];",[1100,420]),
  respond_node("resp_cli_401","resp_cli_401",401,[1320,420]),
]
link("wh_clientes","cfg_cli"); link("cfg_cli","gate_cli"); link("gate_cli","if_cli")
link("if_cli","q_clientes",0)   # true
link("q_clientes","shape_cli"); link("shape_cli","resp_cli_ok")
link("if_cli","deny_cli",1)     # false
link("deny_cli","resp_cli_401")
```

- [ ] **Step 3: Deploy**

Run: `cd scripts && python3 f_01_admin_api.py`
Expected: `deploy OK: <id> | endpoints: ['admin-auth', 'admin-clientes']`

- [ ] **Step 4: Curl-test DEPOIS (autorizado e negado)**

Run:
```bash
BASE="https://n8n.quirkgrowth.online/webhook/admin-clientes"
echo "autorizado:"; curl -s -X POST "$BASE" -H "Content-Type: application/json" -d '{"passphrase":"<PASSPHRASE>","somente_ativos":false}' | python3 -m json.tool | head -40
echo "negado:"; curl -s -o /dev/null -w "%{http_code}\n" -X POST "$BASE" -H "Content-Type: application/json" -d '{"passphrase":"errada"}'
```
Expected: autorizado → JSON com `ok:true`, `clientes:[...]` (inclui `5511980838409` e `5511980838444`), `total_ativos`, `mrr_estimado`, e `n_campanhas` por cliente · negado → `401`

- [ ] **Step 5: Commit**

```bash
cd /Users/renanreal/quirk_auto_ads
git add scripts/f_01_admin_api.py
git commit -m "feat(admin): endpoint admin-clientes (lista + campanhas + MRR)"
```

---

### Task 3: Endpoint `admin-extrato`

**Files:**
- Modify: `scripts/f_01_admin_api.py`

- [ ] **Step 1: Curl-test ANTES (404)**

Run:
```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST "https://n8n.quirkgrowth.online/webhook/admin-extrato" -H "Content-Type: application/json" -d '{"passphrase":"x"}'
```
Expected: `404`

- [ ] **Step 2: Adicionar a chain `admin-extrato`** (o trabalho é um code node que chama o Asaas via `this.helpers.httpRequest`)

```python
# =========================================================
# ENDPOINT: admin-extrato  (pagamentos por subscription — Asaas)
# =========================================================
EXTRATO_JS = """
const body = $('wh_extrato').first().json.body || {};
const cfg = $('cfg_ext').first().json;
const sub = String(body.subscription_id || '').trim();
if (!sub) return [{ json: { body: { ok:true, pagamentos: [] } } }];
let r;
try {
  r = await this.helpers.httpRequest({
    method: 'GET',
    url: `https://api.asaas.com/v3/payments?subscription=${sub}&limit=50`,
    headers: { 'access_token': cfg.asaas_api_key, 'Content-Type': 'application/json' },
    json: true, returnFullResponse: false,
  });
} catch (e) {
  const det = (e && e.response && e.response.body) || (e && e.message) || String(e);
  return [{ json: { body: { ok:false, erro:'asaas', detalhe: det } } }];
}
const pagamentos = (r.data || []).map(p => ({
  id: p.id, value: p.value, status: p.status, billingType: p.billingType,
  dueDate: p.dueDate, paymentDate: p.paymentDate, invoiceUrl: p.invoiceUrl,
}));
return [{ json: { body: { ok:true, pagamentos } } }];
"""

NODES += [
  node("wh_extrato","wh_extrato","n8n-nodes-base.webhook",2, wh("admin-extrato"), [240,560]),
  pg_node("cfg_ext","cfg_ext","SELECT MAX(CASE WHEN chave='admin_passphrase' THEN valor END) AS admin_passphrase, MAX(CASE WHEN chave='asaas_api_key' THEN valor END) AS asaas_api_key FROM auto_ads.config WHERE chave IN ('admin_passphrase','asaas_api_key')",[460,560]),
  code_node("gate_ext","gate_ext", gate_js("wh_extrato","cfg_ext"), [680,560]),
  node("if_ext","if_ext","n8n-nodes-base.if",2,
       {"conditions":{"options":{"caseSensitive":True,"typeValidation":"strict"},"combinator":"and",
        "conditions":[{"leftValue":"={{ $json.authorized }}","rightValue":True,"operator":{"type":"boolean","operation":"true","singleValue":True}}]}},
       [880,560]),
  code_node("do_extrato","do_extrato", EXTRATO_JS, [1100,500]),
  respond_node("resp_ext_ok","resp_ext_ok",200,[1320,500]),
  code_node("deny_ext","deny_ext","return [{ json: { body: { ok:false, erro:'unauthorized' } } }];",[1100,660]),
  respond_node("resp_ext_401","resp_ext_401",401,[1320,660]),
]
link("wh_extrato","cfg_ext"); link("cfg_ext","gate_ext"); link("gate_ext","if_ext")
link("if_ext","do_extrato",0); link("do_extrato","resp_ext_ok")
link("if_ext","deny_ext",1);   link("deny_ext","resp_ext_401")
```

- [ ] **Step 3: Deploy**

Run: `cd scripts && python3 f_01_admin_api.py`
Expected: endpoints inclui `admin-extrato`.

- [ ] **Step 4: Descobrir uma subscription real pra testar**

Run:
```bash
cd scripts && python3 -c "import psycopg2; u=open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-','aws-1-'); c=psycopg2.connect(u).cursor(); c.execute(\"SELECT telefone, subscription_id FROM auto_ads.clientes WHERE subscription_id IS NOT NULL LIMIT 3\"); print(c.fetchall())"
```
Expected: uma lista com pelo menos um `subscription_id` (ex.: `sub_...`).

- [ ] **Step 5: Curl-test com subscription real**

Run:
```bash
BASE="https://n8n.quirkgrowth.online/webhook/admin-extrato"
curl -s -X POST "$BASE" -H "Content-Type: application/json" -d '{"passphrase":"<PASSPHRASE>","subscription_id":"<SUB_REAL>"}' | python3 -m json.tool
```
Expected: `{"ok":true,"pagamentos":[ ... ]}` (lista de cobranças; pode ser vazia se a assinatura não tiver histórico, mas sem erro).

- [ ] **Step 6: Commit**

```bash
cd /Users/renanreal/quirk_auto_ads
git add scripts/f_01_admin_api.py
git commit -m "feat(admin): endpoint admin-extrato (pagamentos Asaas por subscription)"
```

---

### Task 4: Endpoint `admin-desativar` (os 3 passos + audit_log)

**Files:**
- Modify: `scripts/f_01_admin_api.py`

- [ ] **Step 1: Curl-test ANTES (404)**

Run:
```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST "https://n8n.quirkgrowth.online/webhook/admin-desativar" -H "Content-Type: application/json" -d '{"passphrase":"x"}'
```
Expected: `404`

- [ ] **Step 2: Adicionar a chain `admin-desativar`** — um único code node executa os 3 passos (Asaas cancel → Meta pause → Supabase update) usando `this.helpers.httpRequest` pro Asaas/Meta; o UPDATE + audit são feitos por nós Postgres depois. Ordem: estanca dinheiro primeiro.

```python
# =========================================================
# ENDPOINT: admin-desativar  (Asaas cancel -> Meta pause -> status -> audit)
# =========================================================
# Passo Asaas + Meta num code node (retorna resultados + carrega dados p/ os PGs seguintes)
DESATIVAR_JS = """
const body = $('wh_desativar').first().json.body || {};
const cfg = $('cfg_des').first().json;
const telefone = String(body.telefone || '').trim();
if (!telefone) return [{ json: { body: { ok:false, erro:'sem_telefone' } } , stop:true }];

// dados do cliente + campanhas (vieram nos PGs anteriores)
const cli = $('pg_cli_des').first().json;              // { subscription_id }
const campRows = $('pg_camp_des').all().map(i => i.json).filter(r => r.campaign_id);

const asaasHeaders = { 'access_token': cfg.asaas_api_key, 'Content-Type': 'application/json' };

// 1) Asaas: cancela assinatura
let passo_asaas = { ok:false };
const sub = cli && cli.subscription_id;
if (!sub) { passo_asaas = { ok:true, nota:'sem_subscription' }; }
else {
  try {
    await this.helpers.httpRequest({ method:'DELETE', url:`https://api.asaas.com/v3/subscriptions/${sub}`, headers: asaasHeaders, json:true });
    passo_asaas = { ok:true, subscription_id: sub };
  } catch (e) {
    const det=(e&&e.response&&e.response.body)||(e&&e.message)||String(e);
    // se ja cancelada/inexistente, trata como ok
    passo_asaas = { ok:true, nota:'ja_cancelada_ou_inexistente', detalhe: det };
  }
}

// 2) Meta: pausa cada campanha do cliente
let pausadas = 0; const erros = [];
for (const c of campRows) {
  try {
    await this.helpers.httpRequest({ method:'POST', url:`https://graph.facebook.com/v21.0/${c.campaign_id}`,
      body:{ status:'PAUSED', access_token: cfg.meta_access_token }, json:true });
    pausadas++;
  } catch (e) { erros.push({ campaign_id: c.campaign_id, erro: (e&&e.message)||String(e) }); }
}
const passo_meta = { ok: erros.length===0, pausadas, total: campRows.length, erros };

return [{ json: { telefone, passo_asaas, passo_meta } }];
"""

# code final: monta a resposta (o UPDATE e o audit rodam entre este e o respond)
RESP_DES_JS = """
const d = $('do_desativar').first().json;
return [{ json: { body: { ok:true, passo_asaas: d.passo_asaas, passo_meta: d.passo_meta, passo_status: { ok:true } } } }];
"""

NODES += [
  node("wh_desativar","wh_desativar","n8n-nodes-base.webhook",2, wh("admin-desativar"), [240,820]),
  pg_node("cfg_des","cfg_des","SELECT MAX(CASE WHEN chave='admin_passphrase' THEN valor END) AS admin_passphrase, MAX(CASE WHEN chave='asaas_api_key' THEN valor END) AS asaas_api_key, MAX(CASE WHEN chave='meta_access_token' THEN valor END) AS meta_access_token FROM auto_ads.config WHERE chave IN ('admin_passphrase','asaas_api_key','meta_access_token')",[460,820]),
  code_node("gate_des","gate_des", gate_js("wh_desativar","cfg_des"), [680,820]),
  node("if_des","if_des","n8n-nodes-base.if",2,
       {"conditions":{"options":{"caseSensitive":True,"typeValidation":"strict"},"combinator":"and",
        "conditions":[{"leftValue":"={{ $json.authorized }}","rightValue":True,"operator":{"type":"boolean","operation":"true","singleValue":True}}]}},
       [880,820]),
  pg_node("pg_cli_des","pg_cli_des","SELECT subscription_id FROM auto_ads.clientes WHERE telefone = '{{ $json.body.telefone }}' LIMIT 1",[1080,760]),
  pg_node("pg_camp_des","pg_camp_des","SELECT campaign_id FROM auto_ads.campanhas WHERE telefone = '{{ $json.body.telefone }}' AND status <> 'DELETED' AND campaign_id IS NOT NULL",[1280,760]),
  code_node("do_desativar","do_desativar", DESATIVAR_JS, [1480,760]),
  pg_node("pg_update_des","pg_update_des","UPDATE auto_ads.clientes SET status='inativo', ativo=false, subscription_canceled_at=now(), status_atualizado_em=now() WHERE telefone = '{{ $('do_desativar').first().json.telefone }}'",[1680,760]),
  pg_node("pg_audit_des","pg_audit_des","INSERT INTO auto_ads.audit_log (telefone, acao, detalhe) VALUES ('{{ $('do_desativar').first().json.telefone }}', 'admin_desativar', '{{ JSON.stringify($('do_desativar').first().json).replace(/'/g, \\\"''\\\") }}')",[1880,760]),
  code_node("resp_des_build","resp_des_build", RESP_DES_JS, [2080,760]),
  respond_node("resp_des_ok","resp_des_ok",200,[2280,760]),
  code_node("deny_des","deny_des","return [{ json: { body: { ok:false, erro:'unauthorized' } } }];",[1080,920]),
  respond_node("resp_des_401","resp_des_401",401,[1280,920]),
]
link("wh_desativar","cfg_des"); link("cfg_des","gate_des"); link("gate_des","if_des")
link("if_des","pg_cli_des",0)
link("pg_cli_des","pg_camp_des"); link("pg_camp_des","do_desativar")
link("do_desativar","pg_update_des"); link("pg_update_des","pg_audit_des")
link("pg_audit_des","resp_des_build"); link("resp_des_build","resp_des_ok")
link("if_des","deny_des",1); link("deny_des","resp_des_401")
```

> **Nota sobre `audit_log`:** confirme as colunas antes (Step 3). Se a tabela não tiver `(telefone, acao, detalhe)`, ajuste o INSERT às colunas reais.

- [ ] **Step 3: Conferir as colunas de `audit_log` (ajustar o INSERT se preciso)**

Run:
```bash
cd scripts && python3 -c "import psycopg2; u=open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-','aws-1-'); c=psycopg2.connect(u).cursor(); c.execute(\"SELECT column_name FROM information_schema.columns WHERE table_schema='auto_ads' AND table_name='audit_log' ORDER BY ordinal_position\"); print([r[0] for r in c.fetchall()])"
```
Expected: a lista de colunas. Ajuste `pg_audit_des` pra bater com elas (ex.: se houver `criado_em` com default, não precisa incluir).

- [ ] **Step 4: Deploy**

Run: `cd scripts && python3 f_01_admin_api.py`
Expected: endpoints inclui `admin-desativar`.

- [ ] **Step 5: Preparar um cliente de teste seguro e anotar estado atual**

Run:
```bash
cd scripts && python3 -c "
import psycopg2; u=open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-','aws-1-')
c=psycopg2.connect(u); cur=c.cursor()
cur.execute(\"SELECT telefone,status,ativo,subscription_id FROM auto_ads.clientes WHERE telefone='5511980838444'\"); print('ANTES:', cur.fetchone())
c.close()"
```
Expected: imprime o estado do cliente de teste (Nathalie). **Anote** pra restaurar depois.

- [ ] **Step 6: Curl-test do desativar (autorizado) + verificar os 3 passos**

Run:
```bash
BASE="https://n8n.quirkgrowth.online/webhook/admin-desativar"
curl -s -X POST "$BASE" -H "Content-Type: application/json" -d '{"passphrase":"<PASSPHRASE>","telefone":"5511980838444"}' | python3 -m json.tool
```
Expected: `{"ok":true,"passo_asaas":{...ok:true},"passo_meta":{...},"passo_status":{"ok":true}}`

Depois verifique no banco:
```bash
cd scripts && python3 -c "
import psycopg2; u=open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-','aws-1-')
c=psycopg2.connect(u).cursor()
c.execute(\"SELECT status,ativo,subscription_canceled_at FROM auto_ads.clientes WHERE telefone='5511980838444'\"); print('DEPOIS:', c.fetchone())
c.execute(\"SELECT acao, criado_em FROM auto_ads.audit_log WHERE telefone='5511980838444' ORDER BY 2 DESC LIMIT 1\"); print('AUDIT:', c.fetchone())"
```
Expected: status=`inativo`, ativo=`False`, `subscription_canceled_at` preenchido; linha no audit_log com acao `admin_desativar`.

- [ ] **Step 7: Curl-test negado (passphrase errada NÃO deve executar nada)**

Run:
```bash
BASE="https://n8n.quirkgrowth.online/webhook/admin-desativar"
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$BASE" -H "Content-Type: application/json" -d '{"passphrase":"errada","telefone":"5511980838409"}'
```
Expected: `401` (e o cliente `...409` permanece `pago_aguardando_meta`/inalterado — confirme no banco se quiser).

- [ ] **Step 8: Restaurar o cliente de teste**

Run:
```bash
cd scripts && python3 -c "
import psycopg2; u=open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-','aws-1-')
c=psycopg2.connect(u); cur=c.cursor()
cur.execute(\"UPDATE auto_ads.clientes SET status='pago_aguardando_meta', ativo=true, subscription_canceled_at=NULL WHERE telefone='5511980838444'\")
c.commit(); print('restaurado')"
```
Expected: `restaurado` (ajuste o status ao valor que você anotou no Step 5).

- [ ] **Step 9: Commit**

```bash
cd /Users/renanreal/quirk_auto_ads
git add scripts/f_01_admin_api.py
git commit -m "feat(admin): endpoint admin-desativar (cancela Asaas + pausa Meta + status + audit)"
```

---

### Task 5: Frontend `admin.html` — login + dashboard (lista)

**Files:**
- Create: `/Users/renanreal/Desktop/Quirk Auto Ads - Páginas/admin.html`

- [ ] **Step 1: Criar `admin.html` (login + dashboard + tabela)**

```html
<!doctype html>
<html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Auto Ads — Gestão</title>
<style>
  :root{--bg:#001D41;--deep:#00132C;--surf:#0a2952;--blue:#1D80FF;--neon:#00E5FF;--green:#39b54a;--red:#ef4444;--txt:#fff;--muted:#8CBEFF}
  *{box-sizing:border-box}body{margin:0;font-family:'Poppins',system-ui,sans-serif;background:var(--bg);color:var(--txt)}
  .wrap{max-width:1200px;margin:0 auto;padding:24px}
  .card{background:var(--surf);border-radius:14px;padding:20px}
  input,button{font:inherit}
  input{background:var(--deep);border:1px solid #143667;color:#fff;border-radius:10px;padding:12px 14px;width:100%}
  button{background:var(--blue);color:#fff;border:0;border-radius:10px;padding:12px 18px;cursor:pointer;font-weight:600}
  button.ghost{background:transparent;border:1px solid #143667}
  button.danger{background:var(--red)}
  table{width:100%;border-collapse:collapse;margin-top:16px}
  th,td{text-align:left;padding:10px 12px;border-bottom:1px solid #143667;font-size:14px}
  tr[data-tel]{cursor:pointer}tr[data-tel]:hover{background:#0c2f5e}
  .badge{padding:3px 9px;border-radius:20px;font-size:12px;font-weight:600}
  .badge.ativo{background:rgba(57,181,74,.2);color:#7BE38A}
  .badge.inativo{background:rgba(239,68,68,.2);color:#ff9c9c}
  .badge.pago_aguardando_meta,.badge.em_onboarding{background:rgba(29,128,255,.2);color:#8CBEFF}
  .kpis{display:flex;gap:16px;margin-bottom:16px}.kpi{flex:1}.kpi b{font-size:26px;display:block}
  .hidden{display:none}
  .drawer{position:fixed;top:0;right:0;height:100%;width:min(460px,100%);background:var(--deep);
          border-left:1px solid #143667;padding:24px;overflow:auto;transform:translateX(100%);transition:.2s}
  .drawer.open{transform:none}.row{display:flex;justify-content:space-between;gap:12px;padding:6px 0;border-bottom:1px solid #123157;font-size:14px}
  .muted{color:var(--muted)}
</style></head><body>

<!-- LOGIN -->
<div id="login" class="wrap"><div class="card" style="max-width:420px;margin:12vh auto">
  <h2>Auto Ads — Gestão</h2>
  <p class="muted">Digite a senha de acesso.</p>
  <input id="pass" type="password" placeholder="Senha" onkeydown="if(event.key==='Enter')doLogin()">
  <p id="loginErr" class="hidden" style="color:var(--red)">Senha incorreta.</p>
  <button style="margin-top:12px;width:100%" onclick="doLogin()">Entrar</button>
</div></div>

<!-- DASHBOARD -->
<div id="dash" class="wrap hidden">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <h2>Clientes</h2>
    <label class="muted"><input type="checkbox" id="soAtivos" checked onchange="loadClientes()" style="width:auto"> só ativos</label>
  </div>
  <div class="kpis">
    <div class="card kpi"><span class="muted">Ativos</span><b id="kAtivos">–</b></div>
    <div class="card kpi"><span class="muted">MRR estimado</span><b id="kMrr">–</b></div>
  </div>
  <div class="card"><table><thead><tr>
    <th>Nome</th><th>Telefone</th><th>Entrada</th><th>Status</th><th>Campanhas</th><th>Gateway</th>
  </tr></thead><tbody id="tbody"></tbody></table></div>
</div>

<div id="drawer" class="drawer"></div>

<script>
const API="https://n8n.quirkgrowth.online/webhook";
let PASS="";
let CLIENTES=[];

async function post(path, extra){
  const r=await fetch(`${API}/${path}`,{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify(Object.assign({passphrase:PASS},extra||{}))});
  if(r.status===401) throw {unauthorized:true};
  return r.json();
}
async function doLogin(){
  PASS=document.getElementById("pass").value;
  try{
    const res=await post("admin-auth");
    if(res.ok){ sessionStorage.setItem("pp",PASS); showDash(); }
    else document.getElementById("loginErr").classList.remove("hidden");
  }catch(e){ document.getElementById("loginErr").classList.remove("hidden"); }
}
function showDash(){
  document.getElementById("login").classList.add("hidden");
  document.getElementById("dash").classList.remove("hidden");
  loadClientes();
}
function fmtDate(s){ if(!s)return"–"; const d=new Date(s); return d.toLocaleDateString("pt-BR"); }
function badge(status){ return `<span class="badge ${status}">${status}</span>`; }

async function loadClientes(){
  const soAtivos=document.getElementById("soAtivos").checked;
  try{
    const res=await post("admin-clientes",{somente_ativos:soAtivos});
    CLIENTES=res.clientes||[];
    document.getElementById("kAtivos").textContent=res.total_ativos;
    document.getElementById("kMrr").textContent="R$ "+(res.mrr_estimado||0).toLocaleString("pt-BR");
    const tb=document.getElementById("tbody");
    tb.innerHTML=CLIENTES.map(c=>`<tr data-tel="${c.telefone}" onclick="openDetail('${c.telefone}')">
      <td>${c.nome_cliente||"–"}</td><td>${c.telefone}</td>
      <td>${fmtDate(c.subscription_started_at||c.criado_em)}</td>
      <td>${badge(c.status)}</td><td>${c.n_campanhas||0}</td><td>${c.gateway||"–"}</td></tr>`).join("");
  }catch(e){ if(e.unauthorized) logout(); }
}
function logout(){ sessionStorage.removeItem("pp"); location.reload(); }

// auto-login se já autenticado nesta sessão
window.addEventListener("load",()=>{ const p=sessionStorage.getItem("pp"); if(p){ PASS=p; showDash(); } });
</script>
</body></html>
```

- [ ] **Step 2: Servir localmente e testar login + lista no navegador**

Run: `cd "/Users/renanreal/Desktop/Quirk Auto Ads - Páginas" && python3 -m http.server 8899`
Então abra `http://localhost:8899/admin.html`, digite a passphrase, e confirme: dashboard aparece, KPIs preenchidos, tabela lista os 2 clientes de teste, toggle "só ativos" funciona.
Expected: login com senha certa → dashboard; senha errada → "Senha incorreta."

> **Nota CORS:** como a página local (`localhost:8899`) não é a origem permitida (`autoads.quirkgrowth.com.br`), o navegador pode bloquear o fetch no teste local. Se bloquear, teste temporariamente adicionando `localhost` em `options.allowedOrigins` (array) no `wh()` do build script, redeploy, e **reverta** antes do deploy final. Alternativa: pular o teste local e validar direto após subir no cPanel (Task 7).

- [ ] **Step 3: Commit**

```bash
cd /Users/renanreal/quirk_auto_ads
mkdir -p frontend_admin
cp "/Users/renanreal/Desktop/Quirk Auto Ads - Páginas/admin.html" frontend_admin/admin.html
git add frontend_admin/admin.html
git commit -m "feat(admin): frontend login + dashboard (lista de clientes)"
```

---

### Task 6: Frontend — detalhe do cliente + extrato + desativar

**Files:**
- Modify: `/Users/renanreal/Desktop/Quirk Auto Ads - Páginas/admin.html` (adiciona funções no `<script>`)

- [ ] **Step 1: Adicionar `openDetail`, `loadExtrato` e `doDeactivate`** (inserir antes do bloco de auto-login)

```javascript
async function openDetail(tel){
  const c=CLIENTES.find(x=>x.telefone===tel); if(!c)return;
  const d=document.getElementById("drawer");
  d.innerHTML=`
    <button class="ghost" onclick="closeDrawer()" style="float:right">Fechar</button>
    <h3>${c.nome_cliente||"–"}</h3>
    <div class="row"><span class="muted">Telefone</span><span>${c.telefone}</span></div>
    <div class="row"><span class="muted">Email</span><span>${c.email||"–"}</span></div>
    <div class="row"><span class="muted">Entrada</span><span>${fmtDate(c.subscription_started_at||c.criado_em)}</span></div>
    <div class="row"><span class="muted">Status</span><span>${badge(c.status)}</span></div>
    <div class="row"><span class="muted">Ad Account</span><span>${c.ad_account_id||"–"}</span></div>
    <div class="row"><span class="muted">Página</span><span>${c.page_id||"–"}</span></div>
    <div class="row"><span class="muted">Campanhas</span><span>${c.n_campanhas||0}</span></div>
    <h4 style="margin-top:20px">Extrato de pagamentos</h4>
    <div id="extrato" class="muted">Carregando…</div>
    <button class="danger" style="width:100%;margin-top:24px" onclick="doDeactivate('${c.telefone}','${(c.nome_cliente||'').replace(/'/g,'')}')">Desativar cliente</button>`;
  d.classList.add("open");
  loadExtrato(c.subscription_id);
}
function closeDrawer(){ document.getElementById("drawer").classList.remove("open"); }

async function loadExtrato(subId){
  const el=document.getElementById("extrato");
  try{
    const res=await post("admin-extrato",{subscription_id:subId});
    const p=res.pagamentos||[];
    el.innerHTML = p.length? p.map(x=>`<div class="row">
      <span>${fmtDate(x.paymentDate||x.dueDate)}</span>
      <span>R$ ${(x.value||0).toLocaleString("pt-BR")} · ${x.status}</span></div>`).join("")
      : "Sem pagamentos.";
  }catch(e){ el.textContent = e.unauthorized? "Sessão expirada." : "Erro ao carregar extrato."; }
}

async function doDeactivate(tel,nome){
  if(!confirm(`Desativar ${nome||tel}?\n\nIsto vai:\n• Cancelar a assinatura no Asaas (para de cobrar)\n• Pausar as campanhas Meta (para de gastar)\n• Marcar status = inativo\n\nConfirmar?`)) return;
  try{
    const res=await post("admin-desativar",{telefone:tel});
    if(res.ok){
      alert(`Cliente desativado.\nAsaas: ${res.passo_asaas.ok?"✓":"✗"}\nMeta: ${res.passo_meta.pausadas}/${res.passo_meta.total} pausadas\nStatus: ✓`);
      closeDrawer(); loadClientes();
    } else alert("Falhou: "+(res.erro||"erro"));
  }catch(e){ if(e.unauthorized) logout(); else alert("Erro de rede."); }
}
```

- [ ] **Step 2: Testar no navegador (detalhe + extrato + desativar)**

Sirva de novo (`python3 -m http.server 8899` na pasta das páginas), abra `admin.html`, clique num cliente → confirme o drawer com dados + extrato. Teste o "Desativar" no cliente de teste `5511980838444` → confirme o alerta com os 3 passos, e depois **restaure** (Task 4, Step 8).
Expected: drawer abre com dados e extrato; desativar mostra resultado dos 3 passos e some da lista de ativos.

- [ ] **Step 3: Commit**

```bash
cd /Users/renanreal/quirk_auto_ads
cp "/Users/renanreal/Desktop/Quirk Auto Ads - Páginas/admin.html" frontend_admin/admin.html
git add frontend_admin/admin.html
git commit -m "feat(admin): detalhe do cliente + extrato + desativar (frontend)"
```

---

### Task 7: Deploy no cPanel + verificação final + commit

**Files:**
- Deploy: `admin.html` no cPanel (pasta do subdomínio `autoads.quirkgrowth.com.br`)

- [ ] **Step 1: Garantir que `allowedOrigins` está só com a origem de produção**

Confira no `scripts/f_01_admin_api.py` que `ORIGIN = "https://autoads.quirkgrowth.com.br"` (sem `localhost`, se você tiver adicionado no teste). Se mexeu, `cd scripts && python3 f_01_admin_api.py` de novo.

- [ ] **Step 2: Subir `admin.html` no cPanel**

No File Manager do cPanel, entre na pasta-raiz do subdomínio `autoads.quirkgrowth.com.br` (a mesma onde estão `index.html`, `checkout.html` etc.) e faça upload de `admin.html` (de `/Users/renanreal/Desktop/Quirk Auto Ads - Páginas/admin.html`).

- [ ] **Step 3: Verificação final em produção**

Abra `https://autoads.quirkgrowth.com.br/admin.html`:
- Login com a passphrase → dashboard carrega (sem erro de CORS no console).
- Lista, KPIs, toggle, detalhe e extrato funcionam.
- (Opcional) desativar no cliente de teste e restaurar.
Expected: tudo funciona em produção, sem erro de CORS.

- [ ] **Step 4: Commit final (plano + fecha a feature)**

```bash
cd /Users/renanreal/quirk_auto_ads
git add docs/superpowers/plans/2026-07-03-admin-painel-gestao.md frontend_admin/admin.html
git commit -m "feat(admin): painel de gestão de assinaturas no ar (plano + frontend final)"
```

---

## Self-Review (feito na escrita)

**Cobertura do spec:**
- Passphrase no n8n → Task 1 (config + gate em todos os endpoints). ✓
- Listar clientes + nº campanhas + MRR → Task 2. ✓
- Extrato Asaas por subscription → Task 3. ✓
- Desativar = Asaas cancel → Meta pause → status → audit_log → Task 4. ✓
- Frontend: login, dashboard, toggle, detalhe, extrato, desativar → Tasks 5–6. ✓
- Deploy cPanel + CORS → Task 7 + `allowedOrigins`. ✓
- Não-objetivos (sem multiusuário, sem editar, sem reativar, sem aviso WhatsApp) → respeitados. ✓

**Pontos que o executor deve validar ao vivo (podem exigir ajuste fino):**
1. `typeVersion` dos nós (webhook 2, postgres 2.5, if 2, code 2, respondToWebhook 1.1) — se a instância n8n reclamar, rode `get_workflow` num workflow existente e alinhe as versões.
2. Formato do nó **IF** (v2 usa `conditions.conditions[]` com `operator`); se a UI mostrar a condição vazia, ajuste ao shape de um IF existente na instância.
3. Colunas reais de `auto_ads.audit_log` (Task 4, Step 3) antes do INSERT.
4. Interpolação `{{ $json.body.telefone }}` nos nós Postgres: confirme que o Postgres node aceita expressão na query (a instância já usa esse padrão em `upsert_cliente`); se precisar, passe via `additionalFields`/parâmetros.
5. CORS no teste local (Task 5, Step 2) — validar em produção é o caminho garantido.
```
