# scripts/f_01_admin_api.py
# Build script do workflow "Quirk Auto Ads — Admin API".
# Re-runnable: cria se nao existe, atualiza se existe. Persiste wf_id em n8n_workflow/.admin_api_id.
# Cresce por tarefa: Task 1 = helpers + endpoint admin-auth.
import json, os, n8n_api, config

ORIGIN = "https://autoads.quirkgrowth.com.br"
ID_FILE = "../n8n_workflow/.admin_api_id"
PG = config.POSTGRES_CRED

# typeVersions alinhadas com a instancia (via get_workflow do gateway 2ZnZqb4wFous4uEs):
#   webhook 2, postgres 2.6, code 2, respondToWebhook 1, if 1
PG_VER = 2.6
RESP_VER = 1


def wh(path):
    return {"httpMethod": "POST", "path": path, "responseMode": "responseNode",
            "options": {"allowedOrigins": ORIGIN}}


def node(id_, name, typ, ver, params, pos, creds=None):
    n = {"id": id_, "name": name, "type": typ, "typeVersion": ver,
         "parameters": params, "position": pos}
    if creds: n["credentials"] = creds
    return n


def pg_node(id_, name, query, pos):
    return node(id_, name, "n8n-nodes-base.postgres", PG_VER,
                {"operation": "executeQuery", "query": query}, pos,
                creds={"postgres": PG})


def code_node(id_, name, js, pos):
    return node(id_, name, "n8n-nodes-base.code", 2, {"jsCode": js}, pos)


def respond_node(id_, name, code_http, pos):
    return node(id_, name, "n8n-nodes-base.respondToWebhook", RESP_VER,
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
  node("wh_auth", "wh_auth", "n8n-nodes-base.webhook", 2, wh("admin-auth"), [240, 120]),
  pg_node("cfg_auth", "cfg_auth", "SELECT valor AS admin_passphrase FROM auto_ads.config WHERE chave='admin_passphrase' LIMIT 1", [460, 120]),
  code_node("auth_check", "auth_check",
     "const body=$('wh_auth').first().json.body||{};const cfg=$('cfg_auth').first().json;"
     "const ok=String(body.passphrase||'')!==''&&String(body.passphrase)===String(cfg.admin_passphrase||'__none__');"
     "return [{ json: { body: { ok } } }];", [680, 120]),
  respond_node("auth_resp", "auth_resp", 200, [900, 120]),
]
link("wh_auth", "cfg_auth"); link("cfg_auth", "auth_check"); link("auth_check", "auth_resp")


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
  node("wh_clientes", "wh_clientes", "n8n-nodes-base.webhook", 2, wh("admin-clientes"), [240, 320]),
  pg_node("cfg_cli", "cfg_cli", "SELECT valor AS admin_passphrase FROM auto_ads.config WHERE chave='admin_passphrase' LIMIT 1", [460, 320]),
  code_node("gate_cli", "gate_cli", gate_js("wh_clientes", "cfg_cli"), [680, 320]),
  node("if_cli", "if_cli", "n8n-nodes-base.if", 1,
       {"conditions": {"boolean": [{"value1": "={{ $json.authorized }}", "value2": True}]}},
       [880, 320]),
  pg_node("q_clientes", "q_clientes", Q_CLIENTES, [1100, 260]),
  code_node("shape_cli", "shape_cli", SHAPE_CLIENTES_JS, [1320, 260]),
  respond_node("resp_cli_ok", "resp_cli_ok", 200, [1540, 260]),
  code_node("deny_cli", "deny_cli", "return [{ json: { body: { ok:false, erro:'unauthorized' } } }];", [1100, 420]),
  respond_node("resp_cli_401", "resp_cli_401", 401, [1320, 420]),
]
link("wh_clientes", "cfg_cli"); link("cfg_cli", "gate_cli"); link("gate_cli", "if_cli")
link("if_cli", "q_clientes", 0)   # true
link("q_clientes", "shape_cli"); link("shape_cli", "resp_cli_ok")
link("if_cli", "deny_cli", 1)     # false
link("deny_cli", "resp_cli_401")


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
  node("wh_extrato", "wh_extrato", "n8n-nodes-base.webhook", 2, wh("admin-extrato"), [240, 560]),
  pg_node("cfg_ext", "cfg_ext", "SELECT MAX(CASE WHEN chave='admin_passphrase' THEN valor END) AS admin_passphrase, MAX(CASE WHEN chave='asaas_api_key' THEN valor END) AS asaas_api_key FROM auto_ads.config WHERE chave IN ('admin_passphrase','asaas_api_key')", [460, 560]),
  code_node("gate_ext", "gate_ext", gate_js("wh_extrato", "cfg_ext"), [680, 560]),
  node("if_ext", "if_ext", "n8n-nodes-base.if", 1,
       {"conditions": {"boolean": [{"value1": "={{ $json.authorized }}", "value2": True}]}},
       [880, 560]),
  code_node("do_extrato", "do_extrato", EXTRATO_JS, [1100, 500]),
  respond_node("resp_ext_ok", "resp_ext_ok", 200, [1320, 500]),
  code_node("deny_ext", "deny_ext", "return [{ json: { body: { ok:false, erro:'unauthorized' } } }];", [1100, 660]),
  respond_node("resp_ext_401", "resp_ext_401", 401, [1320, 660]),
]
link("wh_extrato", "cfg_ext"); link("cfg_ext", "gate_ext"); link("gate_ext", "if_ext")
link("if_ext", "do_extrato", 0); link("do_extrato", "resp_ext_ok")
link("if_ext", "deny_ext", 1);   link("deny_ext", "resp_ext_401")


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
  node("wh_desativar", "wh_desativar", "n8n-nodes-base.webhook", 2, wh("admin-desativar"), [240, 820]),
  pg_node("cfg_des", "cfg_des", "SELECT MAX(CASE WHEN chave='admin_passphrase' THEN valor END) AS admin_passphrase, MAX(CASE WHEN chave='asaas_api_key' THEN valor END) AS asaas_api_key, MAX(CASE WHEN chave='meta_access_token' THEN valor END) AS meta_access_token FROM auto_ads.config WHERE chave IN ('admin_passphrase','asaas_api_key','meta_access_token')", [460, 820]),
  code_node("gate_des", "gate_des", gate_js("wh_desativar", "cfg_des"), [680, 820]),
  node("if_des", "if_des", "n8n-nodes-base.if", 1,
       {"conditions": {"boolean": [{"value1": "={{ $json.authorized }}", "value2": True}]}},
       [880, 820]),
  pg_node("pg_cli_des", "pg_cli_des", "SELECT subscription_id FROM auto_ads.clientes WHERE telefone = '{{ $('wh_desativar').first().json.body.telefone }}' LIMIT 1", [1080, 760]),
  # sentinela (NULL campaign_id) garante >=1 item mesmo se o cliente nao tiver campanhas,
  # senao a cadeia linear do n8n para aqui (nenhum item -> do_desativar nunca roda).
  # do_desativar ja ignora linhas sem campaign_id via .filter(r => r.campaign_id).
  pg_node("pg_camp_des", "pg_camp_des", "SELECT campaign_id FROM auto_ads.campanhas WHERE telefone = '{{ $('wh_desativar').first().json.body.telefone }}' AND status <> 'DELETED' AND campaign_id IS NOT NULL UNION ALL SELECT NULL::text WHERE NOT EXISTS (SELECT 1 FROM auto_ads.campanhas WHERE telefone = '{{ $('wh_desativar').first().json.body.telefone }}' AND status <> 'DELETED' AND campaign_id IS NOT NULL)", [1280, 760]),
  code_node("do_desativar", "do_desativar", DESATIVAR_JS, [1480, 760]),
  pg_node("pg_update_des", "pg_update_des", "UPDATE auto_ads.clientes SET status='inativo', ativo=false, subscription_canceled_at=now(), status_atualizado_em=now() WHERE telefone = '{{ $('do_desativar').first().json.telefone }}'", [1680, 760]),
  pg_node("pg_audit_des", "pg_audit_des", "INSERT INTO auto_ads.audit_log (telefone, evento, detalhes) VALUES ('{{ $('do_desativar').first().json.telefone }}', 'admin_desativar', '{{ JSON.stringify($('do_desativar').first().json).replace(/'/g, \"''\") }}'::jsonb)", [1880, 760]),
  code_node("resp_des_build", "resp_des_build", RESP_DES_JS, [2080, 760]),
  respond_node("resp_des_ok", "resp_des_ok", 200, [2280, 760]),
  code_node("deny_des", "deny_des", "return [{ json: { body: { ok:false, erro:'unauthorized' } } }];", [1080, 920]),
  respond_node("resp_des_401", "resp_des_401", 401, [1280, 920]),
]
link("wh_desativar", "cfg_des"); link("cfg_des", "gate_des"); link("gate_des", "if_des")
link("if_des", "pg_cli_des", 0)
link("pg_cli_des", "pg_camp_des"); link("pg_camp_des", "do_desativar")
link("do_desativar", "pg_update_des"); link("pg_update_des", "pg_audit_des")
link("pg_audit_des", "resp_des_build"); link("resp_des_build", "resp_des_ok")
link("if_des", "deny_des", 1); link("deny_des", "resp_des_401")


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
        wf_id = res["id"]; open(ID_FILE, "w").write(wf_id)
    n8n_api.activate_workflow(wf_id)
    print("deploy OK:", wf_id, "| endpoints:", sorted({n['parameters'].get('path') for n in NODES if n['type'] == 'n8n-nodes-base.webhook'}))


if __name__ == "__main__":
    deploy()
