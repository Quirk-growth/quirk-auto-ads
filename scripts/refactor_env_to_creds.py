#!/usr/bin/env python3
"""
Refatora o workflow Quirk Auto Ads para NÃO depender de variáveis $env:

1. HTTP UAZAPI nodes (5 deles) usam credential httpHeaderAuth "Quirk UAZAPI Header"
   em vez de '{{ $env.UAZAPI_TOKEN }}' no header.

2. Antes do D.1, adiciona um node Postgres "load_meta_token" que faz SELECT
   do meta_access_token na tabela auto_ads.config.

3. HTTP Meta nodes (D.1-D.4) leem o token de
   '{{ $('load_meta_token').item.json.valor }}' em vez de '{{ $env.META_ACCESS_TOKEN }}'.

Resultado: workflow funciona sem nenhuma ENV var no servidor n8n.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api
import config


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)

    # ─────────────────────────────────────────
    # PARTE 1: UAZAPI nodes → credential httpHeaderAuth
    # ─────────────────────────────────────────
    UAZAPI_NODE_NAMES = {
        "send_nao_cadastrado",
        "send_resposta",
        "send_confirmacao_cliente",
        "media_send_confirma",
        # media_download também usa UAZAPI mas com endpoint diferente — refatorar igual
        "media_download",
    }

    uazapi_updated = 0
    for node in wf["nodes"]:
        if node["name"] not in UAZAPI_NODE_NAMES:
            continue
        params = node["parameters"]
        # Remove "token" do headerParameters (será injetado pela credential)
        if "headerParameters" in params:
            kept = [
                h for h in params["headerParameters"].get("parameters", [])
                if h.get("name", "").lower() != "token"
            ]
            params["headerParameters"]["parameters"] = kept

        # Configura autenticação por credential httpHeaderAuth
        params["authentication"] = "predefinedCredentialType"
        params["nodeCredentialType"] = "httpHeaderAuth"
        node["credentials"] = node.get("credentials", {})
        node["credentials"]["httpHeaderAuth"] = config.UAZAPI_HEADER_CRED
        uazapi_updated += 1

    print(f"✓ {uazapi_updated} UAZAPI HTTP nodes refatorados (sem $env.UAZAPI_TOKEN)")

    # ─────────────────────────────────────────
    # PARTE 2: Inserir load_meta_token antes do D.1
    # ─────────────────────────────────────────
    LOAD_META_TOKEN_NODE = {
        "id": "load_meta_token",
        "name": "load_meta_token",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.6,
        "position": [3680, -100],
        "parameters": {
            "operation": "executeQuery",
            "query": "SELECT valor FROM auto_ads.config WHERE chave = 'meta_access_token' LIMIT 1",
            "options": {}
        },
        "credentials": {"postgres": config.POSTGRES_CRED},
    }

    existing = {n["name"] for n in wf["nodes"]}
    if "load_meta_token" not in existing:
        wf["nodes"].append(LOAD_META_TOKEN_NODE)
        print("✓ Node load_meta_token adicionado")

    # ─────────────────────────────────────────
    # PARTE 3: Reroteamento: if_valid (true) → load_meta_token → meta_d1_campaign
    # ─────────────────────────────────────────
    if_valid_conns = wf["connections"].setdefault("if_valid", {"main": [[], []]})
    # Remove conexão direta if_valid → meta_d1_campaign (true output)
    if_valid_conns["main"][0] = [
        c for c in if_valid_conns["main"][0]
        if c.get("node") != "meta_d1_campaign"
    ]
    # Adiciona if_valid (true) → load_meta_token
    if not any(c.get("node") == "load_meta_token" for c in if_valid_conns["main"][0]):
        if_valid_conns["main"][0].append({"node": "load_meta_token", "type": "main", "index": 0})

    # load_meta_token → meta_d1_campaign
    wf["connections"]["load_meta_token"] = {
        "main": [[{"node": "meta_d1_campaign", "type": "main", "index": 0}]]
    }

    # ─────────────────────────────────────────
    # PARTE 4: Substituir $env.META_ACCESS_TOKEN nos bodies dos 4 HTTP Meta
    # ─────────────────────────────────────────
    meta_updated = 0
    for node in wf["nodes"]:
        if node["name"].startswith("meta_d"):
            body = node["parameters"].get("jsonBody", "")
            new_body = body.replace(
                "{{ $env.META_ACCESS_TOKEN }}",
                "{{ $('load_meta_token').item.json.valor }}"
            )
            if new_body != body:
                node["parameters"]["jsonBody"] = new_body
                meta_updated += 1
    print(f"✓ {meta_updated} HTTP Meta nodes agora leem token via load_meta_token")

    n8n_api.update_workflow(
        WF_ID,
        name=wf["name"],
        nodes=wf["nodes"],
        connections=wf["connections"],
        settings=wf.get("settings", {"executionOrder": "v1"}),
    )
    print(f"\n✓ Workflow atualizado")


if __name__ == "__main__":
    main()
