#!/usr/bin/env python3
"""
Branch MÍDIA — após switch_type output 1 ("media"):
  media_normalize_phone (Code) →
  media_select_cliente (Postgres) →
  media_if_cadastrado (IF) →
    ├── false → END (ignora silenciosamente — já existe send_nao_cadastrado no branch texto pra primeira interação)
    └── true → media_download (HTTP UAZAPI) →
              media_upsert_criativo (Postgres) →
              media_send_confirma (HTTP UAZAPI) → END
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api
import config

WF_ID = config.get_workflow_id()
wf = n8n_api.get_workflow(WF_ID)

new_nodes = [
    # ──────────────────────────────────────────────
    # M1. Normaliza telefone (mídia)
    # ──────────────────────────────────────────────
    {
        "id": "media_normalize_phone",
        "name": "media_normalize_phone",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [680, 500],
        "parameters": {
            "language": "javaScript",
            "jsCode": """const body = $input.first().json.body || {};
const raw = body.chat?.phone || body.message?.sender_pn?.split('@')[0] || body.message?.from || '';
const normalized = String(raw).replace(/[+\\s\\-@]/g, '').replace(/s.whatsapp.net.*$/, '');
return [{
  json: {
    ...$input.first().json,
    telefone_normalizado: normalized,
    message_id: body.message?.id || ''
  }
}];"""
        },
    },
    # ──────────────────────────────────────────────
    # M2. SELECT cliente (multi-tenancy check)
    # ──────────────────────────────────────────────
    {
        "id": "media_select_cliente",
        "name": "media_select_cliente",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.6,
        "position": [900, 500],
        "parameters": {
            "operation": "executeQuery",
            "query": "SELECT * FROM auto_ads.clientes WHERE telefone = $1 LIMIT 1",
            "options": {
                "queryReplacement": "={{ $json.telefone_normalizado }}"
            }
        },
        "credentials": {"postgres": config.POSTGRES_CRED},
    },
    # ──────────────────────────────────────────────
    # M3. IF cadastrado (silent skip se não)
    # ──────────────────────────────────────────────
    {
        "id": "media_if_cadastrado",
        "name": "media_if_cadastrado",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [1120, 500],
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                "conditions": [{
                    "id": "1",
                    "leftValue": "={{ $json.telefone }}",
                    "rightValue": "",
                    "operator": {"type": "string", "operation": "notEmpty"}
                }],
                "combinator": "and"
            },
            "options": {}
        },
    },
    # ──────────────────────────────────────────────
    # M4. Download mídia descriptografada via UAZAPI
    # ──────────────────────────────────────────────
    {
        "id": "media_download",
        "name": "media_download",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1340, 460],
        "parameters": {
            "method": "POST",
            "url": f"{config.UAZAPI_BASE}/message/download",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "token", "value": "={{ $env.UAZAPI_TOKEN }}"},
                    {"name": "Content-Type", "value": "application/json"}
                ]
            },
            "sendBody": True,
            "contentType": "json",
            "bodyParameters": {
                "parameters": [
                    {"name": "id", "value": "={{ $('media_normalize_phone').item.json.message_id }}"}
                ]
            },
            "options": {}
        },
        "retryOnFail": True,
        "maxTries": 2,
        "waitBetweenTries": 1000,
        "continueOnFail": True,
    },
    # ──────────────────────────────────────────────
    # M5. UPSERT conversa — anexa fileURL e nota no histórico
    # ──────────────────────────────────────────────
    {
        "id": "media_upsert_criativo",
        "name": "media_upsert_criativo",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.6,
        "position": [1560, 460],
        "parameters": {
            "operation": "executeQuery",
            "query": """INSERT INTO auto_ads.conversas (telefone, criativo_url, historico)
VALUES ($1, $2 || E'\\n', '|||TURN|||[Sistema: criativo recebido em ' || NOW()::TEXT || ']')
ON CONFLICT (telefone) DO UPDATE
  SET criativo_url = COALESCE(auto_ads.conversas.criativo_url, '') || EXCLUDED.criativo_url,
      historico = COALESCE(auto_ads.conversas.historico, '') || EXCLUDED.historico,
      ultima_atualizacao = NOW()""",
            "options": {
                "queryReplacement": "={{ $('media_normalize_phone').item.json.telefone_normalizado }},{{ $('media_download').item.json.data?.fileURL || $('media_download').item.json.fileURL || '' }}"
            }
        },
        "credentials": {"postgres": config.POSTGRES_CRED},
    },
    # ──────────────────────────────────────────────
    # M6. Send confirmação
    # ──────────────────────────────────────────────
    {
        "id": "media_send_confirma",
        "name": "media_send_confirma",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1780, 460],
        "parameters": {
            "method": "POST",
            "url": f"{config.UAZAPI_BASE}/send/text",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "token", "value": "={{ $env.UAZAPI_TOKEN }}"},
                    {"name": "Content-Type", "value": "application/json"}
                ]
            },
            "sendBody": True,
            "contentType": "json",
            "bodyParameters": {
                "parameters": [
                    {"name": "number", "value": "={{ $('media_normalize_phone').item.json.telefone_normalizado }}"},
                    {"name": "text", "value": "Recebi seu criativo! Vou usar nessa campanha quando você confirmar."}
                ]
            },
            "options": {}
        },
    },
]

existing_names = {n["name"] for n in wf["nodes"]}
for n in new_nodes:
    if n["name"] not in existing_names:
        wf["nodes"].append(n)
        print(f"  + {n['name']}")
    else:
        print(f"  = {n['name']} (já existia)")

# Conexões
# Switch output 1 (media) → media_normalize_phone
switch_conns = wf["connections"].setdefault("switch_type", {"main": [[], []]})
while len(switch_conns["main"]) < 2:
    switch_conns["main"].append([])
if not any(c.get("node") == "media_normalize_phone" for c in switch_conns["main"][1]):
    switch_conns["main"][1].append({"node": "media_normalize_phone", "type": "main", "index": 0})

wf["connections"]["media_normalize_phone"] = {"main": [[{"node": "media_select_cliente", "type": "main", "index": 0}]]}
wf["connections"]["media_select_cliente"] = {"main": [[{"node": "media_if_cadastrado", "type": "main", "index": 0}]]}
wf["connections"]["media_if_cadastrado"] = {
    "main": [
        [{"node": "media_download", "type": "main", "index": 0}],  # true
        []  # false: silent skip
    ]
}
wf["connections"]["media_download"] = {"main": [[{"node": "media_upsert_criativo", "type": "main", "index": 0}]]}
wf["connections"]["media_upsert_criativo"] = {"main": [[{"node": "media_send_confirma", "type": "main", "index": 0}]]}

n8n_api.update_workflow(
    WF_ID,
    name=wf["name"],
    nodes=wf["nodes"],
    connections=wf["connections"],
    settings=wf.get("settings", {"executionOrder": "v1"}),
)
print(f"\n✓ Workflow atualizado: {WF_ID}")
print(f"  Nodes totais: {len(wf['nodes'])}")
