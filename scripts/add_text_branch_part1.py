#!/usr/bin/env python3
"""
Adiciona ao workflow Quirk Auto Ads (branch TEXTO, parte 1):

  switch_type (output 0 "text") →
    normalize_phone (Code) →
    select_cliente (Postgres) →
    if_cadastrado (IF) →
      ├── true → select_conversa (Postgres) → agente_principal (Anthropic) [→ continua na parte 2]
      └── false → send_nao_cadastrado (HTTP UAZAPI) → END
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
    # 1. Normaliza telefone
    # ──────────────────────────────────────────────
    {
        "id": "normalize_phone",
        "name": "normalize_phone",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [680, 200],
        "parameters": {
            "language": "javaScript",
            "jsCode": """// Extrai telefone do payload UAZAPI e normaliza (só dígitos)
const body = $input.first().json.body || {};
const raw = body.chat?.phone || body.message?.sender_pn?.split('@')[0] || body.message?.from || '';
const normalized = String(raw).replace(/[+\\s\\-@]/g, '').replace(/s.whatsapp.net.*$/, '');
return [{
  json: {
    ...$input.first().json,
    telefone_normalizado: normalized,
    mensagem_texto: body.message?.text || body.chat?.wa_lastMessageTextVote || ''
  }
}];"""
        },
    },
    # ──────────────────────────────────────────────
    # 2. SELECT cliente
    # ──────────────────────────────────────────────
    {
        "id": "select_cliente",
        "name": "select_cliente",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.6,
        "position": [900, 200],
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
    # 3. IF cliente cadastrado
    # ──────────────────────────────────────────────
    {
        "id": "if_cadastrado",
        "name": "if_cadastrado",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [1120, 200],
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
    # 4. Send "não cadastrado" (false branch)
    # ──────────────────────────────────────────────
    {
        "id": "send_nao_cadastrado",
        "name": "send_nao_cadastrado",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1340, 360],
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
                    {"name": "number", "value": "={{ $('normalize_phone').item.json.telefone_normalizado }}"},
                    {"name": "text", "value": "Olá! Esse número ainda não está cadastrado na Quirk Auto Ads. Entre em contato com a equipe pra ativar seu acesso."}
                ]
            },
            "options": {}
        },
    },
    # ──────────────────────────────────────────────
    # 5. SELECT conversa (true branch - parte 1 continua)
    # ──────────────────────────────────────────────
    {
        "id": "select_conversa",
        "name": "select_conversa",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.6,
        "position": [1340, 100],
        "parameters": {
            "operation": "executeQuery",
            "query": "SELECT * FROM auto_ads.conversas WHERE telefone = $1 LIMIT 1",
            "options": {
                "queryReplacement": "={{ $('normalize_phone').item.json.telefone_normalizado }}"
            }
        },
        "credentials": {"postgres": config.POSTGRES_CRED},
    },
    # ──────────────────────────────────────────────
    # 6. Agente principal (Anthropic)
    # ──────────────────────────────────────────────
    {
        "id": "agente_principal",
        "name": "agente_principal",
        "type": "n8n-nodes-base.anthropic",
        "typeVersion": 1,
        "position": [1560, 100],
        "parameters": {
            "resource": "message",
            "operation": "create",
            "model": "claude-sonnet-4-5",
            "messages": {
                "values": [
                    {
                        "role": "user",
                        "content": "={{ $('normalize_phone').item.json.mensagem_texto }}"
                    }
                ]
            },
            "options": {
                "system": config.load_prompt("agente_principal"),
                "maxTokens": 1500,
                "temperature": 0.3
            }
        },
        "credentials": {"anthropicApi": config.ANTHROPIC_CRED},
    },
]

# Idempotência: pula nodes que já existem
existing_names = {n["name"] for n in wf["nodes"]}
for n in new_nodes:
    if n["name"] not in existing_names:
        wf["nodes"].append(n)
        print(f"  + {n['name']}")
    else:
        print(f"  = {n['name']} (já existia)")

# Conexões
# Output 0 do switch_type (text) → normalize_phone
switch_conns = wf["connections"].setdefault("switch_type", {"main": [[], []]})
if not any(c.get("node") == "normalize_phone" for c in switch_conns["main"][0]):
    switch_conns["main"][0].append({"node": "normalize_phone", "type": "main", "index": 0})

wf["connections"]["normalize_phone"] = {"main": [[{"node": "select_cliente", "type": "main", "index": 0}]]}
wf["connections"]["select_cliente"] = {"main": [[{"node": "if_cadastrado", "type": "main", "index": 0}]]}
# IF cadastrado tem 2 outputs: 0 = true (select_conversa), 1 = false (send_nao_cadastrado)
wf["connections"]["if_cadastrado"] = {
    "main": [
        [{"node": "select_conversa", "type": "main", "index": 0}],
        [{"node": "send_nao_cadastrado", "type": "main", "index": 0}],
    ]
}
wf["connections"]["select_conversa"] = {"main": [[{"node": "agente_principal", "type": "main", "index": 0}]]}
# agente_principal não tem saída ainda — será conectado na parte 2

n8n_api.update_workflow(
    WF_ID,
    name=wf["name"],
    nodes=wf["nodes"],
    connections=wf["connections"],
    settings=wf.get("settings", {"executionOrder": "v1"}),
)
print(f"\n✓ Workflow atualizado: {WF_ID}")
print(f"  Nodes totais: {len(wf['nodes'])}")
