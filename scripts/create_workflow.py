#!/usr/bin/env python3
"""
Cria o workflow Quirk Auto Ads no n8n com estrutura inicial:
- Webhook trigger
- Switch text/media (router por body.message.type)

Idempotente: se workflow já existe (workflow_id em n8n_workflow/.workflow_id),
faz update em vez de criar duplicado.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api

WORKFLOW_NAME = "Quirk Auto Ads"
WEBHOOK_PATH = "quirk-auto-ads"
WF_ID_FILE = os.path.expanduser("/Users/renanreal/quirk_auto_ads/n8n_workflow/.workflow_id")


def build_initial_nodes():
    return [
        {
            "id": "webhook",
            "name": "webhook",
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 2,
            "position": [240, 300],
            "parameters": {
                "httpMethod": "POST",
                "path": WEBHOOK_PATH,
                "responseMode": "responseNode",
                "options": {},
            },
            "webhookId": WEBHOOK_PATH,
        },
        {
            "id": "respond_immediate",
            "name": "respond_immediate",
            "type": "n8n-nodes-base.respondToWebhook",
            "typeVersion": 1.1,
            "position": [460, 460],
            "parameters": {
                "respondWith": "text",
                "responseBody": "ok",
                "options": {},
            },
        },
        {
            "id": "switch_type",
            "name": "switch_type",
            "type": "n8n-nodes-base.switch",
            "typeVersion": 3,
            "position": [460, 200],
            "parameters": {
                "rules": {
                    "values": [
                        {
                            "conditions": {
                                "options": {
                                    "caseSensitive": True,
                                    "leftValue": "",
                                    "typeValidation": "loose",
                                },
                                "conditions": [
                                    {
                                        "leftValue": "={{ $json.body.message.type }}",
                                        "rightValue": "text",
                                        "operator": {"type": "string", "operation": "equals"},
                                    }
                                ],
                                "combinator": "and",
                            },
                            "renameOutput": True,
                            "outputKey": "text",
                        },
                        {
                            "conditions": {
                                "options": {
                                    "caseSensitive": True,
                                    "leftValue": "",
                                    "typeValidation": "loose",
                                },
                                "conditions": [
                                    {
                                        "leftValue": "={{ $json.body.message.type }}",
                                        "rightValue": "media",
                                        "operator": {"type": "string", "operation": "equals"},
                                    }
                                ],
                                "combinator": "and",
                            },
                            "renameOutput": True,
                            "outputKey": "media",
                        },
                    ]
                },
                "options": {},
            },
        },
    ]


def build_initial_connections():
    return {
        "webhook": {
            "main": [
                [
                    {"node": "respond_immediate", "type": "main", "index": 0},
                    {"node": "switch_type", "type": "main", "index": 0},
                ]
            ]
        }
    }


def main():
    nodes = build_initial_nodes()
    connections = build_initial_connections()

    # Idempotente
    existing_id = None
    if os.path.exists(WF_ID_FILE):
        existing_id = open(WF_ID_FILE).read().strip()
        try:
            existing = n8n_api.get_workflow(existing_id)
            print(f"Workflow já existe: {existing_id} ({existing['name']})")
            print("Atualizando com estrutura inicial...")
            result = n8n_api.update_workflow(
                existing_id, name=WORKFLOW_NAME, nodes=nodes, connections=connections
            )
            print(f"✓ Update OK")
        except Exception as e:
            print(f"Workflow id antigo ({existing_id}) não encontrado, criando novo...")
            existing_id = None

    if not existing_id:
        result = n8n_api.create_workflow(
            name=WORKFLOW_NAME, nodes=nodes, connections=connections
        )
        wf_id = result["id"]
        os.makedirs(os.path.dirname(WF_ID_FILE), exist_ok=True)
        with open(WF_ID_FILE, "w") as f:
            f.write(wf_id)
        print(f"✓ Workflow criado: {wf_id}")
        print(f"  UI: https://n8n.quirkgrowth.online/workflow/{wf_id}")
        print(f"  Webhook URL: https://n8n.quirkgrowth.online/webhook/{WEBHOOK_PATH}")
        print(f"  ID salvo em: {WF_ID_FILE}")


if __name__ == "__main__":
    main()
