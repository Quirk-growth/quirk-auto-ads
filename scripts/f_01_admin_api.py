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
