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
