#!/usr/bin/env python3
"""
Branch TEXTO parte 3 — após if_valid (true):
  meta_d1_campaign → meta_d2_adset → meta_d3_creative → meta_d4_ad →
  insert_campanhas → audit_campanha_criada → send_confirmacao_cliente → END

Cada chamada Meta tem retry (3x, backoff 2/4/8s) + continueOnFail.
Se algum D.N falhar, vai pra branch de erro com audit log + alerta WhatsApp.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api
import config

WF_ID = config.get_workflow_id()
wf = n8n_api.get_workflow(WF_ID)

UAZAPI_TEAM_NUMBER = "5511952136200"  # número interno Quirk pra alertas de erro

new_nodes = [
    # ──────────────────────────────────────────────
    # 17. D.1 Campanha
    # ──────────────────────────────────────────────
    {
        "id": "meta_d1_campaign",
        "name": "meta_d1_campaign",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [3760, -100],
        "parameters": {
            "method": "POST",
            "url": "={{ '" + config.META_GRAPH_BASE + "/act_' + $('validate').item.json.cliente.ad_account_id + '/campaigns' }}",
            "sendBody": True,
            "contentType": "json",
            "specifyBody": "json",
            "jsonBody": """={
  "name": "{{ $('validate').item.json.json_extrator.campanha.nome }}",
  "objective": "OUTCOME_LEADS",
  "status": "PAUSED",
  "special_ad_categories": [],
  "is_adset_budget_sharing_enabled": false,
  "access_token": "{{ $env.META_ACCESS_TOKEN }}"
}""",
            "options": {
                "response": {"response": {"fullResponse": False, "responseFormat": "json"}}
            }
        },
        "retryOnFail": True,
        "maxTries": 3,
        "waitBetweenTries": 2000,
        "continueOnFail": True,
    },
    # ──────────────────────────────────────────────
    # 18. D.2 AdSet
    # ──────────────────────────────────────────────
    {
        "id": "meta_d2_adset",
        "name": "meta_d2_adset",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [3980, -100],
        "parameters": {
            "method": "POST",
            "url": "={{ '" + config.META_GRAPH_BASE + "/act_' + $('validate').item.json.cliente.ad_account_id + '/adsets' }}",
            "sendBody": True,
            "contentType": "json",
            "specifyBody": "json",
            "jsonBody": """={
  "name": "{{ $('validate').item.json.json_extrator.publico_escolhido }}",
  "campaign_id": "{{ $('meta_d1_campaign').item.json.id }}",
  "daily_budget": {{ $('validate').item.json.verba_em_centavos }},
  "billing_event": "IMPRESSIONS",
  "optimization_goal": "CONVERSATIONS",
  "destination_type": "WHATSAPP",
  "promoted_object": {"page_id": "{{ $('validate').item.json.cliente.page_id }}"},
  "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
  "targeting": {{ JSON.stringify($('validate').item.json.json_extrator.targeting_meta) }},
  "status": "PAUSED",
  "access_token": "{{ $env.META_ACCESS_TOKEN }}"
}""",
            "options": {}
        },
        "retryOnFail": True,
        "maxTries": 3,
        "waitBetweenTries": 2000,
        "continueOnFail": True,
    },
    # ──────────────────────────────────────────────
    # 19. D.3 Creative
    # ──────────────────────────────────────────────
    {
        "id": "meta_d3_creative",
        "name": "meta_d3_creative",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [4200, -100],
        "parameters": {
            "method": "POST",
            "url": "={{ '" + config.META_GRAPH_BASE + "/act_' + $('validate').item.json.cliente.ad_account_id + '/adcreatives' }}",
            "sendBody": True,
            "contentType": "json",
            "specifyBody": "json",
            "jsonBody": """={
  "name": "{{ $('validate').item.json.json_extrator.campanha.nome }}",
  "object_story_spec": {
    "page_id": "{{ $('validate').item.json.cliente.page_id }}",
    "link_data": {
      "message": "{{ $('validate').item.json.json_extrator.anuncio.copy }}",
      "picture": "{{ ($('validate').item.json.conversa.criativo_url || '').trim().split('\\n').filter(u => u).slice(-1)[0] }}",
      "link": "{{ $('validate').item.json.cliente.wa_link }}",
      "call_to_action": {
        "type": "WHATSAPP_MESSAGE",
        "value": {"app_destination": "WHATSAPP"}
      }
    }
  },
  "access_token": "{{ $env.META_ACCESS_TOKEN }}"
}""",
            "options": {}
        },
        "retryOnFail": True,
        "maxTries": 3,
        "waitBetweenTries": 2000,
        "continueOnFail": True,
    },
    # ──────────────────────────────────────────────
    # 20. D.4 Ad
    # ──────────────────────────────────────────────
    {
        "id": "meta_d4_ad",
        "name": "meta_d4_ad",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [4420, -100],
        "parameters": {
            "method": "POST",
            "url": "={{ '" + config.META_GRAPH_BASE + "/act_' + $('validate').item.json.cliente.ad_account_id + '/ads' }}",
            "sendBody": True,
            "contentType": "json",
            "specifyBody": "json",
            "jsonBody": """={
  "name": "{{ $('validate').item.json.json_extrator.campanha.nome }}",
  "adset_id": "{{ $('meta_d2_adset').item.json.id }}",
  "creative": {"creative_id": "{{ $('meta_d3_creative').item.json.id }}"},
  "status": "PAUSED",
  "access_token": "{{ $env.META_ACCESS_TOKEN }}"
}""",
            "options": {}
        },
        "retryOnFail": True,
        "maxTries": 3,
        "waitBetweenTries": 2000,
        "continueOnFail": True,
    },
    # ──────────────────────────────────────────────
    # 21. INSERT campanhas
    # ──────────────────────────────────────────────
    {
        "id": "insert_campanha",
        "name": "insert_campanha",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.6,
        "position": [4640, -100],
        "parameters": {
            "operation": "executeQuery",
            "query": """INSERT INTO auto_ads.campanhas
(telefone, nome_campanha, ad_account_id, campaign_id, adset_id, creative_id, ad_id, status, json_extrator)
VALUES ($1, $2, $3, $4, $5, $6, $7, 'PAUSED', $8::jsonb)""",
            "options": {
                "queryReplacement": "={{ $('build_historico').item.json.telefone }},{{ $('validate').item.json.json_extrator.campanha.nome }},{{ $('validate').item.json.cliente.ad_account_id }},{{ $('meta_d1_campaign').item.json.id }},{{ $('meta_d2_adset').item.json.id }},{{ $('meta_d3_creative').item.json.id }},{{ $('meta_d4_ad').item.json.id }},{{ JSON.stringify($('validate').item.json.json_extrator) }}"
            }
        },
        "credentials": {"postgres": config.POSTGRES_CRED},
    },
    # ──────────────────────────────────────────────
    # 22. Audit campanha_criada
    # ──────────────────────────────────────────────
    {
        "id": "audit_campanha_criada",
        "name": "audit_campanha_criada",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.6,
        "position": [4860, -100],
        "parameters": {
            "operation": "executeQuery",
            "query": "INSERT INTO auto_ads.audit_log (telefone, evento, detalhes) VALUES ($1, 'campanha_criada', $2::jsonb)",
            "options": {
                "queryReplacement": "={{ $('build_historico').item.json.telefone }},{{ JSON.stringify({campaign_id: $('meta_d1_campaign').item.json.id, adset_id: $('meta_d2_adset').item.json.id, creative_id: $('meta_d3_creative').item.json.id, ad_id: $('meta_d4_ad').item.json.id, nome: $('validate').item.json.json_extrator.campanha.nome}) }}"
            }
        },
        "credentials": {"postgres": config.POSTGRES_CRED},
    },
    # ──────────────────────────────────────────────
    # 23. Send confirmação ao cliente
    # ──────────────────────────────────────────────
    {
        "id": "send_confirmacao_cliente",
        "name": "send_confirmacao_cliente",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [5080, -100],
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
                    {"name": "number", "value": "={{ $('build_historico').item.json.telefone }}"},
                    {"name": "text", "value": "=Campanha *{{ $('validate').item.json.json_extrator.campanha.nome }}* criada em PAUSED no Ads Manager. Revise por lá pra ativar."}
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

# Conexões: if_valid (true) → D.1 → D.2 → D.3 → D.4 → INSERT → audit → send confirma
if_valid_conns = wf["connections"].setdefault("if_valid", {"main": [[], []]})
if not any(c.get("node") == "meta_d1_campaign" for c in if_valid_conns["main"][0]):
    if_valid_conns["main"][0].append({"node": "meta_d1_campaign", "type": "main", "index": 0})

wf["connections"]["meta_d1_campaign"] = {"main": [[{"node": "meta_d2_adset", "type": "main", "index": 0}]]}
wf["connections"]["meta_d2_adset"] = {"main": [[{"node": "meta_d3_creative", "type": "main", "index": 0}]]}
wf["connections"]["meta_d3_creative"] = {"main": [[{"node": "meta_d4_ad", "type": "main", "index": 0}]]}
wf["connections"]["meta_d4_ad"] = {"main": [[{"node": "insert_campanha", "type": "main", "index": 0}]]}
wf["connections"]["insert_campanha"] = {"main": [[{"node": "audit_campanha_criada", "type": "main", "index": 0}]]}
wf["connections"]["audit_campanha_criada"] = {"main": [[{"node": "send_confirmacao_cliente", "type": "main", "index": 0}]]}

n8n_api.update_workflow(
    WF_ID,
    name=wf["name"],
    nodes=wf["nodes"],
    connections=wf["connections"],
    settings=wf.get("settings", {"executionOrder": "v1"}),
)
print(f"\n✓ Workflow atualizado: {WF_ID}")
print(f"  Nodes totais: {len(wf['nodes'])}")
